# ResQ — Implementation Plan

## Goal

Build a single-page hackathon demo for AI-assisted disaster response coordination, following [resq-antigravity-brief.md](file:///e:/ResQ/resq-antigravity-brief.md) exactly. The result is a FastAPI backend serving a Leaflet-based dashboard that shows 5 hardcoded incidents scored, ranked, and allocated to available resources via a greedy algorithm, with one simulate button to demo dynamic reallocation.

---

## Design Decisions (Resolved via Interview)

| Decision | Choice |
|---|---|
| Backend framework | FastAPI |
| Frontend serving | Via FastAPI `StaticFiles` mount — single `python main.py` |
| Simulate target | Fixed: Ambulance A02 (hardcoded) |
| Computation | Server-side Python, fetched via REST |
| Type matching | Inferred from incident flags; soft preference (ambulance/NDRF first for medical/trapped, fallback to any) |
| Layout | Side-by-side: map ~60% left, panels ~40% right |
| Visual style | Dark theme, flat solid panels, colored severity accents |
| Map markers | `L.circleMarker` — zero extra dependencies |
| Reset | Full re-seed from `data.json` into memory |
| Hospitals | Static map markers + status panel only, excluded from allocation |
| Score breakdown | Inline expand/collapse in the incident list |
| Map-list sync | Highlight/pulse marker on click; `fitBounds` on load, no panning |
| Diff display | Highlighted rows in incident list + updated assignment lines on map |
| Disclaimer | In the header/toolbar area of the dashboard |

---

## Proposed Changes

### Folder Structure

```
e:\ResQ\
  resq-antigravity-brief.md    # (existing, read-only)
  backend\
    main.py                     # FastAPI app, all routes, static file mount
    scoring.py                  # Priority formula (Section 6)
    allocation.py               # Greedy nearest-feasible assignment (Section 7)
    data.json                   # Seeded incidents + resources (Section 5)
  frontend\
    index.html                  # Single-page dashboard
    app.js                      # Leaflet map + dashboard logic
    style.css                   # Dark theme, flat panels, layout
  requirements.txt              # fastapi, uvicorn
```

This matches Section 10 exactly, with `requirements.txt` added at the root for dependency management.

---

### Backend

#### [NEW] [data.json](file:///e:/ResQ/backend/data.json)

Seed data containing:
- **5 incidents** (Section 2): trapped elderly, injured & stranded, pregnant medical emergency, stranded on flooded road, diabetic needing insulin. Each has `id`, `name`, `description`, `lat`, `lng`, `medical_emergency`, `trapped`, `people_affected`, `vulnerable_count`, `severity`. Located at real-ish Delhi lat/lngs inside a rough flood zone polygon.
- **12 resources** (Section 2): 5 ambulances (A01–A05), 2 NDRF teams (N01–N02), 2 fire units (F01–F02), 3 hospitals (H01–H03). Each has `id`, `type`, `lat`, `lng`, `status` (all start "available"), `capacity`.
- **1 zone polygon**: A handful of lat/lng points roughly bounding a Delhi area (for map display only — no geofence enforcement per Section 3).

All lat/lngs will be placed in the central/east Delhi area around the Yamuna floodplain for visual realism.

---

#### [NEW] [scoring.py](file:///e:/ResQ/backend/scoring.py)

Single function: `compute_priority(incident) -> dict`

Implements Section 6 formula exactly:
```python
priority_score =
    30 * medical_emergency
  + 20 * (vulnerable_count > 0)
  + 20 * trapped
  + 15 * (severity / 5)
  + 10 * min(people_affected, 10) / 10
```

Returns a dict with:
- `priority_score`: float (the total)
- `breakdown`: list of `{label: str, value: float}` for each non-zero term (e.g. `{label: "Medical emergency", value: 30}`)

This breakdown powers the UI's inline score expansion. No external dependencies.

---

#### [NEW] [allocation.py](file:///e:/ResQ/backend/allocation.py)

Two functions:

1. **`haversine(lat1, lng1, lat2, lng2) -> float`** — straight-line distance in km. No routing API (Section 3 forbids OSRM/routing).

2. **`allocate(incidents, resources) -> list[dict]`** — implements Section 7:
   - Sort incidents by `priority_score` descending.
   - For each incident, find candidate resources where `status == "available"` and type is not `"hospital"` (hospitals excluded from allocation per design decision).
   - Soft preference: if incident has `medical_emergency` or `trapped`, prefer `"ambulance"` or `"ndrf"` type candidates. If none available, fall back to any available non-hospital resource.
   - Pick candidate with smallest haversine distance.
   - Mark chosen resource as `"busy"`, record the assignment.
   - If no candidates remain, mark incident `"unassigned"`.
   - Returns the full list of assignments: `{incident_id, resource_id, distance_km}` plus each incident and resource with updated state.

On simulate/reset, this is called from scratch on the full dataset (Section 7 note: "re-run this whole loop from scratch").

---

#### [NEW] [main.py](file:///e:/ResQ/backend/main.py)

FastAPI application with:

**Startup:**
- Load `data.json` into in-memory Python dicts/lists.
- Run `compute_priority()` on each incident, attach scores + breakdowns.
- Run `allocate()` to produce initial assignments.
- Store everything in module-level variables (no database — Section 3/4).

**Routes:**

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/state` | Returns full current state: incidents (with scores, breakdowns, assignments), resources (with statuses), zone polygon, assignments list. Single endpoint — the dataset is tiny. |
| `POST` | `/api/simulate` | Marks Ambulance A02 as `"unavailable"`, re-runs `allocate()` from scratch, diffs old vs new assignments, returns the new state + a `changes` list (which incidents got reassigned and from/to which resource). |
| `POST` | `/api/reset` | Re-loads `data.json` from disk, re-computes scores, re-runs allocation. Returns fresh state. Full re-seed. |

**Static files:**
- Mount `frontend/` directory at `/` using `StaticFiles` so `index.html` is served at the root.

**CORS:** Not needed (same origin via StaticFiles mount).

**Server:** `uvicorn.run(app, host="0.0.0.0", port=8000)` in the `if __name__ == "__main__"` block for one-command startup.

---

### Frontend

#### [NEW] [index.html](file:///e:/ResQ/frontend/index.html)

Single-page HTML:
- Loads Leaflet CSS/JS from CDN (`unpkg.com/leaflet@1.9`).
- Loads `style.css` and `app.js`.
- Semantic structure:
  - `<header>`: "ResQ — Disaster Response Coordinator" title + the Section 1 policy disclaimer in muted text.
  - `<main>`: Two-column flex layout:
    - Left (60%): `<div id="map">` for Leaflet.
    - Right (40%): Scrollable panel containing:
      - Ranked incident list (`<div id="incident-list">`)
      - Resource status panel (`<div id="resource-status">`)
      - Simulate button + reset button (`<div id="simulate-panel">`)
- Proper `<title>`, `<meta>` description, semantic HTML.
- No additional JS dependencies beyond Leaflet.

---

#### [NEW] [style.css](file:///e:/ResQ/frontend/style.css)

Dark theme design system:
- **Palette:** Deep navy/charcoal background (`#0f1923` base), with solid lighter card surfaces (`#1a2733`).
- **Accent colors:** Red/crimson for incidents, teal/green for available resources, orange for busy, grey for unavailable, white/blue for hospitals.
- **Panels:** Flat solid backgrounds with subtle 1px borders — no transparency, no `backdrop-filter`, no glassmorphism.
- **Typography:** System font stack (`-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen, Ubuntu, Cantarell, sans-serif`). No external font CDN — Leaflet is the only dependency (Section 4).
- **Layout:** Flexbox-based side-by-side, responsive enough for a laptop demo screen.
- **Incident list:** Card-style rows with rank number, name, score badge. Expandable breakdown section with smooth CSS transition.
- **Highlight class:** A glowing border / background pulse for reassigned incidents post-simulate.
- **Buttons:** Styled simulate button (amber/warning color) and reset button (muted/secondary).
- **Map container:** Full height of the left column, rounded corners.

---

#### [NEW] [app.js](file:///e:/ResQ/frontend/app.js)

All frontend logic in one file:

**On load:**
1. `fetch('/api/state')` to get initial data.
2. Initialize Leaflet map with OSM tiles (`https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png`).
3. Draw the flood zone polygon (semi-transparent blue/red fill).
4. Place incident markers (red `L.circleMarker`) with popups showing name + description.
5. Place resource markers (colored `L.circleMarker` by type: blue=ambulance, green=NDRF, orange=fire, white=hospital) with popups showing id + type + status.
6. Draw assignment lines (`L.polyline`, dashed, colored) between each assigned incident-resource pair.
7. `fitBounds()` to show all markers.
8. Render the ranked incident list in the right panel (sorted by `priority_score` desc). Each row shows rank, name, score. Clicking expands inline to show the breakdown terms.
9. Render resource status panel (counts: "Ambulances: 3 available / 2 busy" etc.).
10. Wire up simulate and reset buttons.

**Incident list click handler:**
- Toggle inline expand/collapse for score breakdown.
- Highlight/pulse the corresponding marker on the map (add a CSS class or change marker style, then revert after a short timeout or on next click).

**Simulate button click:**
1. `POST /api/simulate`.
2. Receive new state + changes list.
3. Re-render map: update marker colors for status changes, redraw assignment lines.
4. In the incident list, highlight rows that were reassigned (e.g., amber border + "Reassigned: A02 → A04" label).
5. Disable the simulate button (it's a one-shot action). Enable the reset button.

**Reset button click:**
1. `POST /api/reset`.
2. Re-render everything from fresh state.
3. Re-enable simulate button, clear all highlights.

---

### Root Files

#### [NEW] [requirements.txt](file:///e:/ResQ/requirements.txt)

```
fastapi
uvicorn[standard]
```

Two dependencies only. Both free, no API keys (Section 3/12 compliance).

---

## Section 3 Cross-Check (Out-of-Scope Guardrails)

| Forbidden item (Section 3) | Status |
|---|---|
| Real GPS/geofence, login, user accounts | ✅ Not built. Users are hardcoded in `data.json`. Zone polygon is display-only. |
| Live NLP/LLM extraction | ✅ Not built. All incident data is pre-structured. |
| Real road-network routing, OSRM, routing API | ✅ Not built. Using haversine distance only. |
| Real optimization solver (LP/IP) | ✅ Not built. Using greedy nearest-feasible. |
| Duplicate/spam detection, multi-channel, multi-disaster, real-time sync, real database | ✅ Not built. Single disaster, in-memory Python dicts, single JSON seed file. |
| Paid API or service requiring credit card | ✅ Not used. Map tiles are free OSM via Leaflet. System font stack — no CDN. |
| Multiple simulate scenarios | ✅ Not built. Exactly one simulate button (A02 unavailable). |

> [!IMPORTANT]
> The only external CDN dependencies are:
> - Leaflet JS/CSS from `unpkg.com` (free, no key)
> - OSM tiles — free, no key
>
> Typography uses a system font stack — no Google Fonts or any other external font CDN. Leaflet is the sole JS dependency (Section 4 compliance).
>
> For offline demo resilience (Section 4 note about venue WiFi), the presenter should pre-load the page once before the demo so tiles are browser-cached. A full offline tile solution is out of scope for this build.

---

## Verification Plan

### Automated
- `pip install -r requirements.txt` succeeds.
- `python backend/main.py` starts the server without errors.
- `GET /api/state` returns valid JSON with 5 incidents (scored, ranked) and 12 resources (5 assigned, rest available/hospital).
- `POST /api/simulate` returns state with A02 unavailable and a non-empty `changes` list.
- `POST /api/reset` returns state identical to initial load.

### Manual (Browser)
- Dashboard loads at `http://localhost:8000` with map + panels.
- Map shows Delhi area with zone polygon, 5 red incident markers, 12 resource markers, assignment lines.
- Incident list is ranked highest-first; clicking expands score breakdown.
- Clicking an incident highlights its map marker.
- Simulate button triggers reallocation; changed incidents are highlighted in the list and map lines update.
- Reset button restores initial state.
- Policy disclaimer is visible in the header.
