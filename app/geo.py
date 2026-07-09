"""Geography: the London box and Great Britain polygon, and point classification.

Kept deliberately dependency-free (pure Python) so it is trivial to unit-test and
matches the ray-casting logic used in the original blimp-watch.sh shell script.
"""
from __future__ import annotations

# Greater London bounding box (roughly M25-ish): (lat_min, lat_max, lon_min, lon_max)
LONDON_BOX = (51.28, 51.70, -0.53, 0.34)

# Great Britain outline — coarse polygon of (lat, lon) vertices, clockwise.
# The southern/Channel edge runs down the middle of the water so France, Belgium,
# the Netherlands and Ireland fall OUTSIDE. (Northern Ireland is intentionally excluded.)
UK_POLYGON = [
    (58.85, -3.00), (57.60, -1.50), (56.20, -1.30), (55.00, -1.10), (53.60, 0.60),
    (53.00, 1.90), (52.30, 2.10), (51.80, 1.80), (51.40, 1.55), (51.00, 1.45),
    (50.30, -0.30), (49.90, -2.50), (49.80, -6.10), (51.60, -5.60), (52.60, -5.20),
    (53.40, -5.10), (54.20, -5.20), (55.00, -5.30), (55.60, -5.90), (56.60, -6.60),
    (57.60, -6.70), (58.65, -5.30),
]


def in_box(lat: float, lon: float, box=LONDON_BOX) -> bool:
    a, b, c, d = box
    return a <= lat <= b and c <= lon <= d


def in_polygon(lat: float, lon: float, poly=UK_POLYGON) -> bool:
    """Ray-casting point-in-polygon. lon is x, lat is y."""
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        yi, xi = poly[i]
        yj, xj = poly[j]
        if ((yi > lat) != (yj > lat)) and (
            lon < (xj - xi) * (lat - yi) / (yj - yi) + xi
        ):
            inside = not inside
        j = i
    return inside


def is_airborne(alt_baro, gs) -> bool:
    """alt_baro is the string 'ground' when moored/taxiing; otherwise a number of feet."""
    if alt_baro == "ground" or alt_baro is None:
        return False
    try:
        if float(alt_baro) > 300:
            return True
    except (TypeError, ValueError):
        pass
    try:
        return float(gs) > 3
    except (TypeError, ValueError):
        return False


def classify(ac: dict | None) -> dict:
    """Turn a raw aircraft record (or None when offline) into a state dict.

    presence: offline | ground | airborne_london | airborne_uk | airborne_away
    region:   uk | away | None   (None only when offline — caller keeps last known)
    """
    if not ac or ac.get("lat") is None:
        return {"presence": "offline", "region": None, "ac": None}

    lat = float(ac["lat"])
    lon = float(ac["lon"])
    airborne = is_airborne(ac.get("alt_baro"), ac.get("gs"))
    in_london = in_box(lat, lon)
    in_uk = in_polygon(lat, lon)
    region = "uk" if in_uk else "away"

    if not airborne:
        presence = "ground"
    elif in_london:
        presence = "airborne_london"
    elif in_uk:
        presence = "airborne_uk"
    else:
        presence = "airborne_away"

    return {"presence": presence, "region": region, "in_london": in_london, "in_uk": in_uk, "ac": ac}
