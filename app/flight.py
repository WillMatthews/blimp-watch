"""Pure flight-state accumulator: airborne duration + track distance for one aircraft.

No I/O and no async — trivially unit-testable (see tests/test_flight.py).
"""
from __future__ import annotations

from .geo import haversine_km

# A gap between airborne fixes longer than this (seconds) means the flight ended
# off-radar (landed & powered down); the next airborne fix starts a fresh flight
# rather than resuming and drawing a bogus straight line across the gap.
FLIGHT_GAP_S = 900


class FlightTracker:
    def __init__(self, airborne_since=None, dist_km=0.0, last_pt=None, last_air_ts=None):
        self.airborne_since = airborne_since  # epoch when the current flight began
        self.dist_km = dist_km                # cumulative track distance this flight
        self.last_pt = last_pt                # [lat, lon] of the last airborne fix
        self.last_air_ts = last_air_ts        # epoch of the last airborne fix

    def update(self, now: float, presence: str, lat=None, lon=None) -> None:
        airborne = presence.startswith("airborne") and lat is not None and lon is not None
        if airborne:
            resumed = self.airborne_since is not None and (
                self.last_air_ts is None or now - self.last_air_ts <= FLIGHT_GAP_S)
            if resumed:
                if self.last_pt:
                    self.dist_km += haversine_km(self.last_pt[0], self.last_pt[1], lat, lon)
            else:  # start a new flight
                self.airborne_since = now
                self.dist_km = 0.0
            self.last_pt = [lat, lon]
            self.last_air_ts = now
        elif presence == "ground":  # confirmed down — end the flight (offline stays sticky)
            self.reset()

    def reset(self) -> None:
        self.airborne_since = None
        self.dist_km = 0.0
        self.last_pt = None
        self.last_air_ts = None

    def to_dict(self) -> dict:
        return {"airborne_since": self.airborne_since, "dist_km": self.dist_km,
                "last_pt": self.last_pt, "last_air_ts": self.last_air_ts}

    @classmethod
    def from_dict(cls, d: dict) -> "FlightTracker":
        return cls(d.get("airborne_since"), d.get("dist_km", 0.0),
                   d.get("last_pt"), d.get("last_air_ts"))
