"""Priority scoring — transparent, hardcoded formula (Section 6)."""


def compute_priority(incident):
    """Compute priority score for an incident.

    Returns dict with:
        priority_score: float  — the total
        breakdown: list of {label, value} for each non-zero term
    """
    terms = []

    # +30 if medical emergency
    medical_val = 30 * int(incident.get("medical_emergency", False))
    if medical_val > 0:
        terms.append({"label": "Medical emergency", "value": medical_val})

    # +25 if water rising rapidly
    water_val = 25 * int(incident.get("water_rising_rapidly", False))
    if water_val > 0:
        terms.append({"label": "Water rising rapidly", "value": water_val})

    # +25 if structural collapse risk
    struct_val = 25 * int(incident.get("structural_collapse_risk", False))
    if struct_val > 0:
        terms.append({"label": "Structural collapse risk", "value": struct_val})

    # +20 if vulnerable persons (elderly/children/disabled)
    vulnerable_val = 20 * int(incident.get("vulnerable_count", 0) > 0)
    if vulnerable_val > 0:
        terms.append({"label": "Vulnerable persons present", "value": vulnerable_val})

    # +20 if trapped / inaccessible
    trapped_val = 20 * int(incident.get("trapped", False))
    if trapped_val > 0:
        terms.append({"label": "Trapped / inaccessible", "value": trapped_val})

    # Location type bonuses
    loc = incident.get("location_type", "").lower()
    if loc == "hospital":
        terms.append({"label": "Critical Infra (Hospital)", "value": 20})
    elif loc == "school":
        terms.append({"label": "Critical Infra (School)", "value": 15})

    # +15 * (severity / 5)
    severity_val = 15 * (incident.get("severity", 1) / 5)
    if severity_val > 0:
        terms.append({
            "label": f"Severity ({incident.get('severity', 1)}/5)",
            "value": round(severity_val, 1),
        })

    # +10 * min(people_affected, 10) / 10
    people_val = 10 * min(incident.get("people_affected", 0), 10) / 10
    if people_val > 0:
        terms.append({
            "label": f"People affected ({incident.get('people_affected', 0)})",
            "value": round(people_val, 1),
        })

    # +5 per hour pending
    hours = incident.get("hours_pending", 0)
    if hours > 0:
        terms.append({"label": f"Time pending ({hours} hrs)", "value": hours * 5})

    # +30 if Hazmat / Toxic exposure
    hazmat_val = 30 * int(incident.get("hazmat_present", False))
    if hazmat_val > 0:
        terms.append({"label": "Hazmat / Toxic exposure", "value": hazmat_val})

    # +15 if Communication Lost
    comm_val = 15 * int(incident.get("comm_lost", False))
    if comm_val > 0:
        terms.append({"label": "Communication lost", "value": comm_val})

    # +25 if Fire Spreading
    fire_val = 25 * int(incident.get("fire_spreading", False))
    if fire_val > 0:
        terms.append({"label": "Fire spreading rapidly", "value": fire_val})

    # +40 if MCI Declared (Mass Casualty Incident)
    mci_val = 40 * int(incident.get("mci_declared", False))
    if mci_val > 0:
        terms.append({"label": "Mass Casualty Incident (MCI)", "value": mci_val})

    # +10 per supply shortage
    shortages = incident.get("supply_shortage", [])
    if shortages:
        shortage_val = 10 * len(shortages)
        terms.append({"label": f"Supply shortage ({len(shortages)} items)", "value": shortage_val})
        
    # +15 if Weather Deteriorating
    weather_val = 15 * int(incident.get("weather_deteriorating", False))
    if weather_val > 0:
        terms.append({"label": "Weather deteriorating", "value": weather_val})

    total = sum(t["value"] for t in terms)

    return {
        "priority_score": round(total, 1),
        "breakdown": terms,
    }
