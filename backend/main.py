"""Karyon — FastAPI backend (all routes in one file, per Section 10)."""

import json
from pathlib import Path
import sys
import os
from dotenv import load_dotenv

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
import uvicorn

# ---------------------------------------------------------------------------
# Paths & sys.path setup
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Load .env file for Gemini API Key
load_dotenv(BASE_DIR / ".env")

DATA_FILE = BASE_DIR / "data.json"
FRONTEND_DIR = BASE_DIR.parent / "frontend"

from scoring import compute_priority
from allocation import allocate
from ai_service import generate_tactical_plan, parse_plan_overwrite, apply_actions

from fastapi.responses import JSONResponse, RedirectResponse, Response
import hashlib

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="Karyon — Disaster Response Coordinator")

# ---------------------------------------------------------------------------
# Authentication Middleware
# ---------------------------------------------------------------------------
# The fixed admin credentials requested by the user
ADMIN_USER_ID = "9368060619"
ADMIN_PASSWD = "SP@0608"
ADMIN_TOKEN = hashlib.sha256(f"{ADMIN_USER_ID}:{ADMIN_PASSWD}".encode()).hexdigest()

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    
    # Allow unauthenticated access to the login page, login API, and stylesheet
    if path in ["/login.html", "/api/login", "/style.css"]:
        return await call_next(request)
        
    # Check for the secure admin session cookie
    token = request.cookies.get("admin_session")
    
    if token != ADMIN_TOKEN:
        if path.startswith("/api/"):
            return JSONResponse(
                status_code=401, 
                content={"error": "Unauthorized"},
                headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"}
            )
        return RedirectResponse(
            url="/login.html",
            headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"}
        )
        
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response

# ---------------------------------------------------------------------------
# In-memory state (no database — Section 3/4)
# ---------------------------------------------------------------------------
state = {
    "incidents": [],
    "resources": [],
    "zone_polygon": [],
    "assignments": [],
    "environment": {
        "water_level_cm": 150,
        "rain_intensity": "heavy",
        "hours_elapsed": 0
    }
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
        inc["override_rank"] = None
        result = compute_priority(inc)
        inc["priority_score"] = result["priority_score"]
        inc["breakdown"] = result["breakdown"]
        inc["assigned_resource_ids"] = []
        inc["status"] = "active"
        inc["manual_override"] = False

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


@app.post("/api/login")
async def login(request: Request, response: Response):
    """Secure admin login endpoint."""
    body = await request.json()
    user_id = body.get("user_id")
    password = body.get("password")
    
    if user_id == ADMIN_USER_ID and password == ADMIN_PASSWD:
        response.set_cookie(key="admin_session", value=ADMIN_TOKEN, httponly=True, max_age=86400, samesite="lax")
        return {"status": "success"}
    
    return JSONResponse(status_code=401, content={"error": "Invalid credentials"})


@app.post("/api/simulate")
def simulate():
    """Backward-compatible sim: marks A02 unavailable and advances environment."""
    # Advance the environment
    state["environment"]["hours_elapsed"] += 1
    state["environment"]["water_level_cm"] += 15
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
    import copy
    old_assignments = copy.deepcopy(state.get("assignments", []))

    # Mark the requested resources as unavailable and others as available (unless busy/completed logic applies)
    unavailable_set = set(unavailable_ids)
    for res in state["resources"]:
        if res["type"] != "hospital":
            if res["id"] in unavailable_set:
                res["status"] = "unavailable"
            elif res["status"] == "unavailable":
                res["status"] = "available"

    # Remove assignments involving unavailable resources
    valid_assignments = []
    for a in old_assignments:
        res = next((r for r in state["resources"] if r["id"] == a["resource_id"]), None)
        if res and res["status"] != "unavailable":
            valid_assignments.append(a)
            # Re-affirm busy status for resources still assigned
            res["status"] = "busy"
    
    # Update state assignments and incident IDs lists with only valid assignments
    state["assignments"] = valid_assignments
    for inc in state["incidents"]:
        if inc.get("status") != "completed":
            inc["assigned_resource_ids"] = [a["resource_id"] for a in valid_assignments if a["incident_id"] == inc["id"]]

    # Re-run allocation only on active incidents
    active_incidents = [i for i in state["incidents"] if i.get("status") != "completed"]
    assignments = allocate(active_incidents, state["resources"], valid_assignments)
    state["assignments"] = assignments

    # Compute diff
    from collections import defaultdict
    old_map = defaultdict(set)
    for a in old_assignments:
        old_map[a["incident_id"]].add(a["resource_id"])
        
    new_map = defaultdict(set)
    for a in assignments:
        new_map[a["incident_id"]].add(a["resource_id"])

    all_inc_ids = set(list(old_map.keys()) + list(new_map.keys()))
    changes = []
    for inc_id in all_inc_ids:
        old_res_set = old_map.get(inc_id, set())
        new_res_set = new_map.get(inc_id, set())
        if old_res_set != new_res_set:
            inc = next((i for i in state["incidents"] if i["id"] == inc_id), None)
            old_str = ", ".join(sorted(old_res_set)) if old_res_set else None
            new_str = ", ".join(sorted(new_res_set)) if new_res_set else None
            changes.append({
                "incident_id": inc_id,
                "incident_name": inc["name"] if inc else inc_id,
                "old_resource_id": old_str,
                "new_resource_id": new_str,
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


@app.post("/api/ai/plan")
async def get_ai_plan(request: Request):
    """Generate situational response plan via Gemini (or smart fallback)."""
    body = await request.json()
    api_key = body.get("api_key")
    if api_key:
        os.environ["GEMINI_API_KEY"] = api_key
    plan_data = generate_tactical_plan(state)
    return plan_data


@app.post("/api/ai/apply")
async def apply_ai_commands(request: Request):
    """Process natural language commands using Gemini and update state."""
    body = await request.json()
    api_key = body.get("api_key")
    if api_key:
        os.environ["GEMINI_API_KEY"] = api_key
    command_text = body.get("command", "") or body.get("text", "")
    if not command_text:
        return {"error": "No command provided"}
    actions = parse_plan_overwrite(state, command_text)
    result = apply_actions(state, actions)
    return result


@app.post("/api/incident/complete")
async def complete_incident_endpoint(request: Request):
    """Mark an incident task as completed, free the assigned resource, and clear route."""
    body = await request.json()
    incident_id = body.get("incident_id")
    result = apply_actions(state, [{"action": "complete_task", "incident_id": incident_id}])
    return result


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

    # Single-instance guard: a second Karyon instance must not bind another
    # socket on the same port (on Windows this can silently create two
    # servers — one loopback, one LAN — with independent state, which has
    # cause confusing "stuck loading" behavior in the dashboard).
    if _port_in_use("127.0.0.1", _PORT):
        sys.exit(
            "ERROR: Port {} is already in use — a Karyon server appears to be "
            "running already. Stop the existing instance (or run on a "
            "different port) before starting a new one.".format(_PORT)
        )

    uvicorn.run(app, host=_HOST, port=_PORT)
