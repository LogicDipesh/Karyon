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


def _pool_for(inc, available):
    """Return the restricted candidate pool for an incident.

    Medical/trapped → prefer ambulance/NDRF, fall back to all-available.
    Other incidents → all-available.
    Identical to the original algorithm's pool rule.
    """
    if inc.get("medical_emergency") or inc.get("trapped"):
        preferred = [r for r in available if r["type"] in ("ambulance", "ndrf")]
        return preferred if preferred else available
    return available


def propose_assignments(incidents, resources):
    """Non-mutating proposal: produce top-3 candidates and a winner per incident.

    - Does NOT touch resource.status or incident.assigned_resource_id.
    - Sorts incidents by priority_score descending (same as original).
    - For each incident, builds the same restricted pool the original algorithm
      would use, then returns up to 3 nearest resources in that pool.
    - If the restricted pool is empty, falls back to the nearest 3 overall,
      labelled "farther".
    - Winner = nearest in the (possibly empty→fallback) pool. Must match the
      original allocate() pick for the same input, since both use the same
      pool rule and the same haversine.

    Returns: list of proposal dicts:
        {
          "incident_id": str,
          "winner_resource_id": str | None,
          "winner_distance_km": float | None,
          "candidates": [
              {"resource_id", "distance_km", "reason"},  # up to 3, ordered nearest-first
          ],
          "pool_was_empty": bool,
        }
    """
    sorted_incidents = sorted(
        incidents, key=lambda x: x["priority_score"], reverse=True
    )

    available_all = [
        r for r in resources
        if r["status"] == "available" and r["type"] != "hospital"
    ]

    proposals = []

    for inc in sorted_incidents:
        pool = _pool_for(inc, available_all)
        pool_was_empty = len(pool) == 0
        source = pool if pool else available_all

        # Compute haversine distance for every candidate in the source.
        scored = []
        for r in source:
            d = haversine(inc["lat"], inc["lng"], r["lat"], r["lng"])
            scored.append((r["id"], d))

        # Sort by distance ascending; tie-break by id for determinism.
        scored.sort(key=lambda t: (t[1], t[0]))

        top = scored[:3]
        candidates = []
        for idx, (rid, dist) in enumerate(top):
            reason = "recommended" if idx == 0 else "farther"
            candidates.append({
                "resource_id": rid,
                "distance_km": dist,
                "reason": reason,
            })

        winner_id = top[0][0] if top else None
        winner_dist = top[0][1] if top else None

        proposals.append({
            "incident_id": inc["id"],
            "winner_resource_id": winner_id,
            "winner_distance_km": winner_dist,
            "candidates": candidates,
            "pool_was_empty": pool_was_empty,
        })

    return proposals


def allocate(incidents, resources):
    """Greedy nearest-feasible assignment (original committed allocator).

    - Sorts incidents by priority_score descending.
    - For each incident, finds the nearest available non-hospital resource.
    - Medical/trapped incidents prefer ambulance/NDRF but fall back to any.
    - Modifies incidents (assigned_resource_id) and resources (status) in place.
    - Returns list of assignment dicts: {incident_id, resource_id, distance_km}.

    Retained for reference and for offline equivalence checks against
    propose_assignments(). Not used by the live API surface anymore.
    """
    sorted_incidents = sorted(
        incidents, key=lambda x: x["priority_score"], reverse=True
    )

    assignments = []

    for inc in sorted_incidents:
        available = [
            r for r in resources
            if r["status"] == "available" and r["type"] != "hospital"
        ]

        if not available:
            inc["assigned_resource_id"] = None
            continue

        candidates = _pool_for(inc, available)

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
