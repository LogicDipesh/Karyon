# Karyon — AI-Assisted Disaster Response Coordination

![Python](https://img.shields.io/badge/Python-3.10%2B-3498db) ![FastAPI](https://img.shields.io/badge/FastAPI-2ecc71) ![Gemini](https://img.shields.io/badge/Google%20Gemini-Integrated-8e44ad)

Karyon is an intelligent decision-support dashboard for disaster-response coordinators. It takes incoming emergency incidents, scores and ranks them by priority, and allocates available response resources to each one on a live interactive map — with active assignment route tracking, Gemini AI situational planning, and a bidirectional NLP overwrite engine.

It was designed as an operations center for a **Delhi Flood** scenario, with generic scoring, allocation, and natural language command processing.

> **Important — please read:** Priority scores and AI suggestions are decision-support aids from a configurable response policy. A human coordinator always makes the final call and can overwrite any plan directly through natural language.

---

## Features

- **Active Assignment Routes & Task Completion**
  - Live dashed route paths connect allocated units to their incidents on the map.
  - **Show Active Assignment Routes** toggle switch on the map to switch between full mission overview and selected-only view.
  - **✓ Complete Task** button on incident cards and map popups marks missions completed, immediately frees the allocated unit, and dismisses the route line.
- **AI Tactical Plan & NLP Overwrite Box**
  - **Gemini Response Briefing:** Automatically generates a structured operational briefing (situational assessment, dispatch justification, bottleneck alerts, and directives). Supports free Gemini API keys entered in UI or via `GEMINI_API_KEY`.
  - **NLP Overwrite Engine:** Coordinators can overwrite the plan or issue natural language commands (e.g., *"Move Fatima to priority #1"*, *"Assign N01 to Fatima"*, *"Complete task for Ramesh"*, *"Mark A02 unavailable"*).
  - Uses Gemini structured JSON parsing with a deterministic local regex fallback for offline/instant execution.
- **Interactive map** (Leaflet + OpenStreetMap tiles, no API key required for base map)
  - Red incident markers, colored resource markers by type, flood-zone polygon overlay.
  - Click any marker or panel card to inspect details and highlight route waypoints.
- **Priority Incidents panel** — incidents ranked highest-first, each expandable to show score breakdowns, assigned units, and task completion controls.
- **Resource Status drill-down** — live available / busy / down counts per unit type with drill-down details.
- **Simulate / Reset** — interactive resource picker to simulate units going offline, re-run allocation, and diff state changes.

---

## Tech Stack

| Layer | Choice | Notes |
|---|---|---|
| Backend | Python + FastAPI | Single-server app, in-memory state |
| AI / NLP | Google Gemini + Rule Engine | Structured plan generation & command parsing |
| Data | JSON seed file | `backend/data.json`, no database required |
| Frontend | Plain HTML / CSS / JS | Dark theme, responsive operations console |
| Map | Leaflet 1.9.4 + OSM tiles | Only external CDN (free, no key) |
| Distance | Haversine (straight-line) + Bezier waypoints | Client-side visual paths, no routing API needed |

---

## Project Structure

```
karyon/
├── backend/
│   ├── main.py            # FastAPI app: API routes + static file serving + entry point
│   ├── ai_service.py      # Gemini tactical planning & NLP overwrite engine
│   ├── scoring.py         # Priority scoring formula
│   ├── allocation.py      # Greedy nearest-feasible resource allocation
│   └── data.json          # Seed data: incidents, resources, zone polygon
├── frontend/
│   ├── index.html         # Single-page dashboard shell
│   ├── app.js             # Map, active routes, task completion, AI plan & overwrite
│   └── style.css          # Dark operations theme, AI console, route controls
└── requirements.txt       # fastapi, uvicorn[standard]
```

---

## Getting Started

### Prerequisites

- **Python 3.10+**
- Internet access (to load Leaflet and OpenStreetMap tiles in the browser)

### 1. Clone & install

```bash
git clone <your-repo-url>
cd resq

# create and activate a virtual environment
python -m venv .venv

# Windows (PowerShell)
.venv\Scripts\Activate.ps1
# macOS / Linux
source .venv/bin/activate

# install dependencies
pip install -r requirements.txt
```

### 2. Start the server

```bash
python backend/main.py
```

From the project root, with the virtual environment active. You should see:

```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

> The app binds to all interfaces (`0.0.0.0:8000`). Open it in your browser at
> **http://127.0.0.1:8000**. (You cannot browse to `0.0.0.0` directly — that's the *bind*
> address, not a URL to visit.)

### 3. Open the dashboard

Navigate to **http://127.0.0.1:8000** in any browser.

> **Single-instance guard:** The app refuses to start a second server if port `8000` is already in
> use, so you can't accidentally end up with two ResQ instances fighting over the same port. Stop the
> existing one (Ctrl+C) before starting another.

---

## Using the Dashboard

### Map
- **Red circles** are incidents; **blue/green/orange/white** circles are ambulances / NDRF / fire /
  hospitals. A **grey, faded** resource is *unavailable*.
- Click any marker for a popup.
- **Click an incident or resource** — its card, a panel row, or a map marker — to highlight it and
  draw a **dashed route path** to its allocated partner. The path bends through two intermediate
  waypoints (computed client-side, no routing API) and is colored by the resource type.
- **Click the same item again**, or click an empty map area, to clear the route. Unassigned
  incidents highlight without a path.

### Priority Incidents
- Incidents are sorted by priority score, highest first.
- **Click a card header** to expand its score breakdown (each term with its `+value`), the **Total**,
  and the **assigned resource + distance**.
- Clicking a card also highlights that incident's marker on the map and draws the route path to its
  assigned resource; click again to clear.

### Resource Status (drill-down)
- Four rows — Ambulances, NDRF Teams, Fire Units, Hospitals — each with live counts.
- **Click a row** to expand a per-unit drill-down:
  - *Available* unit → shows `Available`
  - *Busy* unit → shows the incident it's assigned to and distance, e.g. `A02 → Fatima Begum (Pregnant, Medical), 0.66 km`
  - *Unavailable* (after simulate) → shows `Unavailable`
- **Click a busy unit** to highlight that incident's card and map marker and draw the dispatch route.

### Simulate & Reset
- Click **Simulate** to open the resource picker. The picker groups every dispatchable resource
  by category (Ambulances, NDRF Teams, Fire Units) — Hospitals are shown for reference but cannot
  be selected.
- **Click individual resource buttons** to mark them unavailable (red tint). Click again to deselect.
  Pre-marked unavailable units from a previous run stay selected on re-open.
- Click **Run Allocation** to POST the selection to `/api/allocate` and re-run the greedy allocator.
  The dashboard highlights reassigned incidents (amber) and shows a diff like
  `↻ Fatima Begum (Pregnant, Medical): A02 → N01`.
- Click **Clear** to deselect everything, or **Cancel** to close the picker without running.
- An empty selection is allowed: it re-runs the allocator with all resources available (useful to
  re-diff after external state changes).
- **Reset** reloads the seed data and restores the initial state (re-enables Simulate and clears
  the changes display).

---

## API Reference

Base URL: `http://127.0.0.1:8000`

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/state` | Full current state: incidents (scored + assigned), resources (statuses), zone polygon, assignments |
| `POST` | `/api/simulate` | **Backward-compatible.** Marks Ambulance A02 unavailable, re-runs allocation, returns `{ state, changes, unavailable_resource_ids }` |
| `POST` | `/api/allocate` | Mark any set of resources unavailable, re-run allocation. Body: `{"unavailable_resource_ids": ["A02", "N01"]}`. Returns `{ state, changes, unavailable_resource_ids }`. Hospital IDs in the list are ignored |
| `POST` | `/api/reset` | Re-seed from `data.json`, recompute everything, return fresh `state` |

Example:

```bash
curl http://127.0.0.1:8000/api/state
curl -X POST http://127.0.0.1:8000/api/simulate
curl -X POST -H "Content-Type: application/json" \
     -d '{"unavailable_resource_ids":["A02","N01","F01"]}' \
     http://127.0.0.1:8000/api/allocate
curl -X POST http://127.0.0.1:8000/api/reset
```

---

## How It Works

### Priority scoring (`backend/scoring.py`)

Each incident's `priority_score` is a transparent weighted sum:

```
priority_score =
    30 * medical_emergency
  + 20 * (vulnerable_count > 0)
  + 20 * trapped
  + 15 * (severity / 5)
  + 10 * min(people_affected, 10) / 10
```

The per-term breakdown is stored alongside the total so the UI can explain every score.

### Allocation (`backend/allocation.py`)

A greedy nearest-feasible assignment:

1. Sort incidents by priority score, descending.
2. For each incident, find **available, non-hospital** resources (preferring
   ambulance/NDRF for medical or trapped incidents, falling back to any).
3. Assign the **closest** (smallest haversine distance) candidate and mark it `busy`.
4. If none is available, the incident stays unassigned.

Simulate and reset **re-run this whole loop from scratch** on the current dataset.

---

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `ModuleNotFoundError: fastapi` | Venv not activated or deps not installed — run `pip install -r requirements.txt`. |
| `Port 8000 is already in use` | Another ResQ instance is running — stop it, or launch on a different port. |
| Map tiles don't load | Offline/blocked network. Pre-load the page once while online so tiles cache. |
| Leaflet error `Cannot read properties of undefined (reading 'min')` | This was a known bug, now fixed. Make sure you have the latest `app.js` (it sets an initial map view before rendering layers). |
| Nothing loads and panels say "Loading…" forever | Hard-refresh (`Ctrl+Shift+R`). If a browser extension injects a strict CSP, try an incognito window or disable the extension. |
| Clicking incidents doesn't draw assignment routes | Browser is serving a cached old `app.js` — hard-refresh (`Ctrl+Shift+R`) or open in an incognito window once. |

---

## License

This project is provided as a demo/hackathon build. You are free to use and modify it for your own
projects. If you distribute it, include attribution back to the original build.

(Replace with your chosen license, e.g. `MIT`, if you want one.)
