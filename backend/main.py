"""ResQ — FastAPI backend (all routes in one file, per Section 10)."""

import json
from pathlib import Path
import sys

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
import uvicorn

# ---------------------------------------------------------------------------
# Paths & sys.path setup
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

DATA_FILE = BASE_DIR / "data.json"
FRONTEND_DIR = BASE_DIR.parent / "frontend"

from scoring import compute_priority
from allocation import propose_assignments

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="ResQ — Disaster Response Coordinator")

# ---------------------------------------------------------------------------
# In-memory state (no database — Section 3/4)
# ---------------------------------------------------------------------------
state = {
    "incidents": [],
    "resources": [],
    "zone_polygon": [],
    "assignments": [],
    "overrides": [],
}


STATE_FILE = BASE_DIR / "state.json"


def save_state():
    """Write current state to state.json atomically."""
    temp_file = BASE_DIR / "state.json.tmp"
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    temp_file.replace(STATE_FILE)


def load_state_file():
    """Load state from state.json if present."""
    global state
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                state.clear()
                state.update(loaded)
                return True
        except Exception:
            pass
    return False


def load_and_compute():
    """Load data.json, compute priority scores, run pending proposal."""
    with open(DATA_FILE, encoding="utf-8") as f:
        raw = json.load(f)

    incidents = raw["incidents"]
    resources = raw["resources"]
    zone_polygon = raw["zone_polygon"]

    for inc in incidents:
        result = compute_priority(inc)
        inc["priority_score"] = result["priority_score"]
        inc["breakdown"] = result["breakdown"]
        inc["assigned_resource_id"] = None

    for res in resources:
        if res["type"] != "hospital":
            res["status"] = "available"

    proposals = propose_assignments(incidents, resources)

    assignments = []
    for p in proposals:
        if p["winner_resource_id"] is None:
            continue
        assignments.append({
            "incident_id": p["incident_id"],
            "resource_id": p["winner_resource_id"],
            "distance_km": p["winner_distance_km"],
            "status": "pending",
            "candidates": p["candidates"],
            "overridden": False,
        })

    state["incidents"] = incidents
    state["resources"] = resources
    state["zone_polygon"] = zone_polygon
    state["assignments"] = assignments
    state["overrides"] = []


# Initial load at startup (loads persisted state.json if available)
if not load_state_file():
    load_and_compute()
    save_state()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resource_lookup():
    return {r["id"]: r for r in state["resources"]}


def _incident_lookup():
    return {i["id"]: i for i in state["incidents"]}


def _assignment_for(incident_id):
    for a in state["assignments"]:
        if a["incident_id"] == incident_id:
            return a
    return None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/api/state")
def get_state():
    """Return full current state: incidents, resources, zone, assignments, overrides."""
    return state


@app.post("/api/simulate")
def simulate():
    """Backward-compatible hardcoded sim: marks A02 unavailable, re-proposes."""
    return _run_proposal_with_unavailable(["A02"])


@app.post("/api/allocate")
async def allocate_endpoint(request: Request):
    """Mark the given resource IDs unavailable, re-propose, return diff.

    Request body: {"unavailable_resource_ids": ["A02", "N01"]}
    Hospitals are not dispatchable; if listed they are ignored.
    """
    body = await request.json()
    unavailable_ids = body.get("unavailable_resource_ids", []) or []
    return _run_proposal_with_unavailable(unavailable_ids)


def _run_proposal_with_unavailable(unavailable_ids):
    """Shared implementation for /api/simulate and /api/allocate.

    Re-proposes assignments with the listed resources marked unavailable.
    Does NOT clear state.overrides. Mutations:
      - resource.status → reset to available, then unavailable for the set.
      - incident.assigned_resource_id → cleared.
      - assignments → rebuilt as pending proposals.
    """
    old_map = {
        a["incident_id"]: a["resource_id"]
        for a in state["assignments"]
        if a["status"] == "confirmed"
    }

    for res in state["resources"]:
        if res["type"] != "hospital":
            res["status"] = "available"

    unavailable_set = set(unavailable_ids)
    for res in state["resources"]:
        if res["id"] in unavailable_set and res["type"] != "hospital":
            res["status"] = "unavailable"

    for inc in state["incidents"]:
        inc["assigned_resource_id"] = None

    proposals = propose_assignments(state["incidents"], state["resources"])

    # Preserve any confirmed/overridden assignments that are still feasible
    # against the CURRENT resource pool (status != unavailable and != busy).
    # Confirmed assignments must be retained across simulate so the user's
    # commitments don't silently disappear.
    confirmed_lookup = {
        a["incident_id"]: a for a in state["assignments"]
        if a["status"] == "confirmed"
    }
    busy_resource_ids = {
        a["resource_id"] for a in state["assignments"]
        if a["status"] == "confirmed"
    }

    new_assignments = []
    for p in proposals:
        existing = confirmed_lookup.get(p["incident_id"])
        if existing:
            res = next(
                (r for r in state["resources"] if r["id"] == existing["resource_id"]),
                None,
            )
            if res and res["status"] != "unavailable" and res["id"] not in busy_resource_ids:
                if p["winner_resource_id"] is None:
                    new_assignments.append({
                        "incident_id": p["incident_id"],
                        "resource_id": existing["resource_id"],
                        "distance_km": existing.get("distance_km"),
                        "status": "confirmed",
                        "candidates": existing.get("candidates", []),
                        "overridden": existing.get("overridden", False),
                    })
                    continue
                new_assignments.append({
                    "incident_id": p["incident_id"],
                    "resource_id": existing["resource_id"],
                    "distance_km": existing.get("distance_km"),
                    "status": "confirmed",
                    "candidates": p["candidates"],
                    "overridden": existing.get("overridden", False),
                })
                continue

        if p["winner_resource_id"] is None:
            continue
        new_assignments.append({
            "incident_id": p["incident_id"],
            "resource_id": p["winner_resource_id"],
            "distance_km": p["winner_distance_km"],
            "status": "pending",
            "candidates": p["candidates"],
            "overridden": False,
        })

    state["assignments"] = new_assignments

    new_map = {
        a["incident_id"]: a["resource_id"]
        for a in new_assignments
        if a["status"] == "confirmed"
    }
    all_inc_ids = set(list(old_map.keys()) + list(new_map.keys()))
    changes = []
    for inc_id in all_inc_ids:
        old_res = old_map.get(inc_id)
        new_res = new_map.get(inc_id)
        if old_res != new_res:
            inc = next(
                (i for i in state["incidents"] if i["id"] == inc_id), None
            )
            changes.append({
                "incident_id": inc_id,
                "incident_name": inc["name"] if inc else inc_id,
                "old_resource_id": old_res,
                "new_resource_id": new_res,
            })

    save_state()

    return {
        "state": state,
        "changes": changes,
        "unavailable_resource_ids": sorted(unavailable_set),
    }


@app.patch("/api/resources/{resource_id}")
async def patch_resource(resource_id: str, request: Request):
    """Change availability status of a resource.

    Body: {"status": "available"|"unavailable"}
    Hospitals reject status changes with 422. Setting busy directly returns 400.
    """
    body = await request.json()
    new_status = body.get("status")
    if new_status not in ("available", "unavailable", "busy"):
        raise HTTPException(
            status_code=400,
            detail="Invalid status. Must be 'available' or 'unavailable'.",
        )
    if new_status == "busy":
        raise HTTPException(
            status_code=400,
            detail="Setting busy directly is not allowed; busy is an allocation output.",
        )

    resources = _resource_lookup()
    if resource_id not in resources:
        raise HTTPException(status_code=404, detail=f"Unknown resource_id: {resource_id}")

    res = resources[resource_id]
    if res["type"] == "hospital":
        raise HTTPException(status_code=422, detail="Hospitals are not dispatchable")

    res["status"] = new_status

    curr_unavailable = [
        r["id"] for r in state["resources"]
        if r["status"] == "unavailable" and r["type"] != "hospital"
    ]
    res_out = _run_proposal_with_unavailable(curr_unavailable)

    return {
        "resource": res,
        "changes": res_out["changes"],
        "state": state,
    }


@app.post("/api/deallocate/{incident_id}")
def deallocate_incident(incident_id: str):
    """Free an incident's assigned resource and re-run allocation."""
    incidents = _incident_lookup()
    if incident_id not in incidents:
        raise HTTPException(status_code=404, detail=f"Unknown incident_id: {incident_id}")

    assignment = _assignment_for(incident_id)
    if not assignment or assignment.get("status") != "confirmed":
        raise HTTPException(
            status_code=404,
            detail=f"Incident {incident_id} has no confirmed assignment to deallocate.",
        )

    freed_resource_id = assignment["resource_id"]
    resources = _resource_lookup()
    if freed_resource_id in resources:
        resources[freed_resource_id]["status"] = "available"

    incidents[incident_id]["assigned_resource_id"] = None
    state["assignments"] = [a for a in state["assignments"] if a["incident_id"] != incident_id]

    curr_unavailable = [
        r["id"] for r in state["resources"]
        if r["status"] == "unavailable" and r["type"] != "hospital"
    ]
    res_out = _run_proposal_with_unavailable(curr_unavailable)

    return {
        "incident_id": incident_id,
        "freed_resource_id": freed_resource_id,
        "changes": res_out["changes"],
        "state": state,
    }


@app.post("/api/confirm")
async def confirm_endpoint(request: Request):
    """Confirm a batch of proposed assignments."""
    body = await request.json()
    if not isinstance(body, list):
        raise HTTPException(
            status_code=400,
            detail="Request body must be a JSON array of {incident_id, resource_id} pairs.",
        )

    incidents = _incident_lookup()
    resources = _resource_lookup()

    for entry in body:
        inc_id = entry.get("incident_id")
        res_id = entry.get("resource_id")
        if inc_id not in incidents:
            raise HTTPException(
                status_code=404,
                detail=f"Unknown incident_id: {inc_id}",
            )
        if res_id not in resources:
            raise HTTPException(
                status_code=404,
                detail=f"Unknown resource_id: {res_id}",
            )

        resource = resources[res_id]
        if resource["status"] == "busy":
            raise HTTPException(
                status_code=409,
                detail=f"Resource {res_id} is already busy.",
            )

    for entry in body:
        inc_id = entry["incident_id"]
        res_id = entry["resource_id"]
        resource = resources[res_id]
        incident = incidents[inc_id]

        for a in state["assignments"]:
            if a["incident_id"] == inc_id:
                if a["status"] == "confirmed":
                    if a["resource_id"] == res_id:
                        break
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            f"Incident {inc_id} is already confirmed to "
                            f"{a['resource_id']}."
                        ),
                    )

                winner_ids = [
                    c["resource_id"] for c in a.get("candidates", [])
                ]
                if res_id not in winner_ids:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"Resource {res_id} is not among the proposed "
                            f"candidates for incident {inc_id}."
                        ),
                    )

                a["resource_id"] = res_id
                winner = next(
                    c for c in a["candidates"] if c["resource_id"] == res_id
                )
                a["distance_km"] = winner["distance_km"]
                a["status"] = "confirmed"
                a["overridden"] = False
                break

        resource["status"] = "busy"
        incident["assigned_resource_id"] = res_id

    save_state()
    return {"state": state}


@app.post("/api/override")
async def override_endpoint(request: Request):
    """Manually override an incident's resource."""
    body = await request.json()
    inc_id = body.get("incident_id")
    res_id = body.get("resource_id")

    incidents = _incident_lookup()
    resources = _resource_lookup()

    if inc_id not in incidents:
        raise HTTPException(status_code=404, detail=f"Unknown incident_id: {inc_id}")
    if res_id not in resources:
        raise HTTPException(status_code=404, detail=f"Unknown resource_id: {res_id}")

    resource = resources[res_id]
    if resource["type"] == "hospital":
        raise HTTPException(
            status_code=400,
            detail=f"Resource {res_id} is a hospital and is not dispatchable.",
        )
    if resource["status"] == "busy":
        raise HTTPException(
            status_code=409,
            detail=f"Resource {res_id} is already busy.",
        )

    incident = incidents[inc_id]
    existing = _assignment_for(inc_id)

    original_suggestion = (
        existing["resource_id"]
        if existing and existing["status"] == "pending"
        else None
    )

    if existing and existing["status"] == "confirmed":
        old_res_id = existing["resource_id"]
        old_res = resources.get(old_res_id)
        if old_res and old_res["status"] == "busy":
            old_res["status"] = "available"
        if incident["assigned_resource_id"] == old_res_id:
            incident["assigned_resource_id"] = None

    import math as _math
    from allocation import haversine as _hav
    dist = _hav(incident["lat"], incident["lng"], resource["lat"], resource["lng"])

    candidates = existing.get("candidates", []) if existing else []
    new_entry = {
        "incident_id": inc_id,
        "resource_id": res_id,
        "distance_km": dist,
        "status": "confirmed",
        "candidates": candidates,
        "overridden": True,
    }

    if existing:
        existing.update(new_entry)
    else:
        state["assignments"].append(new_entry)

    resource["status"] = "busy"
    incident["assigned_resource_id"] = res_id

    state["overrides"].append({
        "incident_id": inc_id,
        "resource_id": res_id,
        "original_suggestion": original_suggestion,
        "timestamp": _now_iso(),
    })

    save_state()
    return {"state": state}


def _now_iso():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@app.post("/api/reset")
def reset():
    """Re-load data.json and recompute everything. Full re-seed."""
    load_and_compute()
    if STATE_FILE.exists():
        try:
            STATE_FILE.unlink()
        except OSError:
            pass
    save_state()
    return state



# ---------------------------------------------------------------------------
# Serve frontend (must be last — catch-all mount)
# ---------------------------------------------------------------------------
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")

# ---------------------------------------------------------------------------
# One-command startup
# ---------------------------------------------------------------------------
def _port_in_use(host: str, port: int) -> bool:
    """Return True if something is already listening on (host, port)."""
    import socket

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            return s.connect_ex((host, port)) == 0
    except OSError:
        return False


if __name__ == "__main__":
    _HOST, _PORT = "0.0.0.0", 8000

    if _port_in_use("127.0.0.1", _PORT):
        sys.exit(
            "ERROR: Port {} is already in use — a ResQ server appears to be "
            "running already. Stop the existing instance (or run on a "
            "different port) before starting a new one.".format(_PORT)
        )

    uvicorn.run(app, host=_HOST, port=_PORT)
