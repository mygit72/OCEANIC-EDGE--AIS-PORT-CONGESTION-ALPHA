"""
Oceanic Edge — FastAPI Backend
Run: uvicorn app:api --host 0.0.0.0 --port 8000 --reload
Docs: http://localhost:8000/docs
"""

import json
import os
from datetime import datetime, timezone
from typing import Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ── Setup ──────────────────────────────────────────────────────────────────────
api = FastAPI(
    title="Oceanic Edge API",
    description="AIS & Port Congestion Alpha — Real-time maritime intelligence",
    version="1.0.0",
)

api.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

def load_json(filename: str) -> dict:
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"{filename} not found")
    with open(path) as f:
        return json.load(f)


# ── Models ─────────────────────────────────────────────────────────────────────
class AlertConfig(BaseModel):
    critical_threshold: float = 75.0
    high_threshold: float = 50.0
    moderate_threshold: float = 25.0
    mute_moderate: bool = False


# ── Routes ─────────────────────────────────────────────────────────────────────

@api.get("/health")
def health():
    """Uptime check."""
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@api.get("/api/congestion")
def get_all_congestion():
    """All port congestion scores (latest snapshot)."""
    data = load_json("latest.json")
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ports": [{k: v for k, v in p.items() if k != "vessels"} for p in data]
    }


@api.get("/api/congestion/{port}")
def get_port_congestion(port: str):
    """Single port congestion score."""
    data = load_json("latest.json")
    match = next((p for p in data if p["port"].lower() == port.lower()), None)
    if not match:
        raise HTTPException(status_code=404, detail=f"Port '{port}' not found")
    return {k: v for k, v in match.items() if k != "vessels"}


@api.get("/api/vessels/{port}")
def get_vessels(port: str, limit: int = Query(50, ge=1, le=500)):
    """Vessel list for a port."""
    data = load_json("latest.json")
    match = next((p for p in data if p["port"].lower() == port.lower()), None)
    if not match:
        raise HTTPException(status_code=404, detail=f"Port '{port}' not found")
    vessels = match.get("vessels", [])
    return {
        "port": match["port"],
        "total": len(vessels),
        "vessels": vessels[:limit]
    }


@api.get("/api/history/{port}")
def get_history(port: str):
    """30-day congestion history for a port."""
    data = load_json("history.json")
    if port not in data:
        raise HTTPException(status_code=404, detail=f"Port '{port}' not found")
    return {"port": port, "history": data[port]}


@api.get("/api/backtest")
def get_backtest():
    """Backtest P&L results."""
    data = load_json("alpha.json")
    return {"backtest": data.get("backtest", []), "correlations": data.get("correlations", {})}


@api.get("/api/ml")
def get_ml_results():
    """ML model predictions and metrics."""
    data = load_json("alpha.json")
    return data.get("ml", {})


@api.get("/api/commodities")
def get_commodities():
    """Commodity price data."""
    data = load_json("alpha.json")
    return data.get("commodities", {})


@api.post("/api/alerts/config")
def update_alert_config(config: AlertConfig):
    """Update alert thresholds (stored in memory for demo)."""
    return {
        "status": "updated",
        "config": config.dict(),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@api.get("/api/alerts/check")
def check_alerts(
    critical_threshold: float = 75.0,
    high_threshold: float = 50.0,
    moderate_threshold: float = 25.0,
):
    """Check which ports are currently above alert thresholds."""
    data = load_json("latest.json")
    alerts = []
    for p in data:
        idx = p["congestion_index"]
        if idx >= critical_threshold:
            level = "CRITICAL"
        elif idx >= high_threshold:
            level = "HIGH"
        elif idx >= moderate_threshold:
            level = "MODERATE"
        else:
            continue
        alerts.append({
            "port": p["port"],
            "level": level,
            "congestion_index": idx,
            "commodity": p["commodity"],
            "waiting_vessels": p["waiting_vessels"],
            "tankers_waiting": p["tankers_waiting"],
        })
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "alert_count": len(alerts),
        "alerts": sorted(alerts, key=lambda x: x["congestion_index"], reverse=True)
    }


# ── Static files (serve dashboard) ────────────────────────────────────────────
dashboard_path = os.path.join(os.path.dirname(__file__), "dashboard")
if os.path.exists(dashboard_path):
    api.mount("/", StaticFiles(directory=dashboard_path, html=True), name="dashboard")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:api", host="0.0.0.0", port=8000, reload=True)
