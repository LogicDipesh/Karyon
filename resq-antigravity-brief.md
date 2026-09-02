# ResQ — AI-Assisted Disaster Response Coordination (Hackathon Demo Build)

## 0. What this document is
This is the complete build brief for a hackathon demo, not a production system. Build exactly
what's in Section 2. Everything in Section 3 is explicitly OUT of scope — do not build it, do not
scaffold it "for later," do not add TODOs for it in the codebase. If something in Section 2 is
ambiguous, make the simplest possible choice and keep going; do not block on it.

Team context: 5-person team, 2nd-year college students, weak at writing code, building this in a
short hackathon window with AI assistance. Every technical decision below is made to minimize
moving parts and failure surface during a live, judged demo — not to maximize sophistication.

## 1. Positioning (bake this into the UI copy, not just the pitch)
This is a **decision-support tool for disaster-response coordinators**, not an autonomous system
that decides who lives. The dashboard must visibly say, in the UI itself (not just in the pitch):

> "Priority scores are computed from a configurable response policy, not a validated medical or
> scientific ranking. A human coordinator makes the final call."

This line is a defense against the single most likely judge attack ("where did your weights come
from?"). It needs to be on-screen, not something we only say out loud.

## 2. Demo scope — build exactly this

**Scenario:** A single hardcoded disaster zone — "Delhi Flood" — represented as a fixed polygon
(a handful of lat/lng points around a real Delhi area is fine, doesn't need to be precise).

**Actors:**
- 5 pre-scripted citizen users, each with a name, a fixed lat/lng inside the zone, and a short
  emergency description (use the 5 examples already drafted: trapped elderly, injured + stranded,
  pregnant medical emergency, stranded on flooded road, diabetic needing insulin).
- A fixed resource registry: 5 ambulances, 2 NDRF/rescue teams, 2 fire units, 3 hospitals — each
  with a lat/lng and an "available/busy" status.

**Core flow:**
1. Coordinator dashboard loads, shows the 5 incidents as markers on a map and the 5 resources as
   markers.
2. Each incident is scored (Section 6) and ranked in a priority list, highest first.
3. Clicking an incident shows its score breakdown in plain language ("+30 medical emergency, +20
   trapped, +15 severe flooding...").
4. The system assigns each incident the nearest *feasible* available resource (Section 7) and
   draws a line between them on the map.
5. A single "Simulate: Ambulance A02 unavailable" button (or similar — pick ONE simulate event,
   not several) marks a resource unavailable and re-runs allocation. The dashboard highlights what
   changed ("Incident #3 reassigned from A02 to A04").

That's the whole demo. Map + ranked list + explainable score + one dynamic reallocation moment.

## 3. Explicitly out of scope — do not build
- Real GPS/geofence enforcement, login, or user accounts of any kind. Hardcode the 5 users.
- Live NLP/LLM extraction from free-text complaints during the demo. Use pre-structured incident
  data (the "extraction" can be shown as a static before/after slide in the pitch, not live code).
- Real road-network routing, OSRM, or any routing API. Use straight-line (haversine) distance
  only. If you want to gesture at road blockage, do it as a flat distance penalty flag on one
  resource-incident pair, not real GIS analysis.
- A real optimization solver (linear/integer programming). A greedy nearest-feasible assignment
  (Section 7) is enough and is easier to explain to judges than an LP solver you don't fully
  understand.
- Duplicate/spam detection, multi-channel intake (SMS/voice/helpline), multi-disaster/multi-region
  support, real-time resource sync, or any database beyond an in-memory Python structure or a
  single JSON file.
- Any paid API or service requiring a credit card. Map tiles must be free OpenStreetMap tiles via
  Leaflet — no Google Maps API key.

## 4. Tech stack (all free, no signup friction, minimal moving parts)
- **Backend:** Python + FastAPI (or Flask if the team is more comfortable with it). One file per
  concern max — no premature module structure.
- **Data:** In-memory Python dicts/lists seeded from a `data.json` file at startup. No real
  database. This avoids any DB setup failure on demo day.
- **Frontend:** Plain HTML/CSS/JS. Leaflet.js for the map with free OSM tiles (no API key). Keep
  JS dependency count near zero — Leaflet is the only real dependency needed.
- **Hosting for demo:** Run locally on the presenting laptop. Do not depend on live internet
  beyond the OSM tile load (cache/screenshot a fallback in case venue wifi is bad).

## 5. Data model
```
Incident:
  id, name, description, lat, lng,
  medical_emergency: bool, trapped: bool, people_affected: int,
  vulnerable_count: int (elderly/children/disabled),
  severity: 1-5, assigned_resource_id: str | null, priority_score: float

Resource:
  id, type: "ambulance" | "ndrf" | "fire" | "hospital",
  lat, lng, status: "available" | "busy" | "unavailable", capacity: int
```

## 6. Priority scoring — transparent, hardcoded formula
```
priority_score =
    30 * medical_emergency
  + 20 * (vulnerable_count > 0)
  + 20 * trapped
  + 15 * (severity / 5)
  + 10 * min(people_affected, 10) / 10
```
Store each term's contribution alongside the total so the UI can show the breakdown per incident.
Do not present this as scientifically validated — see Section 1.

## 7. Allocation — nearest feasible greedy, not real optimization
```
sort incidents by priority_score, descending
for each incident:
    candidates = resources where status == "available"
                 and type matches incident need
                 (medical_emergency or trapped -> ambulance/ndrf first)
    if candidates is empty: mark incident "unassigned", continue
    pick the candidate with smallest haversine distance to incident
    assign it, mark resource "busy"
```
On simulate (Section 8), re-run this whole loop from scratch on the current incident/resource
state — the dataset is tiny (5 and 5), so a full recompute is instant and far less error-prone
than trying to patch a partial reassignment.

## 8. Simulation / "what-if" feature
Exactly one button: mark one specific resource `unavailable`, then re-run Section 7's algorithm
and diff the old vs new assignments. Show a short "N reassignments" summary and highlight the
changed lines on the map. Do not build multiple simulate scenarios — one clean, reliable one beats
three half-working ones.

## 9. UI / dashboard requirements
- Map (Leaflet, OSM tiles): incident markers (red), resource markers (blue/green/orange by type),
  assignment lines connecting matched pairs.
- Ranked incident list, highest priority first, each row clickable to expand the score breakdown.
- Resource status panel (available/busy count per type).
- The policy disclaimer from Section 1, visible on-screen, not just spoken.
- One simulate button plus a small "what changed" diff panel after it's clicked.

## 10. Suggested folder structure
```
resq/
  backend/
    main.py            # FastAPI app, all routes
    scoring.py          # priority formula
    allocation.py        # greedy nearest-feasible assignment
    data.json            # seeded incidents + resources
  frontend/
    index.html
    app.js               # Leaflet map + dashboard logic
    style.css
```

## 11. Demo script (what the 90-second walkthrough looks like)
1. "This is Delhi during a flood. Five real-time emergency reports have come in." (map loads,
   5 incidents visible)
2. "Our system ranks them — not by who called first, but by an explainable priority policy."
   (click into the top incident, show score breakdown)
3. "Each is matched to the nearest available resource that can actually help." (assignment lines
   drawn)
4. "Now — Ambulance A02 just went out of service." (click simulate) "Watch the dashboard
   recalculate in real time." (reassignment diff shown)
5. Close on the policy disclaimer line and one sentence on what a production version would add
   (real NLP intake, real routing, multi-region) — framed as future work, not something half-built
   in the repo.

## 12. Coding constraints
- Keep functions small and flat — no unnecessary class hierarchies or abstraction layers for a
  demo this size. Plain functions over Python.
- No paid dependencies, no API keys required to run.
- Prioritize "it runs reliably offline on the demo laptop" over "it's architecturally impressive."
  A judge cannot see your architecture; they can see whether the demo breaks.
