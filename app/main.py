"""blimp-watch service: polls ADS-B centrally, caches state, serves a live map + API,
and pushes notifications on UK-border and over-London transitions."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections import deque
from pathlib import Path

import aiohttp
from aiohttp import web

from .adsb import fetch_aircraft
from .geo import LONDON_BOX, UK_POLYGON, classify
from .notify import Notifier

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"),
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("blimp")

HEX = os.getenv("HEX", "3f232b").lower()
NAME = os.getenv("BLIMP_NAME", "Goodyear Blimp (D-LZFN)")
POLL_INTERVAL = float(os.getenv("POLL_INTERVAL", "15"))
PORT = int(os.getenv("PORT", "8080"))
STATE_DIR = Path(os.getenv("STATE_DIR", "/data"))
HISTORY_MAX = int(os.getenv("HISTORY_MAX", "720"))  # ~3h at 15s
MAP_URL = f"https://globe.adsbexchange.com/?icao={HEX}"
STATIC = Path(__file__).parent / "static"

STATE_FILE = STATE_DIR / "state.json"

SUMMARIES = {
    "airborne_london": "🛩️ Flying OVER LONDON",
    "airborne_uk": "Airborne over the UK",
    "airborne_away": "Airborne outside the UK",
    "ground": "On the ground",
    "offline": "Offline (no ADS-B — powered down or out of range)",
}


def summarize(presence: str, ac: dict | None) -> str:
    base = SUMMARIES.get(presence, presence)
    if not ac or ac.get("lat") is None:
        return f"{NAME}: {base}."
    pos = f"@ {ac['lat']:.4f}, {ac['lon']:.4f}"
    alt = ac.get("alt_baro")
    if alt == "ground":  # moored/taxiing — no meaningful altitude to show
        return f"{NAME}: {base} {pos}."
    return f"{NAME}: {base} — {alt} ft, {ac.get('gs')} kt, track {ac.get('track')}° {pos}"


class Service:
    def __init__(self) -> None:
        self.notifier = Notifier()
        self.history: deque[dict] = deque(maxlen=HISTORY_MAX)
        # persisted, sticky pieces
        persisted = self._load_persisted()
        self.presence = persisted.get("presence", "unknown")
        self.region = persisted.get("region", "unknown")  # last KNOWN region (never None)
        # live snapshot for the API
        self.snapshot = {
            "name": NAME, "hex": HEX, "map_url": MAP_URL,
            "presence": self.presence, "region": self.region,
            "feed_ok": False, "ts": None, "age_sec": None,
            "in_london": False, "in_uk": False, "aircraft": None,
            "summary": f"{NAME}: starting up…",
        }

    def _load_persisted(self) -> dict:
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:  # noqa: BLE001
            return {}

    def _persist(self) -> None:
        try:
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            STATE_FILE.write_text(json.dumps({"presence": self.presence, "region": self.region}))
        except Exception as e:  # noqa: BLE001
            log.warning("could not persist state: %s", e)

    async def poll_once(self, session: aiohttp.ClientSession) -> None:
        try:
            ac = await fetch_aircraft(session, HEX)  # dict | None
            feed_ok = True
        except Exception as e:  # noqa: BLE001 - transient: keep last good, don't fire transitions
            log.warning("poll failed, keeping last state: %s", e)
            self.snapshot["feed_ok"] = False
            return

        cls = classify(ac)
        new_presence = cls["presence"]
        new_region = cls["region"]  # None when offline
        prev_presence, prev_region = self.presence, self.region

        await self._maybe_notify(session, prev_presence, prev_region, new_presence, new_region, ac)

        # commit state — region is sticky across offline
        self.presence = new_presence
        if new_region is not None:
            self.region = new_region
        self._persist()

        now = time.time()
        summary = summarize(new_presence, ac)
        self.snapshot.update({
            "presence": new_presence, "region": self.region, "feed_ok": feed_ok,
            "ts": now, "age_sec": 0, "in_london": cls.get("in_london", False),
            "in_uk": cls.get("in_uk", False), "aircraft": ac, "summary": summary,
        })
        if ac and ac.get("lat") is not None:
            self.history.append({
                "ts": now, "lat": ac["lat"], "lon": ac["lon"],
                "alt": ac.get("alt_baro"), "gs": ac.get("gs"), "track": ac.get("track"),
                "presence": new_presence,
            })

    async def _maybe_notify(self, session, prev_presence, prev_region,
                            new_presence, new_region, ac) -> None:
        msg = summarize(new_presence, ac)
        # On a cold start prev_region/prev_presence are "unknown" — seed the baseline
        # silently rather than firing a spurious "arrived"/"over London" on first poll.
        # UK border crossings — only when online (new_region not None); never on power-down.
        if new_region == "uk" and prev_region == "away":
            await self.notifier.send(session, "Goodyear Blimp has arrived in the UK! 🇬🇧",
                                     msg, priority="high", tags=["airplane", "gb"], click=MAP_URL)
        elif new_region == "away" and prev_region == "uk":
            await self.notifier.send(session, "Goodyear Blimp has left the UK", msg,
                                     priority="default", tags=["airplane"], click=MAP_URL)
        # Over London (fires on any genuine transition into the box, but not at cold start).
        if (new_presence == "airborne_london"
                and prev_presence not in (None, "unknown", "airborne_london")):
            await self.notifier.send(session, "Goodyear Blimp over London!", msg,
                                     priority="urgent", tags=["airplane", "cityscape"], click=MAP_URL)

    async def run(self, app: web.Application) -> None:
        log.info("blimp-watch starting: hex=%s interval=%ss notifiers=%s",
                 HEX, POLL_INTERVAL, self.notifier.backends or ["log-only"])
        async with aiohttp.ClientSession(headers={"User-Agent": "blimp-watch/1.0"}) as session:
            while True:
                try:
                    await self.poll_once(session)
                except asyncio.CancelledError:
                    raise
                except Exception as e:  # noqa: BLE001 - never let the loop die
                    log.exception("unexpected poll error: %s", e)
                await asyncio.sleep(POLL_INTERVAL)


# ---- HTTP handlers ---------------------------------------------------------

async def handle_state(request: web.Request) -> web.Response:
    svc: Service = request.app["svc"]
    snap = dict(svc.snapshot)
    if snap.get("ts"):
        snap["age_sec"] = round(time.time() - snap["ts"], 1)
    return web.json_response(snap)


async def handle_history(request: web.Request) -> web.Response:
    svc: Service = request.app["svc"]
    return web.json_response(list(svc.history))


async def handle_geo(request: web.Request) -> web.Response:
    return web.json_response({"london_box": LONDON_BOX, "uk_polygon": UK_POLYGON})


async def handle_health(request: web.Request) -> web.Response:
    svc: Service = request.app["svc"]
    ok = svc.snapshot.get("ts") is not None
    return web.json_response({"ok": ok, "feed_ok": svc.snapshot.get("feed_ok")},
                             status=200 if ok else 503)


async def handle_index(request: web.Request) -> web.FileResponse:
    return web.FileResponse(STATIC / "index.html")


async def _start_bg(app: web.Application) -> None:
    app["task"] = asyncio.create_task(app["svc"].run(app))


async def _stop_bg(app: web.Application) -> None:
    app["task"].cancel()
    try:
        await app["task"]
    except asyncio.CancelledError:
        pass


def build_app() -> web.Application:
    app = web.Application()
    app["svc"] = Service()
    app.router.add_get("/", handle_index)
    app.router.add_get("/api/state", handle_state)
    app.router.add_get("/api/history", handle_history)
    app.router.add_get("/api/geo", handle_geo)
    app.router.add_get("/healthz", handle_health)
    app.router.add_static("/static/", STATIC)
    app.on_startup.append(_start_bg)
    app.on_cleanup.append(_stop_bg)
    return app


if __name__ == "__main__":
    web.run_app(build_app(), port=PORT)
