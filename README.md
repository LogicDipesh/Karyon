# ResQ — AI-Assisted Disaster Response Coordination

![Python](https://img.shields.io/badge/Python-3.10%2B-3498db) ![FastAPI](https://img.shields.io/badge/FastAPI-2ecc71)

ResQ is a decision-support dashboard for disaster-response coordinators. It takes a set of
incoming emergency incidents, scores and ranks them by priority, and allocates available response
resources to each one — all on a live interactive map.

It was designed as a **hackathon demo** for a hardcoded **Delhi Flood** scenario, but its scoring
and allocation logic are generic and easy to re-seed with new data.

> **Important — please read:** Priority scores are computed from a configurable response policy,
> **not** a validated medical or scientific ranking. A human coordinator always makes the final call.

---

## Features

- **Interactive map** (Leaflet + OpenStreetMap tiles, no API key)
  - Red incident markers, colored resource markers by type, flood-zone polygon overlay
  - **Click-to-highlight assignment routes** — click an incident or resource to draw the dashed
    route path to its allocated partner (colored by resource type)
  - Click a marker for a popup with details
- **Priority Incidents panel** — incidents ranked highest-first, each expandable to show a plain-language
  score breakdown and its assigned resource
- **Resource Status panel** — live available / busy / unavailable counts per resource type, with a
  click-to-expand **drill-down** listing every individual unit and, for busy units, which incident they're
  assigned to and the dispatch distance
- **Simulate / Reset** — open a resource picker to mark any combination of ambulances, NDRF teams,
  or fire units as unavailable, re-run allocation, and diff what changed. Reset restores the
  initial state
- **Explanable, transparent logic** — scoring formula and greedy allocation are simple, in-code, and
  visible in the UI

---

## Tech Stack

| Layer | Choice | Notes |
|---|---|---|
| Backend | Python + FastAPI | Single-file app, in-memory state |
| Data | JSON seed file | `backend/data.json`, no database |
| Frontend | Plain HTML / CSS / JS | Dark theme, flat panels |
| Map | Leaflet 1.9.4 + OSM tiles | Only external CDN (free, no key) |
| Distance | Haversine (straight-line); visual waypoints are client-side math | No routing/GSM API |

**Only two Python dependencies:** `fastapi` and `uvicorn[standard]`.

---

## Project Structure

```
resq/
├── backend/
│   ├── main.py            # FastAPI app: routes + static file serving + entry point
│   ├── scoring.py         # Priority scoring formula
│   ├── allocation.py      # Greedy nearest-feasible resource allocation
│   └── data.json          # Seed data: incidents, resources, zone polygon
├── frontend/
│   ├── index.html         # Single-page dashboard shell
│   ├── app.js             # Map + panels, simulate/reset, click-to-highlight routes
│   └── style.css          # Dark theme, flat panels, layout
├── requirements.txt       # fastapi, uvicorn[standard]
└── plans/
    └── allocation_deallocation.md # Dynamic resource allocation plan
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
| `PATCH` | `/api/resources/{id}` | Change resource availability. Body: `{"status": "available" \| "unavailable"}` |
| `POST` | `/api/deallocate/{incident_id}` | Free an incident's assigned resource and re-run allocation |
| `POST` | `/api/allocate` | Mark any set of resources unavailable, re-run allocation. Body: `{"unavailable_resource_ids": ["A02", "N01"]}` |
| `POST` | `/api/simulate` | **Backward-compatible.** Marks Ambulance A02 unavailable, re-runs allocation |
| `POST` | `/api/confirm` | Batch-confirm proposed allocations |
| `POST | `/api/override` | Manually override incident assignment |
| `POST` | `/api/reset` | Re-seed from `data.json`, clear `state.json`, return fresh state |

Example:

```bash
curl http://127.0.0.1:8000/api/state
curl -X PATCH -H "Content-Type: application/json" \
     -d '{"status":"unavailable"}' \
     http://127.0.0.1:8000/api/resources/A02
curl -X POST http://127.0.0.1:8000/api/deallocate/INC-001
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
