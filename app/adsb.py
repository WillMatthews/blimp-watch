"""Fetch a single aircraft's live ADS-B record from free, no-auth feeds."""
from __future__ import annotations

import logging

import aiohttp

log = logging.getLogger("blimp.adsb")

# Free, key-less feeds. Tried in order; first success wins.
FEEDS = [
    "https://api.airplanes.live/v2/hex/{hex}",
    "https://opendata.adsb.fi/api/v2/hex/{hex}",
]


async def fetch_aircraft(session: aiohttp.ClientSession, hexid: str) -> dict | None:
    """Return the aircraft dict, or None if it is not currently transmitting."""
    for tmpl in FEEDS:
        url = tmpl.format(hex=hexid.lower())
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status != 200:
                    log.warning("feed %s -> HTTP %s", url, r.status)
                    continue
                data = await r.json(content_type=None)
        except Exception as e:  # noqa: BLE001 - any network/parse error: try next feed
            log.warning("feed %s failed: %s", url, e)
            continue
        ac = (data.get("ac") or [None])[0]
        return ac  # None means "known aircraft, but no current position" (powered down / out of range)
    # every feed errored — signal a transient failure so the caller keeps the last good state
    raise RuntimeError("all ADS-B feeds unreachable")
