/* ============================================================
   ResQ — Dashboard Logic
   Leaflet map + ranked incident list + resource status +
   simulate/reset controls.
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
    document.getElementById("simulate-btn").addEventListener("click", onSimulate);
    document.getElementById("reset-btn").addEventListener("click", onReset);
    document.getElementById("picker-cancel-btn").addEventListener("click", hidePicker);
    document.getElementById("picker-clear-btn").addEventListener("click", clearPickerSelection);
    document.getElementById("picker-run-btn").addEventListener("click", runPickerAllocation);

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

    // Incident markers (red circles)
    data.incidents.forEach((inc) => {
        const marker = L.circleMarker([inc.lat, inc.lng], {
            radius: 10,
            fillColor: "#e74c3c",
            color: "#c0392b",
            weight: 2,
            fillOpacity: 0.9,
        }).addTo(map);
        marker.bindPopup(
            "<strong>" + escapeHtml(inc.name) + "</strong><br>" +
            "<em>" + escapeHtml(inc.description) + "</em><br>" +
            "Priority: " + inc.priority_score
        );
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

    // Sort by priority descending
    const sorted = [...data.incidents].sort(
        (a, b) => b.priority_score - a.priority_score
    );

    sorted.forEach((inc, index) => {
        const card = document.createElement("div");
        card.className = "incident-card";
        card.id = "card-" + inc.id;

        // Check if changed in simulation
        const change = changes
            ? changes.find((c) => c.incident_id === inc.id)
            : null;
        if (change) card.classList.add("changed");

        // Find assignment
        const assignment = data.assignments.find(
            (a) => a.incident_id === inc.id
        );
        const assignedId = assignment ? assignment.resource_id : "Unassigned";
        const distance = assignment ? assignment.distance_km + " km" : "";

        // Header row
        const header = document.createElement("div");
        header.className = "incident-header";
        header.innerHTML =
            '<span class="incident-rank">#' + (index + 1) + "</span>" +
            '<div class="incident-info">' +
                '<div class="incident-name">' + escapeHtml(inc.name) + "</div>" +
                '<div class="incident-desc">' + escapeHtml(inc.description) + "</div>" +
            "</div>" +
            '<span class="incident-score">' + inc.priority_score + "</span>";

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
                "<span>Total</span>" +
                "<span>" + inc.priority_score + "</span>" +
            "</div>";
        html +=
            '<div class="incident-assignment">' +
                "Assigned to: <strong>" + assignedId + "</strong>" +
                (distance ? " (" + distance + ")" : "") +
            "</div>";
        if (change) {
            html +=
                '<div class="change-label">' +
                    "↻ Reassigned: " + change.old_resource_id +
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

function drawAssignmentPath(incidentId) {
    assignmentLinesLayer.clearLayers();
    if (!currentState) return;
    var assignment = currentState.assignments.find(function (a) {
        return a.incident_id === incidentId;
    });
    if (!assignment) return;
    var inc = currentState.incidents.find(function (i) {
        return i.id === incidentId;
    });
    var res = currentState.resources.find(function (r) {
        return r.id === assignment.resource_id;
    });
    if (!inc || !res) return;
    var waypoints = computeRouteWaypoints(inc.lat, inc.lng, res.lat, res.lng);
    var lineColor = RESOURCE_COLORS[res.type] || "#3498db";
    L.polyline(waypoints, {
        color: lineColor,
        weight: 3,
        opacity: 0.85,
        dashArray: "10, 6",
        lineCap: "round",
        lineJoin: "round",
    }).addTo(assignmentLinesLayer);
}

function highlightMarker(incidentId) {
    // Revert previous
    if (highlightedIncidentId && incidentMarkers[highlightedIncidentId]) {
        incidentMarkers[highlightedIncidentId].setStyle({
            radius: 10,
            fillColor: "#e74c3c",
            color: "#c0392b",
            weight: 2,
        });
    }

    // Toggle: if same id clicked again, just deselect
    if (incidentId === highlightedIncidentId) {
        highlightedIncidentId = null;
        assignmentLinesLayer.clearLayers();
        document.querySelectorAll(".incident-card.active").forEach(function (c) {
            c.classList.remove("active");
        });
        return;
    }

    // Highlight new
    if (incidentMarkers[incidentId]) {
        incidentMarkers[incidentId].setStyle({
            radius: 14,
            fillColor: "#ff6b6b",
            color: "#ffffff",
            weight: 3,
        });
        highlightedIncidentId = incidentId;
        drawAssignmentPath(incidentId);
        document.querySelectorAll(".incident-card.active").forEach(function (c) {
            c.classList.remove("active");
        });
        var card = document.getElementById("card-" + incidentId);
        if (card) card.classList.add("active");
    }
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
                    ? assignment.distance_km.toFixed(2) + " km"
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

        // Restore buttons
        document.getElementById("simulate-btn").textContent =
            "Simulate Resource Unavailable";
        document.getElementById("simulate-btn").disabled = false;
        document.getElementById("changes-display").innerHTML = "";

        // Refresh the picker (in case it is open)
        const picker = document.getElementById("resource-picker");
        if (picker && !picker.classList.contains("hidden")) {
            renderPicker();
        }
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
