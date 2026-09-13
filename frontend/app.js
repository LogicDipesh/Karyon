/* ============================================================
   Karyon — Dashboard Logic
   Leaflet map + ranked incident list + resource status +
   simulate/reset controls + AI Tactical Plan & NLP Overwrite.
   ============================================================ */

// ----- State -----
let map;
const incidentMarkers = {};
const resourceMarkers = {};
let assignmentLinesLayer;
let zoneLayer;
let currentState = null;
let highlightedIncidentId = null;
const expandedResourceTypes = new Set();
let showAllRoutes = true;

// ----- Colours (match style.css) -----
const RESOURCE_COLORS = {
    ambulance: "#3498db",
    ndrf:      "#2ecc71",
    fire:      "#e67e22",
    hospital:  "#ecf0f1",
};

const RESOURCE_LABELS = {
    ambulance: "Ambulances",
    ndrf:      "NDRF Teams",
    fire:      "Fire Units",
    hospital:  "Hospitals",
};

// ----- Init -----
document.addEventListener("DOMContentLoaded", init);

async function init() {
    initMap();
    await loadState();
    await fetchAiPlan();

    document.getElementById("simulate-btn").addEventListener("click", onSimulate);
    document.getElementById("reset-btn").addEventListener("click", onReset);
    document.getElementById("picker-cancel-btn").addEventListener("click", hidePicker);
    document.getElementById("picker-clear-btn").addEventListener("click", clearPickerSelection);
    document.getElementById("picker-run-btn").addEventListener("click", runPickerAllocation);

    // Initialize API Key if stored
    initApiKey();

    const regenBtn = document.getElementById("ai-regen-btn");
    if (regenBtn) {
        regenBtn.addEventListener("click", () => fetchAiPlan(true));
    }

    const saveApiKeyBtn = document.getElementById("save-api-key");
    if (saveApiKeyBtn) {
        saveApiKeyBtn.addEventListener("click", saveApiKey);
    }

    const applyBtn = document.getElementById("ai-apply-btn");
    if (applyBtn) {
        applyBtn.addEventListener("click", applyAiOverwrite);
    }

    // Route toggle
    const routeToggle = document.getElementById("toggle-all-routes");
    if (routeToggle) {
        showAllRoutes = routeToggle.checked;
        routeToggle.addEventListener("change", function () {
            showAllRoutes = this.checked;
            renderAssignmentRoutes();
        });
    }

    document.getElementById("panel").addEventListener("click", function (e) {
        if (!e.target.closest(".incident-header") && !e.target.closest(".resource-unit-row")) {
            if (highlightedIncidentId) {
                highlightMarker(highlightedIncidentId);
            }
        }
    });
}

function initMap() {
    map = L.map("map", { zoomControl: true, attributionControl: true });

    // Give the map an explicit view before any path layers are added.
    // Leaflet's canvas renderer keeps an undefined clip bounds until the map
    // has a real view; adding the zone polygon (a Path layer) first then
    // crashes inside `intersects` ("Cannot read properties of undefined") and
    // aborts rendering of the whole dashboard. `renderMap`'s fitBounds()
    // overrides this view immediately after, so the initial map is unaffected.
    map.setView([28.65, 77.27], 12);

    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution:
            '&copy; <a href="https://openstreetmap.org/copyright">OpenStreetMap</a>',
        maxZoom: 18,
    }).addTo(map);

    assignmentLinesLayer = L.layerGroup().addTo(map);

    map.on('click', function () {
        if (highlightedIncidentId) {
            highlightMarker(highlightedIncidentId);
        }
    });
}

// ----- Data Loading -----
async function loadState() {
    const res = await fetch("/api/state");
    currentState = await res.json();
    renderAll(currentState);
}

// ----- Render Everything -----
function renderAll(data, changes) {
    renderMap(data);
    renderIncidentList(data, changes);
    renderResourceStatus(data);
    renderAssignmentRoutes();
    
    // Render environment
    if (data.environment) {
        const elWater = document.getElementById("env-water");
        const elHours = document.getElementById("env-hours");
        const envDisplay = document.getElementById("env-display");
        if (elWater) elWater.textContent = data.environment.water_level_cm;
        if (elHours) elHours.textContent = data.environment.hours_elapsed;
        
        if (data.environment.water_level_cm >= 180 && envDisplay) {
            envDisplay.style.color = "#e74c3c";
            envDisplay.style.fontWeight = "bold";
        } else if (envDisplay) {
            envDisplay.style.color = "#3498db";
            envDisplay.style.fontWeight = "500";
        }
    }
}

// ----- Map -----
function renderMap(data) {
    // Clear existing layers
    Object.values(incidentMarkers).forEach((m) => {
        if (map.hasLayer(m)) map.removeLayer(m);
    });
    Object.values(resourceMarkers).forEach((m) => {
        if (map.hasLayer(m)) map.removeLayer(m);
    });
    assignmentLinesLayer.clearLayers();
    if (zoneLayer) {
        if (map.hasLayer(zoneLayer)) map.removeLayer(zoneLayer);
        zoneLayer = null;
    }
    for (const k in incidentMarkers) delete incidentMarkers[k];
    for (const k in resourceMarkers) delete resourceMarkers[k];

    // Zone polygon
    if (data.zone_polygon && data.zone_polygon.length > 0) {
        zoneLayer = L.polygon(data.zone_polygon, {
            color: "#e74c3c",
            fillColor: "#e74c3c",
            fillOpacity: 0.06,
            weight: 2,
            dashArray: "8, 6",
        }).addTo(map);
    }

    // Incident markers
    // Pre-calculate ranks for all active incidents
    const sortedActive = [...data.incidents].filter(i => i.status !== "completed").sort((a, b) => {
        const rankA = a.override_rank || 9999;
        const rankB = b.override_rank || 9999;
        if (rankA !== rankB) return rankA - rankB;
        return b.priority_score - a.priority_score;
    });

    data.incidents.forEach((inc) => {
        const isCompleted = (inc.status === "completed");
        const isHighlighted = (inc.id === highlightedIncidentId);
        
        let fillColor = isCompleted ? "#2ecc71" : "#e74c3c";
        if (!isCompleted) {
            const asgn = data.assignments.find(a => a.incident_id === inc.id);
            if (asgn) fillColor = "#f39c12"; // Assigned = Orange
        }
        
        const strokeColor = isCompleted ? "#27ae60" : (isHighlighted ? "#ffeb3b" : "#c0392b");
        const opacity = isCompleted ? 0.45 : 0.9;
        
        let displayRank = "";
        if (!isCompleted) {
            const idx = sortedActive.findIndex(x => x.id === inc.id);
            if (idx !== -1) displayRank = (idx + 1).toString();
        } else {
            displayRank = "✓";
        }

        const iconHtml = `<div style="background-color: ${fillColor}; color: white; border: ${isHighlighted ? '3px' : '2px'} solid ${strokeColor}; border-radius: 50%; width: 24px; height: 24px; display: flex; align-items: center; justify-content: center; font-weight: bold; font-size: 12px; opacity: ${opacity}; box-shadow: ${isHighlighted ? '0 0 10px rgba(0,0,0,0.5)' : 'none'};">${displayRank}</div>`;
        
        const icon = L.divIcon({
            html: iconHtml,
            className: 'custom-incident-icon',
            iconSize: [28, 28],
            iconAnchor: [14, 14]
        });

        const marker = L.marker([inc.lat, inc.lng], { icon: icon, zIndexOffset: isHighlighted ? 1000 : 0 }).addTo(map);

        let popupContent = "<strong>" + escapeHtml(inc.name) + "</strong><br>" +
            "<em>" + escapeHtml(inc.description) + "</em><br>";
        if (isCompleted) {
            popupContent += "<span style='color: #2ecc71; font-weight: 600;'>✓ Task Completed &amp; Resolved</span>";
        } else {
            popupContent += "Priority: " + inc.priority_score + "<br>" +
                "<button type='button' class='popup-complete-btn' onclick='completeIncident(\"" + inc.id + "\")'>✓ Complete Task</button>";
        }

        marker.bindPopup(popupContent);
        incidentMarkers[inc.id] = marker;
        marker.on('click', function () {
            highlightMarker(inc.id);
        });
    });

    // Resource markers (coloured by type)
    data.resources.forEach((r) => {
        const baseColor = RESOURCE_COLORS[r.type] || "#95a5a6";
        let fillColor = baseColor;
        let opacity = 0.9;
        if (r.status === "unavailable") {
            fillColor = "#7f8c8d";
            opacity = 0.45;
        } else if (r.status === "busy") {
            opacity = 0.7;
        }
        const radius = r.type === "hospital" ? 12 : 8;

        const marker = L.circleMarker([r.lat, r.lng], {
            radius: radius,
            fillColor: fillColor,
            color: "#1a2733",
            weight: 2,
            fillOpacity: opacity,
        }).addTo(map);
        marker.bindPopup(
            "<strong>" + r.id + "</strong><br>" +
            "Type: " + r.type + "<br>" +
            "Status: " + r.status
        );
        resourceMarkers[r.id] = marker;
        marker.on('click', function () {
            if (!currentState) return;
            var a = currentState.assignments.find(function (x) {
                return x.resource_id === r.id;
            });
            if (a) highlightMarker(a.incident_id);
        });
    });

    // Fit bounds to show all markers
    const allPoints = [
        ...data.incidents.map((i) => [i.lat, i.lng]),
        ...data.resources.map((r) => [r.lat, r.lng]),
    ];
    if (allPoints.length > 0) {
        map.fitBounds(allPoints, { padding: [30, 30] });
    }
}

// ----- Incident List -----
function renderIncidentList(data, changes) {
    const container = document.getElementById("incident-list");
    container.innerHTML = "";

    // Sort: active incidents first by explicit rank, then by priority descending, completed last
    const sorted = [...data.incidents].sort((a, b) => {
        if (a.status === "completed" && b.status !== "completed") return 1;
        if (a.status !== "completed" && b.status === "completed") return -1;
        
        const rankA = a.override_rank || 9999;
        const rankB = b.override_rank || 9999;
        if (rankA !== rankB) return rankA - rankB;
        
        return b.priority_score - a.priority_score;
    });

    sorted.forEach((inc, index) => {
        const card = document.createElement("div");
        card.className = "incident-card";
        card.id = "card-" + inc.id;

        const isCompleted = (inc.status === "completed");
        if (isCompleted) card.classList.add("completed");

        // Check if changed in simulation
        const change = changes
            ? changes.find((c) => c.incident_id === inc.id)
            : null;
        if (change) card.classList.add("changed");

        // Find assignments
        const incAssignments = data.assignments.filter(
            (a) => a.incident_id === inc.id
        );
        const assignedId = incAssignments.length > 0 ? incAssignments.map(a => a.resource_id).join(", ") : (isCompleted ? "Resolved" : "Unassigned");
        const distance = incAssignments.length > 0 ? incAssignments.map(a => a.distance_km + " km").join(", ") : "";

        // Header row
        const header = document.createElement("div");
        header.className = "incident-header";

        const rankBadge = isCompleted
            ? '<span class="incident-rank completed-rank">✓</span>'
            : '<span class="incident-rank">#' + (index + 1) + "</span>";

        const scoreBadge = isCompleted
            ? '<span class="incident-score completed-score">Done</span>'
            : '<span class="incident-score">' + inc.priority_score + "</span>";

        header.innerHTML =
            rankBadge +
            '<div class="incident-info">' +
                '<div class="incident-name">' + escapeHtml(inc.name) + "</div>" +
                '<div class="incident-desc">' + escapeHtml(inc.description) + "</div>" +
            "</div>" +
            scoreBadge;

        // Breakdown (expandable)
        const breakdown = document.createElement("div");
        breakdown.className = "incident-breakdown";
        breakdown.id = "breakdown-" + inc.id;

        let html = '<div class="breakdown-content">';
        inc.breakdown.forEach((term) => {
            html +=
                '<div class="breakdown-term">' +
                    "<span>" + escapeHtml(term.label) + "</span>" +
                    '<span class="term-value">+' + term.value + "</span>" +
                "</div>";
        });
        html +=
            '<div class="breakdown-total">' +
                "<span>Total Score</span>" +
                "<span>" + inc.priority_score + "</span>" +
            "</div>";
        html +=
            '<div class="incident-assignment">' +
                "Assigned to: <strong>" + assignedId + "</strong>" +
                (distance ? " (" + distance + ")" : "") +
            "</div>";

        if (!isCompleted) {
            html +=
                '<div class="incident-actions-row">' +
                    '<button type="button" class="complete-task-btn" onclick="event.stopPropagation(); completeIncident(\'' + inc.id + '\')">✓ Complete Task &amp; Free Resource</button>' +
                '</div>';
        } else {
            html += '<div class="task-resolved-label">✓ Emergency response completed. Route line dismissed.</div>';
        }

        if (change) {
            html +=
                '<div class="change-label">' +
                    "↻ Reassigned: " + (change.old_resource_id || "Unassigned") +
                    " → " + (change.new_resource_id || "Unassigned") +
                "</div>";
        }
        html += "</div>";
        breakdown.innerHTML = html;

        card.appendChild(header);
        card.appendChild(breakdown);

        // Click: expand breakdown + highlight marker
        header.addEventListener("click", function () {
            toggleBreakdown(inc.id);
            highlightMarker(inc.id);
        });

        container.appendChild(card);
    });
}

function toggleBreakdown(incidentId) {
    const el = document.getElementById("breakdown-" + incidentId);
    if (!el) return;

    // Close all others first
    document.querySelectorAll(".incident-breakdown.expanded").forEach((b) => {
        if (b.id !== "breakdown-" + incidentId) b.classList.remove("expanded");
    });

    el.classList.toggle("expanded");
}

function computeRouteWaypoints(lat1, lng1, lat2, lng2) {
    var dLat = lat2 - lat1;
    var dLng = lng2 - lng1;
    var dist = Math.sqrt(dLat * dLat + dLng * dLng);
    if (dist === 0) return [[lat1, lng1]];
    var offset = dist * 0.15;
    var perpLat = -dLng / dist;
    var perpLng = dLat / dist;
    var wp1Lat = lat1 + dLat / 3 + perpLat * offset;
    var wp1Lng = lng1 + dLng / 3 + perpLng * offset;
    var wp2Lat = lat1 + (2 * dLat) / 3 - perpLat * offset;
    var wp2Lng = lng1 + (2 * dLng) / 3 - perpLng * offset;
    return [
        [lat1, lng1],
        [wp1Lat, wp1Lng],
        [wp2Lat, wp2Lng],
        [lat2, lng2],
    ];
}

function renderAssignmentRoutes() {
    assignmentLinesLayer.clearLayers();
    if (!currentState) return;

    if (showAllRoutes) {
        // Draw route lines for all active assignments
        currentState.assignments.forEach(function (assignment) {
            const inc = currentState.incidents.find(i => i.id === assignment.incident_id);
            const res = currentState.resources.find(r => r.id === assignment.resource_id);
            if (!inc || !res || inc.status === "completed") return;

            const isHighlighted = (assignment.incident_id === highlightedIncidentId);
            const waypoints = computeRouteWaypoints(inc.lat, inc.lng, res.lat, res.lng);
            const lineColor = RESOURCE_COLORS[res.type] || "#3498db";

            L.polyline(waypoints, {
                color: lineColor,
                weight: isHighlighted ? 5 : 3,
                opacity: isHighlighted ? 1.0 : 0.65,
                dashArray: isHighlighted ? "6, 4" : "10, 6",
                lineCap: "round",
                lineJoin: "round",
            }).addTo(assignmentLinesLayer);
        });
    } else if (highlightedIncidentId) {
        // Draw ALL routes for the currently highlighted incident (supports multi-resource)
        const incAssignments = currentState.assignments.filter(a => a.incident_id === highlightedIncidentId);
        incAssignments.forEach(function (assignment) {
            const inc = currentState.incidents.find(i => i.id === assignment.incident_id);
            const res = currentState.resources.find(r => r.id === assignment.resource_id);
            if (inc && res && inc.status !== "completed") {
                const waypoints = computeRouteWaypoints(inc.lat, inc.lng, res.lat, res.lng);
                const lineColor = RESOURCE_COLORS[res.type] || "#3498db";
                const line = L.polyline(waypoints, {
                    color: lineColor,
                    weight: 4,
                    opacity: 0.9,
                    dashArray: "10, 6",
                    lineCap: "round",
                    lineJoin: "round",
                });

                // Safety check for distance_km formatting
                let distStr = "";
                if (typeof assignment.distance_km === 'number') {
                    distStr = `<br>Distance: ${assignment.distance_km.toFixed(1)} km`;
                }
                
                let etaStr = "";
                if (typeof assignment.eta_minutes === 'number') {
                    etaStr = `<br>ETA: ${assignment.eta_minutes} mins (Drive Time)`;
                } else if (typeof assignment.distance_km === 'number') {
                    // Fallback estimation if no ETA
                    etaStr = `<br>Est. ETA: ${Math.round(assignment.distance_km * 2)} mins`;
                }

                line.bindPopup(`<b>Dispatch Route</b><br>${res.name} &rarr; ${inc.name}${distStr}${etaStr}`);
                assignmentLinesLayer.addLayer(line);
            }
        });
    }
}

function highlightMarker(incidentId) {
    // Toggle: if same id clicked again, deselect
    if (incidentId === highlightedIncidentId) {
        highlightedIncidentId = null;
        // Re-render map to reset marker icons
        if (currentState) renderMap(currentState);
        renderAssignmentRoutes();
        document.querySelectorAll(".incident-card.active").forEach(function (c) {
            c.classList.remove("active");
        });
        return;
    }

    // Set new highlight
    highlightedIncidentId = incidentId;
    // Re-render map to apply highlight styling via divIcon
    if (currentState) renderMap(currentState);
    renderAssignmentRoutes();

    document.querySelectorAll(".incident-card.active").forEach(function (c) {
        c.classList.remove("active");
    });
    var card = document.getElementById("card-" + incidentId);
    if (card) card.classList.add("active");
}

// ----- Resource Status -----
function renderResourceStatus(data) {
    const container = document.getElementById("resource-status");
    container.innerHTML = "";

    var types = ["ambulance", "ndrf", "fire", "hospital"];

    types.forEach(function (type) {
        var ofType = data.resources.filter(function (r) {
            return r.type === type;
        });
        var available = ofType.filter(function (r) {
            return r.status === "available";
        }).length;
        var busy = ofType.filter(function (r) {
            return r.status === "busy";
        }).length;
        var unavailable = ofType.filter(function (r) {
            return r.status === "unavailable";
        }).length;

        var row = document.createElement("div");
        row.className = "resource-type-row";
        row.dataset.type = type;

        var countsHTML = '<span class="count-available">' + available + " avail</span>";
        if (busy > 0)
            countsHTML += ' <span class="count-busy">· ' + busy + " busy</span>";
        if (unavailable > 0)
            countsHTML +=
                ' <span class="count-unavailable">· ' + unavailable + " down</span>";

        var isExpanded = expandedResourceTypes.has(type);
        var expandIcon = isExpanded ? "▼" : "▶";

        row.innerHTML =
            '<span class="resource-type-label" style="color:' +
            RESOURCE_COLORS[type] +
            '">' +
            RESOURCE_LABELS[type] +
            "</span>" +
            '<span class="resource-counts">' +
            countsHTML +
            "</span>" +
            '<span class="resource-expand-icon" style="color:' +
            RESOURCE_COLORS[type] +
            '">' +
            expandIcon +
            "</span>";

        var drilldown = document.createElement("div");
        drilldown.className = "resource-drilldown";
        drilldown.id = "drilldown-" + type;
        if (isExpanded) drilldown.classList.add("expanded");

        var drilldownContent = document.createElement("div");
        drilldownContent.className = "drilldown-content";

        ofType.forEach(function (resource) {
            var unitRow = document.createElement("div");
            unitRow.className = "resource-unit-row";
            unitRow.dataset.resourceId = resource.id;

            var statusClass = "unit-status-" + resource.status;
            var statusText = resource.status.charAt(0).toUpperCase() + resource.status.slice(1);

            var html = '<span class="unit-id">' + escapeHtml(resource.id) + "</span>";

            if (resource.status === "busy") {
                var assignment = data.assignments.find(function (a) {
                    return a.resource_id === resource.id;
                });
                var incident = assignment
                    ? data.incidents.find(function (i) {
                        return i.id === assignment.incident_id;
                    })
                    : null;
                var incidentName = incident ? incident.name : "Unknown";
                var distance = assignment
                    ? (typeof assignment.distance_km === 'number' ? assignment.distance_km.toFixed(1) + " km" : "")
                    : "";
                html +=
                    '<span class="unit-status ' +
                    statusClass +
                    '">' +
                    statusText +
                    "</span>" +
                    '<span class="unit-assignment">' +
                    "→ " +
                    escapeHtml(incidentName) +
                    (distance ? ", " + distance : "") +
                    "</span>";
                unitRow.classList.add("clickable");
                unitRow.addEventListener("click", function (e) {
                    e.stopPropagation();
                    if (incident) {
                        highlightMarker(incident.id);
                    }
                });
            } else {
                html +=
                    '<span class="unit-status ' +
                    statusClass +
                    '">' +
                    statusText +
                    "</span>";
            }

            unitRow.innerHTML = html;
            drilldownContent.appendChild(unitRow);
        });

        drilldown.appendChild(drilldownContent);
        row.addEventListener("click", function () {
            toggleResourceDrilldown(type);
        });

        container.appendChild(row);
        container.appendChild(drilldown);
    });
}

function toggleResourceDrilldown(type) {
    const drilldown = document.getElementById("drilldown-" + type);
    const row = document.querySelector('.resource-type-row[data-type="' + type + '"]');
    const icon = row ? row.querySelector(".resource-expand-icon") : null;

    if (!drilldown) return;

    if (drilldown.classList.contains("expanded")) {
        drilldown.classList.remove("expanded");
        expandedResourceTypes.delete(type);
        if (icon) icon.textContent = "▶";
    } else {
        document
            .querySelectorAll(".resource-drilldown.expanded")
            .forEach(function (d) {
                d.classList.remove("expanded");
                var t = d.id.replace("drilldown-", "");
                expandedResourceTypes.delete(t);
                var r = document.querySelector(
                    '.resource-type-row[data-type="' + t + '"]'
                );
                var i = r ? r.querySelector(".resource-expand-icon") : null;
                if (i) i.textContent = "▶";
            });
        drilldown.classList.add("expanded");
        expandedResourceTypes.add(type);
        if (icon) icon.textContent = "▼";
    }
}

// ----- Simulate -----
const PICKER_TYPES = ["ambulance", "ndrf", "fire", "hospital"];

function onSimulate() {
    showPicker();
}

function showPicker() {
    const picker = document.getElementById("resource-picker");
    if (!picker) return;
    renderPicker();
    picker.classList.remove("hidden");
    document.getElementById("simulate-btn").disabled = true;
}

function hidePicker() {
    const picker = document.getElementById("resource-picker");
    if (!picker) return;
    picker.classList.add("hidden");
    document.getElementById("simulate-btn").disabled = false;
}

function renderPicker() {
    const container = document.getElementById("picker-categories");
    if (!container || !currentState) return;
    container.innerHTML = "";

    PICKER_TYPES.forEach(function (type) {
        const ofType = currentState.resources.filter(function (r) {
            return r.type === type;
        });
        if (ofType.length === 0) return;

        const group = document.createElement("div");
        group.className = "picker-category";

        const header = document.createElement("div");
        header.className = "picker-category-header";
        header.style.borderLeftColor = RESOURCE_COLORS[type] || "#95a5a6";
        header.innerHTML =
            '<span class="picker-category-label" style="color:' +
            (RESOURCE_COLORS[type] || "#95a5a6") +
            '">' +
            RESOURCE_LABELS[type] +
            "</span>" +
            '<span class="picker-category-count">' + ofType.length + "</span>";

        const buttons = document.createElement("div");
        buttons.className = "picker-buttons";

        ofType.forEach(function (res) {
            const btn = document.createElement("button");
            btn.className = "picker-resource-btn";
            btn.type = "button";
            btn.dataset.resourceId = res.id;
            btn.dataset.resourceType = res.type;
            const statusClass = "picker-status-" + res.status;
            btn.innerHTML =
                '<span class="picker-resource-id">' + escapeHtml(res.id) + "</span>" +
                '<span class="picker-resource-status ' + statusClass + '">' +
                res.status + "</span>";

            if (res.status === "unavailable") {
                btn.classList.add("selected");
            }
            if (res.type === "hospital") {
                btn.classList.add("picker-hospital-disabled");
                btn.title = "Hospitals are not dispatchable";
                btn.disabled = true;
            }

            btn.addEventListener("click", function () {
                if (btn.disabled) return;
                btn.classList.toggle("selected");
            });

            buttons.appendChild(btn);
        });

        group.appendChild(header);
        group.appendChild(buttons);
        container.appendChild(group);
    });
}

function clearPickerSelection() {
    const container = document.getElementById("picker-categories");
    if (!container) return;
    container.querySelectorAll(".picker-resource-btn.selected").forEach(function (b) {
        b.classList.remove("selected");
    });
}

function getSelectedUnavailableIds() {
    const container = document.getElementById("picker-categories");
    if (!container) return [];
    const ids = [];
    container.querySelectorAll(".picker-resource-btn.selected").forEach(function (b) {
        if (!b.disabled) ids.push(b.dataset.resourceId);
    });
    return ids;
}

async function runPickerAllocation() {
    const ids = getSelectedUnavailableIds();
    const runBtn = document.getElementById("picker-run-btn");
    runBtn.disabled = true;
    runBtn.textContent = "Running…";

    try {
        const res = await fetch("/api/allocate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ unavailable_resource_ids: ids }),
        });
        const result = await res.json();

        currentState = result.state;
        highlightedIncidentId = null;
        renderAll(currentState, result.changes);

        // Reflect the new statuses in the picker buttons
        renderPicker();

        // Show changes summary
        const changesDiv = document.getElementById("changes-display");
        if (result.changes && result.changes.length > 0) {
            changesDiv.innerHTML = result.changes
                .map(function (c) {
                    return (
                        "↻ " +
                        escapeHtml(c.incident_name) + ": " +
                        (c.old_resource_id || "Unassigned") +
                        " → " +
                        (c.new_resource_id || "Unassigned")
                    );
                })
                .join("<br>");
        } else {
            changesDiv.innerHTML =
                '<span class="picker-no-change">No reassignments needed.</span>';
        }

        // Update simulate button label to reflect selection
        const simBtn = document.getElementById("simulate-btn");
        if (ids.length === 0) {
            simBtn.textContent = "Simulate Resource Unavailable";
        } else {
            simBtn.textContent = "Simulate (" + ids.length + " down)";
        }
        document.getElementById("reset-btn").disabled = false;
    } catch (err) {
        console.error("Allocate failed:", err);
    } finally {
        runBtn.disabled = false;
        runBtn.textContent = "Run Allocation";
    }
}

// ----- Reset -----
async function onReset() {
    var resetBtn = document.getElementById("reset-btn");
    resetBtn.disabled = true;

    try {
        var res = await fetch("/api/reset", { method: "POST" });
        currentState = await res.json();
        highlightedIncidentId = null;

        renderAll(currentState);

        // Enable reset button if changes exist
        const resetBtn = document.getElementById("reset-btn");
        if (resetBtn) resetBtn.disabled = false;

        // Restore buttons
        document.getElementById("simulate-btn").textContent = "▶ Run Sim Step";
        document.getElementById("simulate-btn").disabled = false;
        document.getElementById("changes-display").innerHTML = "";

        // Refresh the picker (in case it is open)
        const picker = document.getElementById("resource-picker");
        if (picker && !picker.classList.contains("hidden")) {
            renderPicker();
        }

        // Clear NLP fields
        const aiInput = document.getElementById("ai-overwrite-input");
        if (aiInput) aiInput.value = "";
        const aiStatus = document.getElementById("ai-status-msg");
        if (aiStatus) aiStatus.textContent = "Simulation completely reset.";

        // Regenerate AI Plan for clean state
        fetchAiPlan();
        
        resetBtn.disabled = false;
    } catch (err) {
        resetBtn.disabled = false;
        console.error("Reset failed:", err);
    }
}

// ----- Utility -----
function escapeHtml(text) {
    var div = document.createElement("div");
    div.appendChild(document.createTextNode(text));
    return div.innerHTML;
}

// ----- Task Completion (Karyon Req 1) -----
async function completeIncident(incidentId) {
    try {
        const res = await fetch("/api/incident/complete", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ incident_id: incidentId })
        });
        const result = await res.json();
        currentState = result.state;
        if (highlightedIncidentId === incidentId) {
            highlightedIncidentId = null;
        }
        renderAll(currentState, result.changes);

        // Update changes log
        const changesDiv = document.getElementById("changes-display");
        if (changesDiv && result.summary) {
            changesDiv.innerHTML = `<span class="task-resolved-summary">✓ ${escapeHtml(result.summary)}</span>`;
        }

        // Keep AI Plan in sync
        fetchAiPlan();
    } catch (err) {
        console.error("Failed to complete incident:", err);
    }
}

// ----- API Key Management -----
function initApiKey() {
    const key = localStorage.getItem("gemini_api_key");
    if (key) {
        const input = document.getElementById("api-key-input");
        if (input) input.value = key;
    }
}

function saveApiKey() {
    const input = document.getElementById("api-key-input");
    if (!input) return;
    const key = input.value.trim();
    if (key) {
        localStorage.setItem("gemini_api_key", key);
        alert("API Key saved to browser local storage.");
        fetchAiPlan(true);
    } else {
        localStorage.removeItem("gemini_api_key");
        alert("API Key cleared.");
    }
}

// ----- AI Tactical Plan (Karyon Req 3) -----
async function fetchAiPlan(force = false) {
    const planContent = document.getElementById("ai-plan-content");
    if (!planContent) return;

    if (force) {
        planContent.innerHTML = '<p class="loading-message">Generating operational plan briefing with Gemini…</p>';
    }

    try {
        const apiKey = localStorage.getItem("gemini_api_key") || "";
        const res = await fetch("/api/ai/plan", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ api_key: apiKey })
        });
        const data = await res.json();
        if (data && data.plan) {
            planContent.innerHTML = renderMarkdown(data.plan);
            // Pre-fill overwrite input hint or placeholder if empty
            const overwriteInput = document.getElementById("ai-overwrite-input");
            if (overwriteInput && !overwriteInput.value) {
                overwriteInput.placeholder = "Enter plan edits or commands, e.g. 'Move Fatima to priority #1' or 'Assign N01 to Fatima'";
            }
        }
    } catch (err) {
        console.error("Failed to load AI plan:", err);
        planContent.innerHTML = '<p class="error-message">Unable to load tactical plan.</p>';
    }
}

// ----- NLP Plan Overwrite & Bidirectional Sync (Karyon Req 4) -----
async function applyAiOverwrite() {
    const input = document.getElementById("ai-overwrite-input");
    const applyBtn = document.getElementById("ai-apply-btn");
    const statusMsg = document.getElementById("ai-status-msg");
    const text = input ? input.value.trim() : "";

    if (!text) {
        if (statusMsg) statusMsg.textContent = "Please enter an instruction or plan edit.";
        return;
    }

    applyBtn.disabled = true;
    applyBtn.textContent = "Applying…";
    if (statusMsg) statusMsg.textContent = "Processing through NLP…";

    try {
        const apiKey = localStorage.getItem("gemini_api_key") || "";
        const res = await fetch("/api/ai/apply", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ command: text, api_key: apiKey })
        });
        const result = await res.json();

        currentState = result.state;
        renderAll(currentState, result.changes);

        // Update simulation/changes feedback
        const changesDiv = document.getElementById("changes-display");
        if (changesDiv && result.summary) {
            changesDiv.innerHTML = `<span class="ai-applied-summary">✓ ${escapeHtml(result.summary)}</span>`;
        }

        if (statusMsg) {
            statusMsg.textContent = `Applied (${result.actions_applied ? result.actions_applied.length : 0} action(s))`;
            setTimeout(() => { statusMsg.textContent = ""; }, 4000);
        }

        // Clear input and refresh AI Plan briefing to reflect new state
        if (input) input.value = "";
        fetchAiPlan();
    } catch (err) {
        console.error("Apply overwrite failed:", err);
        if (statusMsg) statusMsg.textContent = "Error applying changes.";
    } finally {
        applyBtn.disabled = false;
        applyBtn.textContent = "Apply Overwrite";
    }
}

// Lightweight Markdown Formatter
function renderMarkdown(md) {
    if (!md) return "";
    let html = escapeHtml(md);

    // Headers (order matters: ### before ## before #)
    html = html.replace(/^### (.*$)/gim, '<h4 class="md-h3">$1</h4>');
    html = html.replace(/^## (.*$)/gim, '<h3 class="md-h2">$1</h3>');
    html = html.replace(/^# (.*$)/gim, '<h2 class="md-h1">$1</h2>');

    // Bold & Italics
    html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');

    // Bullet points → list items
    html = html.replace(/^\- (.*$)/gim, '<li class="md-li">$1</li>');

    // Wrap consecutive <li> runs in <ul> tags
    html = html.replace(/((?:<li class="md-li">.*?<\/li>\s*)+)/g, '<ul class="md-ul">$1</ul>');

    // Paragraph breaks and line breaks
    html = html.replace(/\n\n/g, '<p class="md-p"></p>');
    html = html.replace(/\n/g, '<br>');

    return html;
}

