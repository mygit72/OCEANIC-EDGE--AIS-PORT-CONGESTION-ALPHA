"""
Oceanic Edge — Realistic Data Simulator
Generates plausible AIS vessel data and congestion scores for all 6 ports.
Used when the API tier doesn't cover area vessel exports.
"""

import json, random, math
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, asdict
from typing import List

random.seed(42)

PORTS = {
    "Houston":     {"lat": 29.7355, "lon": -95.006,  "radius_nm": 30, "commodity": "Crude Oil",          "base_load": 85},
    "Rotterdam":   {"lat": 51.9225, "lon":   4.479,  "radius_nm": 25, "commodity": "Mixed / Container",   "base_load": 70},
    "Singapore":   {"lat":  1.2644, "lon": 103.823,  "radius_nm": 20, "commodity": "Bunker / Container",  "base_load": 90},
    "Qingdao":     {"lat": 36.0671, "lon": 120.382,  "radius_nm": 25, "commodity": "Iron Ore / Coal",     "base_load": 60},
    "Fujairah":    {"lat": 25.1288, "lon":  56.326,  "radius_nm": 20, "commodity": "Crude Oil",            "base_load": 78},
    "Los Angeles": {"lat": 33.7395, "lon":-118.265,  "radius_nm": 30, "commodity": "Container",            "base_load": 55},
}

SHIP_NAMES_PREFIX = ["Pacific", "Atlantic", "Global", "Ocean", "Sea", "Nordic",
                     "Asian", "Gulf", "Eastern", "Western", "Royal", "Grand"]
SHIP_NAMES_SUFFIX = ["Star", "Eagle", "Pioneer", "Voyager", "Express", "Spirit",
                     "Fortune", "Horizon", "Victory", "Promise", "Trader", "Pearl"]
FLAGS = ["US", "PH", "LR", "PA", "MH", "BS", "CY", "SG", "HK", "NO", "GR", "GB"]


def rand_ship_name():
    return f"{random.choice(SHIP_NAMES_PREFIX)} {random.choice(SHIP_NAMES_SUFFIX)}"

def rand_mmsi():
    return str(random.randint(200000000, 799999999))

def rand_point_near(lat, lon, radius_nm):
    """Random point within radius (nautical miles) of center."""
    dist = random.uniform(0, radius_nm)
    angle = random.uniform(0, 2 * math.pi)
    dlat = (dist / 60) * math.cos(angle)
    dlon = (dist / 60) * math.sin(angle) / math.cos(math.radians(lat))
    return round(lat + dlat, 4), round(lon + dlon, 4)


def simulate_vessels(port_name, port_info, n_vessels=None):
    """Simulate a realistic set of vessels around a port."""
    load = port_info["base_load"]
    # Add some daily variation
    hour = datetime.now().hour
    load_jitter = random.randint(-10, 15) + (5 if 8 <= hour <= 18 else -3)
    load = max(20, min(100, load + load_jitter))

    # Total vessels scales with port load
    if n_vessels is None:
        n_vessels = int(load * 0.6) + random.randint(5, 20)

    vessels = []
    for _ in range(n_vessels):
        vlat, vlon = rand_point_near(port_info["lat"], port_info["lon"], port_info["radius_nm"])

        # Vessel type distribution (varies by port commodity)
        if "Crude" in port_info["commodity"]:
            type_weights = {"Tanker": 55, "Cargo": 25, "Other": 20}
        elif "Iron Ore" in port_info["commodity"] or "Coal" in port_info["commodity"]:
            type_weights = {"Tanker": 20, "Cargo": 60, "Other": 20}
        elif "Container" in port_info["commodity"]:
            type_weights = {"Tanker": 15, "Cargo": 65, "Other": 20}
        else:
            type_weights = {"Tanker": 30, "Cargo": 40, "Other": 30}

        categories = list(type_weights.keys())
        weights    = list(type_weights.values())
        category   = random.choices(categories, weights=weights)[0]

        if category == "Tanker":
            ship_type = random.randint(80, 89)
        elif category == "Cargo":
            ship_type = random.randint(70, 79)
        else:
            ship_type = random.choice([50, 51, 52, 60, 90])

        # Status & speed
        r = random.random()
        if r < 0.35:    # Waiting / anchored
            status, speed = 1, round(random.uniform(0, 0.4), 1)
        elif r < 0.45:  # Moored
            status, speed = 5, 0.0
        elif r < 0.65:  # Slow approach
            status, speed = 0, round(random.uniform(0.5, 5.0), 1)
        else:           # Underway
            status, speed = 0, round(random.uniform(5.0, 14.0), 1)

        ts = (datetime.now(timezone.utc) - timedelta(minutes=random.randint(1, 30))).strftime("%Y-%m-%d %H:%M:%S")

        vessels.append({
            "mmsi": rand_mmsi(),
            "name": rand_ship_name(),
            "lat": vlat,
            "lon": vlon,
            "speed": speed,
            "heading": random.randint(0, 359),
            "ship_type": ship_type,
            "ship_type_name": category,
            "status": status,
            "destination": port_name.upper(),
            "timestamp": ts,
            "flag": random.choice(FLAGS),
        })

    return vessels


def compute_congestion(port_name, port_info, vessels):
    """Same scoring logic as the real pipeline."""
    now = datetime.now(timezone.utc).isoformat()
    if not vessels:
        return {"port": port_name, "congestion_index": 0, "signal": "NO DATA"}

    waiting  = [v for v in vessels if v["status"] in (1, 5) or v["speed"] < 0.5]
    tankers  = [v for v in waiting if v.get("ship_type_name") == "Tanker"]
    cargo    = [v for v in waiting if v.get("ship_type_name") == "Cargo"]
    speeds   = [v["speed"] for v in vessels if v["speed"] > 0]
    avg_spd  = round(sum(speeds) / len(speeds), 2) if speeds else 0.0

    wait_ratio    = len(waiting) / len(vessels)
    speed_penalty = max(0, (5 - avg_spd) / 5) * 20
    tanker_boost  = min(20, len(tankers) * 2)
    index = round(min(100, wait_ratio * 60 + speed_penalty + tanker_boost), 1)

    if index >= 75:   signal = "CRITICAL"
    elif index >= 50: signal = "HIGH"
    elif index >= 25: signal = "MODERATE"
    else:             signal = "LOW"

    return {
        "port": port_name,
        "timestamp": now,
        "total_vessels": len(vessels),
        "waiting_vessels": len(waiting),
        "tankers_waiting": len(tankers),
        "cargo_waiting": len(cargo),
        "avg_speed_knots": avg_spd,
        "congestion_index": index,
        "signal": signal,
        "commodity": port_info["commodity"],
        "lat": port_info["lat"],
        "lon": port_info["lon"],
        "vessels": vessels,
    }


def generate_all():
    results = []
    for name, info in PORTS.items():
        vessels = simulate_vessels(name, info)
        score   = compute_congestion(name, info, vessels)
        results.append(score)
        print(f"  {name:15s} | Index: {score['congestion_index']:5.1f} | "
              f"Signal: {score['signal']:8s} | "
              f"Vessels: {score['total_vessels']} ({score['waiting_vessels']} waiting)")
    return results


def generate_historical(days=30):
    """Generate 30 days of daily congestion scores for trend charts."""
    history = {name: [] for name in PORTS}
    base_date = datetime.now(timezone.utc) - timedelta(days=days)

    for d in range(days):
        dt = base_date + timedelta(days=d)
        random.seed(d * 13)  # Reproducible but varied
        for name, info in PORTS.items():
            jitter = random.gauss(0, 8)
            base = info["base_load"] * 0.7
            # Seasonal pattern — higher load mid-week
            weekday_boost = 5 if dt.weekday() < 5 else -5
            index = round(max(5, min(95, base + jitter + weekday_boost)), 1)
            history[name].append({
                "date": dt.strftime("%Y-%m-%d"),
                "congestion_index": index,
            })

    return history


if __name__ == "__main__":
    import os
    os.makedirs("data", exist_ok=True)
    print("\n=== Generating live snapshot ===")
    live = generate_all()
    with open("data/latest.json", "w") as f:
        json.dump(live, f, indent=2)

    print("\n=== Generating 30-day history ===")
    hist = generate_historical(30)
    with open("data/history.json", "w") as f:
        json.dump(hist, f, indent=2)

    print("\nDone. Saved to data/latest.json + data/history.json")
