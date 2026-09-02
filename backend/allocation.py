"""Greedy nearest-feasible allocation (Section 7).

Uses haversine (straight-line) distance only — no routing API.
Hospitals are excluded from the allocation loop.
"""

import math


def haversine(lat1, lng1, lat2, lng2):
    """Straight-line distance between two lat/lng points, in km."""
    R = 6371  # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlng / 2) ** 2)
    c = 2 * math.asin(math.sqrt(a))
    return round(R * c, 2)


def allocate(incidents, resources):
    """Greedy nearest-feasible assignment.

    - Sorts incidents by priority_score descending.
    - For each incident, finds the nearest available non-hospital resource.
    - Medical/trapped incidents prefer ambulance/NDRF but fall back to any.
    - Modifies incidents (assigned_resource_id) and resources (status) in place.
    - Returns list of assignment dicts: {incident_id, resource_id, distance_km}.
    """
    sorted_incidents = sorted(
        incidents, key=lambda x: x["priority_score"], reverse=True
    )

    assignments = []

    for inc in sorted_incidents:
        # Available non-hospital resources only
        available = [
            r for r in resources
            if r["status"] == "available" and r["type"] != "hospital"
        ]

        if not available:
            inc["assigned_resource_id"] = None
            continue

        # Soft preference: medical/trapped → prefer ambulance/ndrf
        if inc.get("medical_emergency") or inc.get("trapped"):
            preferred = [r for r in available if r["type"] in ("ambulance", "ndrf")]
            candidates = preferred if preferred else available
        else:
            candidates = available

        # Pick nearest by haversine
        best = None
        best_dist = float("inf")
        for r in candidates:
            dist = haversine(inc["lat"], inc["lng"], r["lat"], r["lng"])
            if dist < best_dist:
                best = r
                best_dist = dist

        if best:
            inc["assigned_resource_id"] = best["id"]
            best["status"] = "busy"
            assignments.append({
                "incident_id": inc["id"],
                "resource_id": best["id"],
                "distance_km": best_dist,
            })
        else:
            inc["assigned_resource_id"] = None

    return assignments
