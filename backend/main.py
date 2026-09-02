"""ResQ — FastAPI backend (all routes in one file, per Section 10)."""

import json
from pathlib import Path
import sys

from fastapi import FastAPI, Request
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
from allocation import allocate

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
}


def load_and_compute():
    """Load data.json, compute priority scores, run greedy allocation."""
    with open(DATA_FILE, encoding="utf-8") as f:
        raw = json.load(f)

    incidents = raw["incidents"]
    resources = raw["resources"]
    zone_polygon = raw["zone_polygon"]

    # Compute priority scores
    for inc in incidents:
        result = compute_priority(inc)
        inc["priority_score"] = result["priority_score"]
        inc["breakdown"] = result["breakdown"]
        inc["assigned_resource_id"] = None

    # Ensure all dispatchable resources start as available
    for res in resources:
        if res["type"] != "hospital":
            res["status"] = "available"

    # Run greedy allocation
    assignments = allocate(incidents, resources)

    state["incidents"] = incidents
    state["resources"] = resources
    state["zone_polygon"] = zone_polygon
    state["assignments"] = assignments


# Initial load at startup
load_and_compute()

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/api/state")
def get_state():
    """Return full current state: incidents, resources, zone, assignments."""
    return state


@app.post("/api/simulate")
def simulate():
    """Backward-compatible hardcoded sim: marks A02 unavailable."""
    return _run_allocation_with_unavailable(["A02"])


@app.post("/api/allocate")
async def allocate_endpoint(request: Request):
    """Mark the given resource IDs unavailable, re-run allocation, return diff.

    Request body: {"unavailable_resource_ids": ["A02", "N01"]}
    Hospitals are not dispatchable; if listed they are ignored.
    """
    body = await request.json()
    unavailable_ids = body.get("unavailable_resource_ids", []) or []
    return _run_allocation_with_unavailable(unavailable_ids)


def _run_allocation_with_unavailable(unavailable_ids):
    """Shared implementation for /api/simulate and /api/allocate."""
    # Snapshot old assignments for diffing
    old_map = {a["incident_id"]: a["resource_id"] for a in state["assignments"]}

    # Reset all dispatchable resources to available first
    for res in state["resources"]:
        if res["type"] != "hospital":
            res["status"] = "available"

    # Mark the requested resources as unavailable
    unavailable_set = set(unavailable_ids)
    for res in state["resources"]:
        if res["id"] in unavailable_set and res["type"] != "hospital":
            res["status"] = "unavailable"

    # Clear incident assignments
    for inc in state["incidents"]:
        inc["assigned_resource_id"] = None

    # Re-run allocation from scratch
    assignments = allocate(state["incidents"], state["resources"])
    state["assignments"] = assignments

    # Compute diff
    new_map = {a["incident_id"]: a["resource_id"] for a in assignments}
    all_inc_ids = set(list(old_map.keys()) + list(new_map.keys()))
    changes = []
    for inc_id in all_inc_ids:
        old_res = old_map.get(inc_id)
        new_res = new_map.get(inc_id)
        if old_res != new_res:
            inc = next((i for i in state["incidents"] if i["id"] == inc_id), None)
            changes.append({
                "incident_id": inc_id,
                "incident_name": inc["name"] if inc else inc_id,
                "old_resource_id": old_res,
                "new_resource_id": new_res,
            })

    return {
        "state": state,
        "changes": changes,
        "unavailable_resource_ids": sorted(unavailable_set),
    }


@app.post("/api/reset")
def reset():
    """Re-load data.json and recompute everything. Full re-seed."""
    load_and_compute()
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

    # Single-instance guard: a second ResQ instance must not bind another
    # socket on the same port (on Windows this can silently create two
    # servers — one loopback, one LAN — with independent state, which has
    # cause confusing "stuck loading" behavior in the dashboard).
    if _port_in_use("127.0.0.1", _PORT):
        sys.exit(
            "ERROR: Port {} is already in use — a ResQ server appears to be "
            "running already. Stop the existing instance (or run on a "
            "different port) before starting a new one.".format(_PORT)
        )

    uvicorn.run(app, host=_HOST, port=_PORT)
