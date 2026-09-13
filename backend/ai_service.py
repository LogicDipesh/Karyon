import json
import os
import re
import urllib.request
import urllib.error
from typing import Dict, Any, List, Optional
from allocation import haversine
from scoring import compute_priority

GEMINI_MODEL = "gemini-1.5-flash"


def _call_gemini_api(prompt: str, system_instruction: Optional[str] = None, json_mode: bool = False, temperature: float = 0.2) -> str:
    """Call Google Gemini generateContent REST endpoint using .env API key."""
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("No API key provided.")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={api_key}"
    
    body: Dict[str, Any] = {
        "contents": [
            {
                "parts": [{"text": prompt}]
            }
        ],
        "generationConfig": {
            "temperature": temperature,
        }
    }
    
    if system_instruction:
        body["systemInstruction"] = {
            "parts": [{"text": system_instruction}]
        }
        
    if json_mode:
        body["generationConfig"]["responseMimeType"] = "application/json"

    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    
    with urllib.request.urlopen(req, timeout=15) as resp:
        result = json.loads(resp.read().decode("utf-8"))
        
    candidates = result.get("candidates", [])
    if not candidates:
        raise ValueError("No response candidate returned by Gemini.")
        
    content_parts = candidates[0].get("content", {}).get("parts", [])
    if not content_parts:
        raise ValueError("Empty content returned by Gemini.")
        
    return content_parts[0].get("text", "")


def generate_tactical_plan(state: Dict[str, Any]) -> Dict[str, Any]:
    """Generate operational response briefing based on current state."""
    incidents = [i for i in state.get("incidents", []) if i.get("status") != "completed"]
    resources = state.get("resources", [])
    assignments = state.get("assignments", [])
    
    summary_data = []
    # Sort by override_rank (default 9999) first, then priority_score descending
    for idx, inc in enumerate(sorted(incidents, key=lambda x: (x.get("override_rank") or 9999, -x.get("priority_score", 0)))):
        asgns = [a for a in assignments if a["incident_id"] == inc["id"]]
        if asgns:
            res_info = "Assigned to " + ", ".join(f"{a['resource_id']} ({a.get('distance_km', 0)} km)" for a in asgns)
        else:
            res_info = "UNASSIGNED"
        summary_data.append({
            "rank": idx + 1,
            "id": inc["id"],
            "name": inc["name"],
            "score": inc.get("priority_score"),
            "medical": inc.get("medical_emergency"),
            "trapped": inc.get("trapped"),
            "affected": inc.get("people_affected"),
            "assignment": res_info
        })
        
    available_units = [r["id"] for r in resources if r.get("status") == "available" and r.get("type") != "hospital"]
    busy_units = [r["id"] for r in resources if r.get("status") == "busy"]
    down_units = [r["id"] for r in resources if r.get("status") == "unavailable"]

    try:
        sys_inst = (
            "You are Karyon AI, an expert disaster response coordination intelligence assistant. "
            "Produce a structured tactical response briefing for the human incident commander in clean Markdown. "
            "Keep it concise, actionable, and formatted with headers: "
            "1. Situational Assessment, 2. Priority Dispatch Justification, 3. Critical Resource Bottlenecks, 4. Strategic Recommendations."
        )
        env = state.get("environment", {})
        water_level = env.get("water_level_cm", 150)
        hours = env.get("hours_elapsed", 0)
        
        prompt = (
            f"Current Incidents and Dispatches:\n{json.dumps(summary_data, indent=2)}\n\n"
            f"Available Resources: {available_units}\n"
            f"Busy Resources: {busy_units}\n"
            f"Down/Unavailable Resources: {down_units}\n\n"
            f"Environmental State: Water Level {water_level}cm, Hours Elapsed {hours}.\n"
            "If water levels exceed 180cm, you MUST include a 'CRITICAL PREDICTION' section advising where resources should be proactively staged or warning of impending route flooding.\n\n"
            "Generate the operational tactical plan briefing now."
        )
        briefing = _call_gemini_api(prompt, system_instruction=sys_inst, temperature=1.2)
        return {"plan": briefing, "source": "gemini", "model": GEMINI_MODEL}
    except urllib.error.HTTPError as e:
        if e.code == 429:
            return {
                "plan": "### ⚠️ API Rate Limit Exceeded\n\nYou've clicked Regenerate too many times in a short period and hit the Gemini API rate limit.\n\nPlease wait about **60 seconds** and try again.", 
                "source": "rate_limit_error",
                "model": GEMINI_MODEL
            }
        print("GEMINI API HTTP ERROR:", e)
    except Exception as e:
        print("GEMINI API ERROR:", e)

    # Intelligent local fallback briefing
    lines = [
        "### Operational Response Briefing — Delhi Flood Sector",
        "",
        "**1. Situational Assessment**",
        f"- Active emergency incidents: **{len(incidents)}**",
        f"- Units currently dispatched: **{len(busy_units)}** | Free: **{len(available_units)}** | Out of service: **{len(down_units)}**",
        "",
        "**2. Priority Dispatch Order & Rationale**"
    ]
    for s in summary_data[:5]:
        lines.append(f"- **#{s['rank']} {s['name']} (Score: {s['score']})**: {s['assignment']}.")
    
    unassigned = [s for s in summary_data if "UNASSIGNED" in s["assignment"]]
    if unassigned:
        lines.append("")
        lines.append("**3. Critical Alerts & Bottlenecks**")
        for u in unassigned:
            lines.append(f"- ⚠️ **{u['name']}** has no assigned unit! Allocate backup team immediately.")
    else:
        lines.append("")
        lines.append("**3. Resource Coverage**")
        lines.append("- All active incidents currently have a primary rescue unit dispatched.")

    lines.append("")
    lines.append("**4. Commander Directives**")
    lines.append("- Verify road accessibility along Yamuna marginal bunds.")
    lines.append("- Prioritize critical medical transfers before flood crest window closes.")
    lines.append("*(Plan can be overwritten or adjusted below using natural language commands)*")

    return {"plan": "\n".join(lines), "source": "local_fallback", "model": "rule_engine"}


def _local_nlp_parser(text: str, state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Deterministic local regex/rule parser for admin commands and plan overwrites."""
    actions = []
    
    incidents = state.get("incidents", [])
    resources = state.get("resources", [])

    # Pre-compute the current visual rank order for rank-based lookups
    active_sorted = sorted(
        [i for i in incidents if i.get("status") != "completed"],
        key=lambda x: (x.get("override_rank") or 9999, -x.get("priority_score", 0))
    )

    def find_incident_by_rank(rank_num: int) -> Optional[Dict[str, Any]]:
        """Look up the incident currently displayed at visual rank #rank_num."""
        if 1 <= rank_num <= len(active_sorted):
            return active_sorted[rank_num - 1]
        return None

    def find_incident(ref: str) -> Optional[Dict[str, Any]]:
        ref = ref.strip().lower()
        if not ref:
            return None

        # Check for bare rank number: "1", "#1", "#3", "rank 2"
        rank_match = re.match(r'^#?(\d+)$', ref.strip())
        if rank_match:
            rank_num = int(rank_match.group(1))
            by_rank = find_incident_by_rank(rank_num)
            if by_rank:
                return by_rank

        if len(ref) < 2:
            return None

        # Exact ID match (e.g. "INC-001")
        for inc in incidents:
            if inc["id"].lower() == ref:
                return inc
        # Substring match on full name
        for inc in incidents:
            if ref in inc["name"].lower():
                return inc
        # First-word match (only if name first word is >= 3 chars to avoid false positives)
        for inc in incidents:
            first_name = inc["name"].split()[0].lower()
            if len(first_name) >= 3 and (ref == first_name or first_name in ref.split()):
                return inc
        return None

    def find_resource(ref: str) -> Optional[Dict[str, Any]]:
        ref = ref.strip().upper()
        for r in resources:
            if r["id"].upper() == ref:
                return r
        return None

    statements = re.split(r'[\n;]+', text)
    
    for stmt in statements:
        s = stmt.strip()
        if not s:
            continue
        s_lower = s.lower()

        # 1. Complete task / resolve incident
        comp_match = re.search(r'(?:mark\s+)?([a-z0-9\-\s]+?)\s+(?:as\s+)?(?:completed?|resolved?|done)|(?:complete|resolve)\s+(?:task\s+for\s+|incident\s+)?([a-z0-9\-\s]+)', s_lower)
        if comp_match:
            target_str = comp_match.group(1) or comp_match.group(2)
            if target_str:
                inc = find_incident(target_str)
                if inc:
                    actions.append({
                        "action": "complete_task",
                        "incident_id": inc["id"]
                    })
                    continue

        # 2. Reorder / set priority (handling "top priority", "first", or "#1")
        reorder_match = re.search(r'(?:move|make|put|set|shift)\s+([a-z0-9\-\s]+?)\s+(?:to\s+)?(?:top\s+priority|priority\s+|rank\s+|position\s+|#|number\s+)?(\d+|first|top)', s_lower)
        if reorder_match and not ("unavailable" in s_lower or "available" in s_lower):
            name_str, rank_str = reorder_match.groups()
            inc = find_incident(name_str)
            if inc:
                rank = 1 if rank_str in ["first", "top"] else int(rank_str)
                actions.append({
                    "action": "reorder_priority",
                    "incident_id": inc["id"],
                    "new_rank": rank
                })
                continue

        # 3. Also catch "X top priority" without a verb
        top_match = re.search(r'([a-z]{3,}[\w\s]*?)\s+top\s+priority', s_lower)
        if top_match:
            name_str = top_match.group(1)
            inc = find_incident(name_str)
            if inc:
                actions.append({
                    "action": "reorder_priority",
                    "incident_id": inc["id"],
                    "new_rank": 1
                })
                continue

        # 4. Reassign / Append resource (handling dispatch, send, assign, allocate, also "send X to Y")
        assign_match = re.search(r'(?:assign|reassign|dispatch|send|allocate|add)\s+([a-z0-9]+)\s+(?:to\s+)?([a-z0-9\-\s]+)', s_lower)
        if assign_match:
            res_id_str, inc_str = assign_match.groups()
            res = find_resource(res_id_str)
            inc = find_incident(inc_str.strip())
            if res and inc:
                actions.append({
                    "action": "reassign_resource",
                    "incident_id": inc["id"],
                    "resource_id": res["id"]
                })
                continue

        # 5. Unassign resource
        unassign_match = re.search(r'(?:remove|unassign|withdraw|pull|detach)\s+([a-z0-9]+)\s+(?:from\s+)?([a-z0-9\-\s]+)', s_lower)
        if unassign_match:
            res_id_str, inc_str = unassign_match.groups()
            res = find_resource(res_id_str)
            inc = find_incident(inc_str.strip())
            if res and inc:
                actions.append({
                    "action": "unassign_resource",
                    "incident_id": inc["id"],
                    "resource_id": res["id"]
                })
                continue

        # 6. Resource status: unavailable / down
        status_match = re.search(r'(?:mark|set)?\s*([a-z0-9]+)\s+(?:as\s+)?(unavailable|down|offline|available|online|ready)', s_lower)
        if status_match:
            res_id_str, st_str = status_match.groups()
            res = find_resource(res_id_str)
            if res:
                target_status = "unavailable" if st_str in ("unavailable", "down", "offline") else "available"
                actions.append({
                    "action": "set_resource_status",
                    "resource_id": res["id"],
                    "status": target_status
                })
                continue

    return actions


def parse_plan_overwrite(state: Dict[str, Any], text: str) -> List[Dict[str, Any]]:
    """Parse admin plan edits or commands into structured state actions."""
    incidents = state.get("incidents", [])
    resources = state.get("resources", [])

    # Pre-compute the current visual rank order
    active_sorted = sorted(
        [i for i in incidents if i.get("status") != "completed"],
        key=lambda x: (x.get("override_rank") or 9999, -x.get("priority_score", 0))
    )

    incident_context = []
    for inc in incidents:
        rank = -1
        if inc in active_sorted:
            rank = active_sorted.index(inc) + 1
        incident_context.append({"id": inc["id"], "name": inc["name"], "current_rank": rank if rank > 0 else "completed"})

    resource_context = [{"id": r["id"], "type": r["type"], "status": r["status"]} for r in resources]

    try:
        sys_inst = (
            "You are an NLP state parser for disaster response operations. "
            "Parse the commander's natural language instructions into a JSON list of actions. "
            "Map partial names to the exact incident ID, and resource codes to the exact resource ID.\n"
            "Supported actions:\n"
            '1. {"action": "reorder_priority", "incident_id": "INC-XXX", "new_rank": 1}\n'
            '2. {"action": "reassign_resource", "incident_id": "INC-XXX", "resource_id": "A01"}\n'
            '3. {"action": "unassign_resource", "incident_id": "INC-XXX", "resource_id": "A01"}\n'
            '4. {"action": "complete_task", "incident_id": "INC-XXX"}\n'
            '5. {"action": "set_resource_status", "resource_id": "A01", "status": "available"|"unavailable"}\n\n'
            "IMPORTANT: When a resource is assigned to an incident that already has other resources, "
            "DO NOT unassign or remove the existing ones. Just add the new one. "
            "Multiple resources CAN be assigned to the same incident simultaneously.\n"
            "IMPORTANT: If the user refers to incidents by numbers like '1', '#1', 'rank 1', match it to the incident with that 'current_rank' in the context.\n\n"
            "EXAMPLES:\n"
            "- \"Make Fatima top priority\" -> [{\"action\": \"reorder_priority\", \"incident_id\": \"INC-003\", \"new_rank\": 1}]\n"
            "- \"move 1 to 4 and complete 4\" -> [{\"action\": \"reorder_priority\", \"incident_id\": \"<id of current_rank 1>\", \"new_rank\": 4}, {\"action\": \"complete_task\", \"incident_id\": \"<id of current_rank 4>\"}]\n"
            "- \"Send A02 to Ramesh\" -> [{\"action\": \"reassign_resource\", \"incident_id\": \"INC-001\", \"resource_id\": \"A02\"}]\n"
            "- \"Also send N01 to Ramesh\" -> [{\"action\": \"reassign_resource\", \"incident_id\": \"INC-001\", \"resource_id\": \"N01\"}]\n"
            "- \"Remove N01 from Ramesh\" -> [{\"action\": \"unassign_resource\", \"incident_id\": \"INC-001\", \"resource_id\": \"N01\"}]\n"
            "- \"Ramesh is done. N01 is down\" -> [{\"action\": \"complete_task\", \"incident_id\": \"INC-001\"}, {\"action\": \"set_resource_status\", \"resource_id\": \"N01\", \"status\": \"unavailable\"}]\n\n"
            "Return ONLY a valid JSON object with an 'actions' array."
        )
        prompt = (
            f"Valid Incidents:\n{json.dumps(incident_context)}\n\n"
            f"Valid Resources:\n{json.dumps(resource_context)}\n\n"
            f"Admin Input/Command:\n\"{text}\"\n\n"
            "Extract all state actions from the admin input as JSON:"
        )
        raw_response = _call_gemini_api(prompt, system_instruction=sys_inst, json_mode=True)
        actions = json.loads(raw_response)
        if isinstance(actions, dict) and "actions" in actions:
            actions = actions["actions"]
        if isinstance(actions, list) and len(actions) > 0:
            return actions
    except Exception:
        pass

    return _local_nlp_parser(text, state)


def apply_actions(state: Dict[str, Any], actions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Execute parsed actions on the state, update assignments, and generate diffs."""
    changes = []
    messages = []
    
    incidents = state.get("incidents", [])
    resources = state.get("resources", [])
    assignments = state.get("assignments", [])

    for act in actions:
        action_type = act.get("action")
        
        # 1. Complete Task
        if action_type == "complete_task":
            inc_id = act.get("incident_id")
            inc = next((i for i in incidents if i["id"] == inc_id), None)
            if inc:
                inc["status"] = "completed"
                # Free ALL resources assigned to this incident
                freed_resources = []
                inc_assignments = [a for a in assignments if a["incident_id"] == inc_id]
                for a in inc_assignments:
                    res = next((r for r in resources if r["id"] == a["resource_id"]), None)
                    if res:
                        res["status"] = "available"
                        freed_resources.append(res["id"])
                
                if freed_resources:
                    assignments[:] = [a for a in assignments if a["incident_id"] != inc_id]
                    changes.append({
                        "incident_id": inc_id,
                        "incident_name": inc["name"],
                        "old_resource_id": ", ".join(freed_resources),
                        "new_resource_id": None,
                        "note": "Task completed; route removed, resource freed."
                    })
                inc["assigned_resource_ids"] = []
                messages.append(f"Completed task for {inc['name']}.")

        # 2. Reorder Priority (Using absolute override_rank, no score modification)
        elif action_type == "reorder_priority":
            inc_id = act.get("incident_id")
            new_rank = act.get("new_rank", 1)
            inc = next((i for i in incidents if i["id"] == inc_id), None)
            if inc:
                # Get the current visual sorted order
                active_inc = sorted([i for i in incidents if i.get("status") != "completed"],
                                    key=lambda x: (x.get("override_rank") or 9999, -x.get("priority_score", 0)))
                
                if inc in active_inc:
                    active_inc.remove(inc)
                    # Insert the incident at its new target position
                    target_idx = max(0, min(new_rank - 1, len(active_inc)))
                    active_inc.insert(target_idx, inc)
                    
                    # Re-apply strict override_ranks to freeze this new order for all active incidents
                    for idx, item in enumerate(active_inc):
                        item["override_rank"] = idx + 1
                        item["manual_override"] = True

                messages.append(f"Pinned {inc['name']} to rank #{new_rank} without altering priority score.")

        # 3. Assign / Append Resource (ADDITIVE — does NOT remove existing resources from the incident)
        elif action_type == "reassign_resource":
            inc_id = act.get("incident_id")
            res_id = act.get("resource_id")
            inc = next((i for i in incidents if i["id"] == inc_id), None)
            res = next((r for r in resources if r["id"] == res_id), None)
            
            if inc and res:
                # Step 1: Remove this resource from any OTHER incident it's currently on
                # Build a snapshot list first to avoid mutating while iterating
                to_remove = [a for a in assignments if a["resource_id"] == res_id and a["incident_id"] != inc_id]
                for old_a in to_remove:
                    other_inc = next((i for i in incidents if i["id"] == old_a["incident_id"]), None)
                    if other_inc:
                        ids_list = other_inc.get("assigned_resource_ids", [])
                        if res_id in ids_list:
                            ids_list.remove(res_id)
                # Now filter assignments list
                assignments[:] = [a for a in assignments if not (a["resource_id"] == res_id and a["incident_id"] != inc_id)]

                # Step 2: Check if it's already assigned to THIS incident (prevent duplicates)
                existing = next((a for a in assignments if a["incident_id"] == inc_id and a["resource_id"] == res_id), None)
                if not existing:
                    dist = round(haversine(inc["lat"], inc["lng"], res["lat"], res["lng"]), 1)
                    if "assigned_resource_ids" not in inc:
                        inc["assigned_resource_ids"] = []
                    inc["assigned_resource_ids"].append(res["id"])
                    res["status"] = "busy"
                    assignments.append({
                        "incident_id": inc["id"],
                        "resource_id": res["id"],
                        "distance_km": dist
                    })
                    changes.append({
                        "incident_id": inc["id"],
                        "incident_name": inc["name"],
                        "old_resource_id": None,
                        "new_resource_id": res["id"],
                        "note": "Resource appended manually"
                    })
                    messages.append(f"Assigned {res['id']} to {inc['name']} ({dist} km).")
                else:
                    messages.append(f"{res['id']} is already assigned to {inc['name']}.")

        # 4. Unassign Resource
        elif action_type == "unassign_resource":
            inc_id = act.get("incident_id")
            res_id = act.get("resource_id")
            inc = next((i for i in incidents if i["id"] == inc_id), None)
            res = next((r for r in resources if r["id"] == res_id), None)
            
            if inc and res:
                asgn = next((a for a in assignments if a["incident_id"] == inc_id and a["resource_id"] == res_id), None)
                if asgn:
                    assignments.remove(asgn)
                    ids_list = inc.get("assigned_resource_ids", [])
                    if res_id in ids_list:
                        ids_list.remove(res_id)
                    res["status"] = "available"
                    changes.append({
                        "incident_id": inc_id,
                        "incident_name": inc["name"],
                        "old_resource_id": res_id,
                        "new_resource_id": None,
                        "note": "Resource manually unassigned"
                    })
                    messages.append(f"Unassigned {res['id']} from {inc['name']}.")
                else:
                    messages.append(f"{res['id']} is not currently assigned to {inc['name']}.")

        # 5. Set Resource Status
        elif action_type == "set_resource_status":
            res_id = act.get("resource_id")
            target_status = act.get("status")
            res = next((r for r in resources if r["id"] == res_id), None)
            if res and res.get("type") != "hospital":
                res["status"] = target_status
                if target_status == "unavailable":
                    # Remove ALL assignments involving this resource
                    affected_assignments = [a for a in assignments if a["resource_id"] == res_id]
                    for a in affected_assignments:
                        inc = next((i for i in incidents if i["id"] == a["incident_id"]), None)
                        if inc:
                            ids_list = inc.get("assigned_resource_ids", [])
                            if res_id in ids_list:
                                ids_list.remove(res_id)
                    assignments[:] = [a for a in assignments if a["resource_id"] != res_id]
                messages.append(f"Resource {res_id} marked {target_status}.")

    state["assignments"] = assignments
    return {
        "state": state,
        "changes": changes,
        "actions_applied": actions,
        "summary": " | ".join(messages) if messages else "No state changes applied."
    }
