# blimp-watch

![ci](https://github.com/WillMatthews/blimp-watch/actions/workflows/ci.yml/badge.svg)

A tiny self-hosted service that tracks the **Goodyear Blimp Europe** — Zeppelin NT
**D-LZFN** (ICAO hex `3F232B`) — over the UK, and pushes you a notification when it:

- 🇬🇧 **arrives in UK** airspace,
- **leaves the UK**, or
- 🛩️ is **flying over London**.

It replaces the old laptop shell script with a proper always-on service:

- **One central poll.** The container polls the free ADS-B feeds once every `POLL_INTERVAL`
  seconds; every machine reads *its* cache instead of hammering upstream from each device.
- **Live map** at `/` — MapLibre GL vector-tile map (basemap: [OpenFreeMap](https://openfreemap.org),
  free & key-less) with a rotating airship silhouette, its recent track, an altitude sparkline,
  a follow toggle, and the UK/London geofences. When the blimp powers its transponder down,
  the marker fades and shows its **last-known position** ("last seen 3h ago") instead of vanishing.
  Position comes from the local cache, so it's low-latency on your LAN.
- **JSON API** for scripts, widgets, and other machines.
- **Proper push** via [ntfy](https://ntfy.sh) (default), Telegram, or a generic webhook —
  reaches your phone from anywhere, no dependence on a laptop being awake.

## Run it

```bash
cp .env.example .env       # then edit .env — at minimum set NTFY_TOPIC
docker compose up -d --build
```

- Map:   `http://<server>:8080/`
- State: `http://<server>:8080/api/state`

State (the sticky UK region + last presence) persists in `./data`, so a restart won't
re-fire "arrived in the UK" or forget where it last was.

## Notifications

Set **one** backend in `.env` (leave all unset for a log-only dry run):

| Backend  | Env vars                                   | Notes |
|----------|--------------------------------------------|-------|
| ntfy     | `NTFY_TOPIC` (+ `NTFY_SERVER`, `NTFY_TOKEN`)| Subscribe to the same topic in the ntfy app. Use a long, unguessable topic on public ntfy.sh. |
| Telegram | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`   | Create a bot with @BotFather. |
| Webhook  | `WEBHOOK_URL`                              | Receives JSON `{title,message,priority,tags,url}`. |

Notifications fire **only on transitions**, and never on a nightly transponder power-down:
UK region is *sticky* across "offline", so you only get "left the UK" when the blimp is
actually seen airborne on the far side of the boundary.

## API

| Endpoint        | Returns |
|-----------------|---------|
| `GET /api/state`| Current cached snapshot: `presence`, `region`, `aircraft`, `age_sec`, `feed_ok`, `summary`. |
| `GET /api/history` | Recent track points for the map trail. |
| `GET /api/geo`  | The `london_box` and `uk_polygon` geofences (single source of truth). |
| `GET /healthz`  | `200` once the first poll has landed, else `503`. |

`presence` ∈ `offline | ground | airborne_london | airborne_uk | airborne_away`.

## CLI client

From any machine, point `client/blimp` at the server:

```bash
export BLIMP_WATCH_URL=http://<server>:8080
client/blimp
```

## Geofences

- **London**: bounding box 51.28–51.70 N, −0.53–0.34 E (roughly the M25).
- **UK**: a **MultiPolygon** — a coarse Great Britain outline (southern edge down the middle
  of the English Channel) **plus a Northern Ireland outline**. A point counts as UK if it's
  inside either. France, Belgium, the Netherlands and the **Republic of Ireland** (Dublin,
  Donegal, Sligo, Monaghan…) all fall outside. The NI land border is approximate.

Both live in `app/geo.py` and are served over `/api/geo`; the map draws them from there.

## Map basemap

The map (`app/static/index.html`) uses **MapLibre GL JS** with **OpenFreeMap** vector tiles
(the `liberty` style) — no API key required. The viewing browser needs internet for the
basemap tiles; the tracking/data path is fully local. To use a different basemap, change the
`STYLE` constant at the top of the page's script (e.g. self-hosted PMTiles for a fully offline
LAN, or a MapTiler/Stadia style with a key).

## Tests

```bash
python -m pytest        # or: python tests/test_geo.py
```
