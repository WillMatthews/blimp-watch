"""Flight accumulator logic. Pure — run: python -m pytest  (or python tests/test_flight.py)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.flight import FLIGHT_GAP_S, FlightTracker  # noqa: E402


def test_takeoff_and_distance():
    f = FlightTracker()
    f.update(1000, "ground")                      # on the ground: nothing accrues
    assert f.airborne_since is None and f.dist_km == 0
    f.update(1010, "airborne_uk", 51.0, 0.0)      # takeoff
    assert f.airborne_since == 1010 and f.dist_km == 0
    f.update(1025, "airborne_uk", 51.0, 1.0)      # ~70 km east at 51°N
    assert 60 < f.dist_km < 80


def test_ground_resets_flight():
    f = FlightTracker(airborne_since=100, dist_km=50, last_pt=[51, 0], last_air_ts=100)
    f.update(200, "ground")
    assert f.airborne_since is None and f.dist_km == 0 and f.last_pt is None


def test_offline_is_sticky_and_resumes():
    f = FlightTracker()
    f.update(1000, "airborne_london", 51.5, -0.1)
    since = f.airborne_since
    f.update(1100, "offline")                     # brief gap — offline never resets
    assert f.airborne_since == since
    f.update(1150, "airborne_london", 51.5, 0.0)  # resumes same flight (gap < FLIGHT_GAP_S)
    assert f.airborne_since == since and f.dist_km > 0


def test_long_gap_starts_new_flight():
    f = FlightTracker()
    f.update(1000, "airborne_uk", 51.0, 0.0)
    f.update(1000 + FLIGHT_GAP_S + 50, "airborne_uk", 52.0, 0.0)   # gap too long -> new flight
    assert f.airborne_since == 1000 + FLIGHT_GAP_S + 50 and f.dist_km == 0


def test_dict_roundtrip():
    f = FlightTracker()
    f.update(1000, "airborne_uk", 51.0, 0.0)
    f.update(1015, "airborne_uk", 51.0, 0.5)
    g = FlightTracker.from_dict(f.to_dict())
    assert g.airborne_since == f.airborne_since and abs(g.dist_km - f.dist_km) < 1e-9


if __name__ == "__main__":
    for _name, _fn in list(globals().items()):
        if _name.startswith("test_"):
            _fn()
    print("all flight tests passed")
