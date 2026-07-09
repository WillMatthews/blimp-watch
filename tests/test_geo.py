"""Point-in-geofence checks. Run: python -m pytest  (or python tests/test_geo.py)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.geo import classify, in_box, in_polygon  # noqa: E402

INSIDE_UK = {
    "London": (51.50, -0.12), "Aberdeen": (57.15, -2.09), "Newcastle": (54.98, -1.60),
    "Lands End": (50.07, -5.71), "Cardiff": (51.48, -3.18), "Holyhead": (53.31, -4.63),
    "John o Groats": (58.63, -3.07),
}
OUTSIDE_UK = {
    "Calais": (50.95, 1.85), "Paris": (48.85, 2.35), "Cherbourg": (49.63, -1.62),
    "Dublin": (53.35, -6.26), "Belfast": (54.60, -5.93), "Ostend": (51.21, 2.92),
    "Amsterdam": (52.37, 4.90),
}


def test_uk_polygon():
    for name, (lat, lon) in INSIDE_UK.items():
        assert in_polygon(lat, lon), f"{name} should be inside UK"
    for name, (lat, lon) in OUTSIDE_UK.items():
        assert not in_polygon(lat, lon), f"{name} should be outside UK"


def test_london_box():
    assert in_box(51.50, -0.12)          # central London
    assert not in_box(51.46, 0.36)       # just east of the box edge
    assert not in_box(52.20, -0.10)      # too far north


def test_classify():
    # airborne over London
    c = classify({"lat": 51.50, "lon": -0.10, "alt_baro": 1000, "gs": 35})
    assert c["presence"] == "airborne_london" and c["region"] == "uk"
    # moored (ground) near London
    c = classify({"lat": 51.53, "lon": 0.23, "alt_baro": "ground", "gs": 0})
    assert c["presence"] == "ground" and c["region"] == "uk"
    # airborne over the continent
    c = classify({"lat": 50.95, "lon": 1.85, "alt_baro": 1200, "gs": 30})
    assert c["presence"] == "airborne_away" and c["region"] == "away"
    # offline
    c = classify(None)
    assert c["presence"] == "offline" and c["region"] is None


if __name__ == "__main__":
    test_uk_polygon(); test_london_box(); test_classify()
    print("all geo tests passed")
