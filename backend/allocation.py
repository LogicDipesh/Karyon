import math
import urllib.request
import json

def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2)**2
    return R * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))

def get_osrm_route(lat1, lon1, lat2, lon2):
    """Fetch real driving distance and duration from OSRM public API."""
    url = f"http://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}?overview=false"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Karyon-Disaster-Response/1.0"})
        with urllib.request.urlopen(req, timeout=2) as response:
            data = json.loads(response.read().decode())
            if data.get("code") == "Ok" and len(data.get("routes", [])) > 0:
                route = data["routes"][0]
                distance_km = route["distance"] / 1000.0
                duration_min = route["duration"] / 60.0
                return distance_km, duration_min
    except Exception as e:
        print(f"OSRM Routing Error: {e}")
    return None, None

def allocate(incidents, resources, existing_assignments=None):
    if existing_assignments is None:
        existing_assignments = []
        
    active_incidents = [i for i in incidents if i.get("status") != "completed"]
    
    sorted_incidents = sorted(
        active_incidents,
        key=lambda x: (x.get("override_rank") or 9999, -x.get("priority_score", 0))
    )

    assignments = list(existing_assignments)

    for inc in sorted_incidents:
        # Skip if the incident already has a resource assigned
        if inc.get("assigned_resource_ids"):
            continue
            
        available = [
            r for r in resources
            if r["status"] == "available" and r["type"] != "hospital"
        ]

        if not available:
            if "assigned_resource_ids" not in inc:
                inc["assigned_resource_ids"] = []
            continue

        if inc.get("medical_emergency") or inc.get("trapped"):
            preferred = [r for r in available if r["type"] in ("ambulance", "ndrf")]
            candidates = preferred if preferred else available
        else:
            candidates = available

        best_res = None
        best_dist = float("inf")
        for res in candidates:
            if res["status"] == "available" and res["type"] != "hospital":
                dist = haversine(inc["lat"], inc["lng"], res["lat"], res["lng"])
                if dist < best_dist:
                    best_dist = dist
                    best_res = res

        if best_res:
            best_res["status"] = "busy"
            if "assigned_resource_ids" not in inc:
                inc["assigned_resource_ids"] = []
            inc["assigned_resource_ids"].append(best_res["id"])
            
            drive_dist, drive_duration = get_osrm_route(inc["lat"], inc["lng"], best_res["lat"], best_res["lng"])
            final_dist = round(drive_dist, 1) if drive_dist is not None else round(best_dist, 1)
            eta = round(drive_duration) if drive_duration is not None else round(best_dist * 2) # fallback ~30km/h
            
            assignments.append({
                "incident_id": inc["id"],
                "resource_id": best_res["id"],
                "distance_km": final_dist,
                "eta_minutes": eta,
                "routing_source": "osrm" if drive_dist is not None else "haversine"
            })
        else:
            if "assigned_resource_ids" not in inc:
                inc["assigned_resource_ids"] = []

    return assignments
