"""Priority scoring — transparent, hardcoded formula (Section 6)."""


def compute_priority(incident):
    """Compute priority score for an incident.

    Returns dict with:
        priority_score: float  — the total
        breakdown: list of {label, value} for each non-zero term
    """
    terms = []

    # +30 if medical emergency
    medical_val = 30 * int(incident["medical_emergency"])
    if medical_val > 0:
        terms.append({"label": "Medical emergency", "value": medical_val})

    # +20 if any vulnerable persons (elderly/children/disabled)
    vulnerable_val = 20 * int(incident["vulnerable_count"] > 0)
    if vulnerable_val > 0:
        terms.append({"label": "Vulnerable persons present", "value": vulnerable_val})

    # +20 if trapped / inaccessible
    trapped_val = 20 * int(incident["trapped"])
    if trapped_val > 0:
        terms.append({"label": "Trapped / inaccessible", "value": trapped_val})

    # +15 * (severity / 5)
    severity_val = 15 * (incident["severity"] / 5)
    if severity_val > 0:
        terms.append({
            "label": f"Severity ({incident['severity']}/5)",
            "value": round(severity_val, 1),
        })

    # +10 * min(people_affected, 10) / 10
    people_val = 10 * min(incident["people_affected"], 10) / 10
    if people_val > 0:
        terms.append({
            "label": f"People affected ({incident['people_affected']})",
            "value": round(people_val, 1),
        })

    total = sum(t["value"] for t in terms)

    return {
        "priority_score": round(total, 1),
        "breakdown": terms,
    }
