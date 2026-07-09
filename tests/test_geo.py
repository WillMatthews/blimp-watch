"""Point-in-geofence checks. Run: python -m pytest  (or python tests/test_geo.py)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.geo import classify, in_box, in_uk  # noqa: E402

INSIDE_UK = {
    # Great Britain
    "London": (51.50, -0.12), "Aberdeen": (57.15, -2.09), "Newcastle": (54.98, -1.60),
    "Lands End": (50.07, -5.71), "Cardiff": (51.48, -3.18), "Holyhead": (53.31, -4.63),
    "John o Groats": (58.63, -3.07),
    # Northern Ireland
    "Belfast": (54.597, -5.930), "Derry": (54.997, -7.309), "Enniskillen": (54.344, -7.631),
    "Newry": (54.176, -6.349), "Armagh": (54.350, -6.653),
}
OUTSIDE_UK = {
    "Calais": (50.95, 1.85), "Paris": (48.85, 2.35), "Cherbourg": (49.63, -1.62),
    "Ostend": (51.21, 2.92), "Amsterdam": (52.37, 4.90),
    # Republic of Ireland — must stay OUT despite Northern Ireland being IN
    "Dublin": (53.35, -6.26), "Letterkenny": (54.956, -7.734), "Sligo": (54.270, -8.476),
    "Dundalk": (54.001, -6.404), "Monaghan": (54.249, -6.968), "DonegalTown": (54.654, -8.110),
}


def test_uk_polygon():
    for name, (lat, lon) in INSIDE_UK.items():
        assert in_uk(lat, lon), f"{name} should be inside UK"
    for name, (lat, lon) in OUTSIDE_UK.items():
        assert not in_uk(lat, lon), f"{name} should be outside UK"


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
