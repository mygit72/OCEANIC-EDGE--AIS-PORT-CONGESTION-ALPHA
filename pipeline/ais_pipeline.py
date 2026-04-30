"""
Oceanic Edge — AIS & Port Congestion Pipeline
Fetches live vessel data from MarineTraffic API and computes congestion scores
"""

import requests
import json
import math
import time
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict

# ── Key Ports of Interest ──────────────────────────────────────────────────────
PORTS = {
    "Houston":        {"lat": 29.7355, "lon": -95.0060, "radius_nm": 30, "commodity": "Crude Oil"},
    "Rotterdam":      {"lat": 51.9225, "lon":   4.4792, "radius_nm": 25, "commodity": "Mixed / Container"},
    "Singapore":      {"lat":  1.2644, "lon": 103.8230, "radius_nm": 20, "commodity": "Bunker / Container"},
    "Qingdao":        {"lat": 36.0671, "lon": 120.3826, "radius_nm": 25, "commodity": "Iron Ore / Coal"},
    "Fujairah":       {"lat": 25.1288, "lon":  56.3264, "radius_nm": 20, "commodity": "Crude Oil"},
    "Los Angeles":    {"lat": 33.7395, "lon":-118.2654, "radius_nm": 30, "commodity": "Container"},
}

# Vessel type codes → category
VESSEL_TYPES = {
    range(70, 80):  "Cargo",
    range(80, 90):  "Tanker",
    range(60, 70):  "Passenger",
    range(30, 40):  "Fishing",
    range(50, 60):  "Special",
    range(20, 30):  "WIG",
}


@dataclass
class Vessel:
    mmsi: str
    name: str
    lat: float
    lon: float
    speed: float       # knots
    heading: int
    ship_type: int
    status: int        # AIS nav status (0=underway, 1=at anchor, 5=moored)
    destination: str
    timestamp: str
    flag: str = ""

    @property
    def is_waiting(self) -> bool:
        """True if vessel is anchored/moored or effectively stationary (<0.5 kn)"""
        return self.status in (1, 5) or self.speed < 0.5

    @property
    def vessel_category(self) -> str:
        for rng, cat in VESSEL_TYPES.items():
            if self.ship_type in rng:
                return cat
        return "Other"


@dataclass
class CongestionScore:
    port: str
    timestamp: str
    total_vessels: int
    waiting_vessels: int
    tankers_waiting: int
    cargo_waiting: int
    avg_speed_knots: float
    congestion_index: float   # 0–100 normalised score
    signal: str               # "LOW" / "MODERATE" / "HIGH" / "CRITICAL"
    commodity: str


def haversine_nm(lat1, lon1, lat2, lon2) -> float:
    """Distance in nautical miles between two lat/lon points."""
    R = 3440.065  # Earth radius in nm
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


class MarineTrafficClient:
    BASE = "https://services.marinetraffic.com/api"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "OceanicEdge/1.0"})

    def get_vessels_in_area(self, min_lat, max_lat, min_lon, max_lon,
                             vessel_type: Optional[int] = None) -> List[dict]:
        """
        PS06 — Vessel positions in a custom area.
        Returns list of vessel dicts.
        """
        params = {
            "v":       "8",
            "minlat":  min_lat,
            "maxlat":  max_lat,
            "minlon":  min_lon,
            "maxlon":  max_lon,
            "protocol":"jsono",
            "msgtype": "simple",
        }
        if vessel_type:
            params["shiptype"] = vessel_type

        url = f"{self.BASE}/exportvessels/{self.api_key}/"
        try:
            resp = self.session.get(url, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            # MT returns list of lists or list of dicts depending on version
            return data if isinstance(data, list) else []
        except Exception as e:
            print(f"  [API ERROR] {e}")
            return []

    def get_port_congestion(self, port_id: int, market: str = "wet bulk",
                             year: Optional[int] = None, week: Optional[int] = None) -> dict:
        """
        VI06 — Port Congestion endpoint (requires specific API tier).
        """
        now = datetime.now()
        params = {
            "v":       "1",
            "portid":  port_id,
            "market":  market,
            "year":    year or now.year,
            "week":    week or now.isocalendar()[1],
            "protocol":"jsono",
        }
        url = f"{self.BASE}/portcongestion/{self.api_key}/"
        try:
            resp = self.session.get(url, params=params, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            print(f"  [PORT CONGESTION API ERROR] {e}")
            return {}


class CongestionEngine:
    """
    Computes a congestion score from a list of vessels near a port.
    Works even if you only have basic PS06 vessel position data.
    """

    def score(self, port_name: str, port_info: dict,
              vessels: List[Vessel]) -> CongestionScore:
        now = datetime.now(timezone.utc).isoformat()

        if not vessels:
            return CongestionScore(
                port=port_name, timestamp=now,
                total_vessels=0, waiting_vessels=0,
                tankers_waiting=0, cargo_waiting=0,
                avg_speed_knots=0.0, congestion_index=0.0,
                signal="NO DATA", commodity=port_info["commodity"]
            )

        waiting = [v for v in vessels if v.is_waiting]
        tankers = [v for v in waiting if v.vessel_category == "Tanker"]
        cargo   = [v for v in waiting if v.vessel_category == "Cargo"]
        speeds  = [v.speed for v in vessels if v.speed > 0]
        avg_spd = sum(speeds) / len(speeds) if speeds else 0.0

        # Congestion Index formula:
        #   base = (waiting / total) * 100
        #   penalty for low avg speed (congested approaches slow everything down)
        #   bonus weight for tankers (commodity signal)
        if len(vessels) > 0:
            wait_ratio = len(waiting) / len(vessels)
            speed_penalty = max(0, (5 - avg_spd) / 5) * 20   # up to +20 if avg < 5kn
            tanker_boost  = min(20, len(tankers) * 2)          # up to +20
            raw = wait_ratio * 60 + speed_penalty + tanker_boost
            index = round(min(100, raw), 1)
        else:
            index = 0.0

        if index >= 75:   signal = "CRITICAL"
        elif index >= 50: signal = "HIGH"
        elif index >= 25: signal = "MODERATE"
        else:             signal = "LOW"

        return CongestionScore(
            port=port_name, timestamp=now,
            total_vessels=len(vessels),
            waiting_vessels=len(waiting),
            tankers_waiting=len(tankers),
            cargo_waiting=len(cargo),
            avg_speed_knots=round(avg_spd, 2),
            congestion_index=index,
            signal=signal,
            commodity=port_info["commodity"]
        )


class OceanicEdgePipeline:
    def __init__(self, api_key: str):
        self.client = CongestionEngine()
        self.mt     = MarineTrafficClient(api_key)
        self.api_key = api_key

    def fetch_port(self, port_name: str, port_info: dict) -> CongestionScore:
        lat, lon, radius = port_info["lat"], port_info["lon"], port_info["radius_nm"]

        # Convert radius in nm to rough degrees
        deg = radius / 60.0
        min_lat, max_lat = lat - deg, lat + deg
        min_lon, max_lon = lon - deg, lon + deg

        print(f"  Fetching vessels near {port_name}...")
        raw_vessels = self.mt.get_vessels_in_area(min_lat, max_lat, min_lon, max_lon)

        vessels = []
        for v in raw_vessels:
            try:
                # Handle both list and dict formats from MT API
                if isinstance(v, list):
                    vessel = Vessel(
                        mmsi=str(v[0]), name=str(v[1]),
                        lat=float(v[2]), lon=float(v[3]),
                        speed=float(v[4]), heading=int(v[5]),
                        ship_type=int(v[6]) if v[6] else 0,
                        status=int(v[7]) if v[7] else 0,
                        destination=str(v[8]) if len(v) > 8 else "",
                        timestamp=str(v[9]) if len(v) > 9 else "",
                    )
                elif isinstance(v, dict):
                    vessel = Vessel(
                        mmsi=str(v.get("MMSI", "")),
                        name=str(v.get("SHIPNAME", v.get("NAME", "UNKNOWN"))),
                        lat=float(v.get("LAT", 0)),
                        lon=float(v.get("LON", 0)),
                        speed=float(v.get("SPEED", 0)) / 10,  # MT sends speed *10
                        heading=int(v.get("HEADING", 0)),
                        ship_type=int(v.get("SHIPTYPE", 0)),
                        status=int(v.get("STATUS", 0)),
                        destination=str(v.get("DESTINATION", "")),
                        timestamp=str(v.get("TIMESTAMP", "")),
                        flag=str(v.get("FLAG", "")),
                    )
                else:
                    continue

                # Filter to only vessels actually within the circular radius
                dist = haversine_nm(lat, lon, vessel.lat, vessel.lon)
                if dist <= radius:
                    vessels.append(vessel)
            except (ValueError, IndexError, TypeError):
                continue

        print(f"    → {len(vessels)} vessels within {radius}nm")
        return self.client.score(port_name, port_info, vessels)

    def run(self, ports: Optional[List[str]] = None) -> List[CongestionScore]:
        target_ports = {k: v for k, v in PORTS.items()
                        if ports is None or k in ports}
        scores = []
        print(f"\n{'='*60}")
        print(f"  OCEANIC EDGE — AIS Pipeline Run")
        print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print(f"{'='*60}")

        for name, info in target_ports.items():
            try:
                score = self.fetch_port(name, info)
                scores.append(score)
                print(f"    ✓ {name:15s} | Index: {score.congestion_index:5.1f} | "
                      f"Signal: {score.signal:8s} | "
                      f"Waiting: {score.waiting_vessels}/{score.total_vessels}")
                time.sleep(1)  # Rate limit courtesy
            except Exception as e:
                print(f"    ✗ {name}: {e}")

        return scores

    def save(self, scores: List[CongestionScore], path: str = "data/latest.json"):
        import os
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump([asdict(s) for s in scores], f, indent=2)
        print(f"\n  Saved → {path}")


if __name__ == "__main__":
    import sys
    API_KEY = sys.argv[1] if len(sys.argv) > 1 else "YOUR_KEY_HERE"
    pipeline = OceanicEdgePipeline(API_KEY)
    scores   = pipeline.run()
    pipeline.save(scores, "data/latest.json")
