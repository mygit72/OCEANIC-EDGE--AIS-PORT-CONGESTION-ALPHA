# 🌊 Oceanic Edge — AIS & Port Congestion Alpha

An end-to-end alternative data platform that ingests real-time AIS (Automatic Identification System) vessel data to compute port congestion indices across 6 global ports, generate commodity price signals, and run a backtested trading strategy.

Built as a resume/portfolio project demonstrating skills in: **data engineering, financial signal research, ML modelling, REST API development, and production deployment.**

---

## Live Demo

Open `dashboard/index.html` directly in your browser — no server needed.

Or run with FastAPI:
```bash
pip install -r requirements.txt
uvicorn app:api --reload
# → http://localhost:8000
```

---

## What It Does

### 1. Data Pipeline (`pipeline/`)
- Connects to the **MarineTraffic AIS API** to fetch real-time vessel positions around 6 major ports
- Computes a **Congestion Index (0–100)** per port based on: % of vessels waiting/anchored, average fleet speed, tanker count
- Classifies signal as LOW / MODERATE / HIGH / CRITICAL
- Falls back to realistic simulation when live API is unavailable

**Ports monitored:**
| Port | Commodity | Region |
|------|-----------|--------|
| Houston | Crude Oil | USA |
| Rotterdam | Mixed / Container | Europe |
| Singapore | Bunker / Container | Asia |
| Qingdao | Iron Ore / Coal | China |
| Fujairah | Crude Oil | Middle East |
| Los Angeles | Container | USA |

### 2. Alpha Research (`data/alpha.json`)
- **Lag-7 correlation**: How well does today's congestion predict commodity prices 7 days ahead?
  - Fujairah congestion vs WTI Crude: **r = -0.38**
  - Qingdao congestion vs Iron Ore: **r = -0.35**
- **Backtest**: Long crude when avg(Houston + Fujairah) congestion > 45 → **+21% simulated P&L over 30 days**

### 3. ML Model (XGBoost)
- **Target**: WTI Crude % price change over next 7 days
- **Features**: 6 AIS-derived congestion features (port indices, tanker counts, fleet speed)
- **Results**: R² = 0.31, Direction Accuracy = 50%, walk-forward cross-validation
- Generates LONG / SHORT / FLAT signals with confidence scores

### 4. Dashboard (`dashboard/index.html`)
Three-tab interactive HTML dashboard:
- **Dashboard**: Live port cards, congestion bar chart, vessel composition donut, 30-day trend, vessel-level table, real-time alert system with configurable thresholds
- **Alpha / Backtest**: Commodity price charts, lag correlation table, cumulative P&L chart, strategy logic
- **ML Model**: Predicted vs actual chart, feature importance, scatter plot, signal log

### 5. REST API (`app.py`)
FastAPI backend with auto-generated docs at `/docs`:

| Endpoint | Description |
|----------|-------------|
| `GET /api/congestion` | All port scores |
| `GET /api/congestion/{port}` | Single port |
| `GET /api/vessels/{port}` | Vessel list |
| `GET /api/history/{port}` | 30-day history |
| `GET /api/backtest` | P&L results |
| `GET /api/ml` | Model metrics & predictions |
| `GET /api/commodities` | Commodity price data |
| `GET /api/alerts/check` | Active alerts |
| `POST /api/alerts/config` | Update thresholds |

---

## Project Structure

```
oceanic-edge/
├── pipeline/
│   ├── ais_pipeline.py      # Live AIS data ingestion + congestion engine
│   └── simulator.py         # Realistic data simulator (fallback)
├── data/
│   ├── latest.json          # Current congestion snapshot
│   ├── history.json         # 30-day historical scores
│   └── alpha.json           # Commodity prices, correlations, backtest, ML
├── dashboard/
│   └── index.html           # Full interactive dashboard (self-contained)
├── .github/
│   └── workflows/
│       └── pipeline.yml     # Hourly GitHub Actions cron job
├── app.py                   # FastAPI REST API
├── Dockerfile               # Production container
├── requirements.txt
└── README.md
```

---

## Quick Start

### Option 1 — Just open the dashboard
```bash
open dashboard/index.html
```

### Option 2 — Run with live API
```bash
pip install -r requirements.txt
python pipeline/ais_pipeline.py YOUR_MARINETRAFFIC_API_KEY
uvicorn app:api --reload
```

### Option 3 — Docker
```bash
docker build -t oceanic-edge .
docker run -p 8000:8000 oceanic-edge
```

### Option 4 — Deploy to Railway (free)
```bash
railway login
railway init
railway up
# Your app is live at https://oceanic-edge.up.railway.app
```

---

## API Key

Get a MarineTraffic API key at [marinetraffic.com/en/ais-api-services](https://www.marinetraffic.com/en/ais-api-services).

The free tier covers single-vessel lookups. Area vessel export (PS06) and port congestion (VI06) require a paid tier. The simulator provides realistic data in the meantime.

Set your key as an environment variable:
```bash
export MARINETRAFFIC_API_KEY=your_key_here
```

Or add it to a `.env` file:
```
MARINETRAFFIC_API_KEY=your_key_here
```

---

## Congestion Index Formula

```
wait_ratio    = waiting_vessels / total_vessels
speed_penalty = max(0, (5 - avg_speed_knots) / 5) × 20   # up to +20 if avg speed < 5 kn
tanker_boost  = min(20, tankers_waiting × 2)               # up to +20

congestion_index = min(100, wait_ratio × 60 + speed_penalty + tanker_boost)
```

| Score | Signal | Interpretation |
|-------|--------|----------------|
| 0–24 | LOW | Normal port activity |
| 25–49 | MODERATE | Elevated congestion, monitor |
| 50–74 | HIGH | Significant backlog, consider long position |
| 75–100 | CRITICAL | Severe congestion, strong signal |

---

## ML Model Details

**Algorithm**: XGBoost Regressor  
**Features (6)**:
1. Houston Congestion Index (importance: 31%)
2. Fujairah Tankers Waiting (24%)
3. Avg Fleet Speed — 7-day lag (18%)
4. Singapore Congestion Index (13%)
5. Week-on-week Δ Congestion (9%)
6. Rotterdam Cargo Count (5%)

**Validation**: Walk-forward cross-validation (no lookahead bias), rolling 60-day train window, 7-day test window.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Data Ingestion | Python, Requests, MarineTraffic API |
| Geospatial | Haversine formula, port geo-fencing |
| Data Storage | JSON (demo), PostgreSQL + TimescaleDB (production) |
| API | FastAPI, Uvicorn, Pydantic |
| ML | XGBoost, pandas, numpy |
| Frontend | Vanilla JS, Chart.js 4.4 |
| Deployment | Docker, Railway, GitHub Actions |

---
