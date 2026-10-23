/**
 * RESQ PULSE — Geospatial Command Center: Live Fleet Radar & Fastest-Route Navigation
 * 
 * Features:
 * - Live vehicle telemetry polling with concurrency guards (prevents overlapping requests)
 * - Road route polylines via OSRM / configurable routing provider adapter
 * - Real-time ETA in minutes, clock arrival time, and distance remaining
 * - Alternative route comparisons and "Fastest Available Route" switcher
 * - Non-fabricated traffic disclosures and telemetry freshness tracking
 * - Smooth marker animations and keyboard-accessible UI
 */

let mapInstance = null;
let ambulanceMarkers = {};
let hospitalMarkers = {};
let incidentMarkers = {};
let routePolylines = [];
let routeAlternativesData = [];
let selectedRouteIndex = 0;

let selectedAmbulanceId = null;
let isFetchingFeed = false;
let pollingIntervalTimer = null;
const POLL_INTERVAL_MS = 4000;

let simulationInterval = null;
let isSimulationActive = false;

document.addEventListener("DOMContentLoaded", () => {
  const mapElement = document.getElementById("trackingMap");
  if (mapElement) {
    initOperationsMap();
  }
});

/* --------------------------------------------------------------------------
   Map Initialization
   -------------------------------------------------------------------------- */
function initOperationsMap() {
  try {
    // Default center: Bengaluru metropolitan area
    mapInstance = L.map("trackingMap", {
      zoomControl: true,
      attributionControl: true,
      preferCanvas: true,
    }).setView([12.9716, 77.5946], 12);

    // OpenStreetMap Tile Layer
    const tileLayer = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    });

    tileLayer.addTo(mapInstance);

    tileLayer.on("tileerror", (error) => {
      console.warn("Tile server error or network offline:", error);
      const errBanner = document.getElementById("mapTileError");
      if (errBanner) errBanner.style.display = "block";
    });

    // Initial load
    fetchLiveFeed(true);

    // Start polling loop with overlap protection
    pollingIntervalTimer = setInterval(() => {
      fetchLiveFeed(false);
    }, POLL_INTERVAL_MS);

    // Bind UI buttons and dropdowns
    bindMapControls();
  } catch (err) {
    console.error("Failed to initialize Leaflet operations radar:", err);
    const container = document.getElementById("trackingMap");
    if (container) {
      container.innerHTML = `
        <div style="padding: 40px; text-align: center; color: #ef4444;">
          <h3>Geospatial Radar Initialization Error</h3>
          <p>Leaflet could not initialize. Please verify network access for OpenStreetMap tiles.</p>
        </div>
      `;
    }
  }
}

/* --------------------------------------------------------------------------
   Custom SVG Icons
   -------------------------------------------------------------------------- */
function createAmbulanceIcon(status, isSelected = false) {
  let color = "#10b981"; // Available (Teal/Emerald)
  let pulseClass = "pulse-available";

  if (status === "Busy") {
    color = "#f59e0b"; // Amber
    pulseClass = "pulse-busy";
  } else if (status === "Out of Service") {
    color = "#64748b"; // Slate
    pulseClass = "pulse-none";
  }

  const borderStyle = isSelected ? "3px solid #38bdf8" : "2px solid #ffffff";
  const scaleStyle = isSelected ? "transform: scale(1.15);" : "";

  const svgHtml = `
    <div class="custom-map-marker ${pulseClass}" style="background-color: ${color}; border: ${borderStyle}; ${scaleStyle}">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M19 17h2c.6 0 1-.4 1-1v-3c0-.9-.7-1.7-1.5-1.9C18.7 10.6 16 10 16 10s-1.3-1.4-2.2-2.3c-.5-.4-1.1-.7-1.8-.7H5c-.6 0-1 .4-1 1v9c0 .6.4 1 1 1h2"/>
        <circle cx="7" cy="17" r="2"/>
        <path d="M9 17h6"/>
        <circle cx="17" cy="17" r="2"/>
      </svg>
    </div>
  `;

  return L.divIcon({
    html: svgHtml,
    className: "map-div-icon",
    iconSize: [36, 36],
    iconAnchor: [18, 18],
    popupAnchor: [0, -18],
  });
}

function createHospitalIcon() {
  const svgHtml = `
    <div class="custom-hospital-marker">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M12 6v12M6 12h12"/>
      </svg>
    </div>
  `;

  return L.divIcon({
    html: svgHtml,
    className: "map-div-icon",
    iconSize: [32, 32],
    iconAnchor: [16, 16],
    popupAnchor: [0, -16],
  });
}

function createEmergencyIcon(priority = "High") {
  const color = priority === "High" ? "#ef4444" : priority === "Medium" ? "#f59e0b" : "#3b82f6";
  const svgHtml = `
    <div class="custom-emergency-marker" style="background-color: ${color};">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="10"/>
        <line x1="12" y1="8" x2="12" y2="12"/>
        <line x1="12" y1="16" x2="12.01" y2="16"/>
      </svg>
    </div>
  `;

  return L.divIcon({
    html: svgHtml,
    className: "map-div-icon",
    iconSize: [32, 32],
    iconAnchor: [16, 16],
    popupAnchor: [0, -16],
  });
}

function createDestinationHospitalIcon() {
  const svgHtml = `
    <div class="custom-hospital-marker" style="background-color: #0284c7; border: 2px solid #38bdf8; box-shadow: 0 0 14px rgba(56, 189, 248, 0.8);">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M12 6v12M6 12h12"/>
      </svg>
    </div>
  `;

  return L.divIcon({
    html: svgHtml,
    className: "map-div-icon",
    iconSize: [34, 34],
    iconAnchor: [17, 17],
    popupAnchor: [0, -17],
  });
}

/* --------------------------------------------------------------------------
   Data Ingestion & Feed Polling
   -------------------------------------------------------------------------- */
async function fetchLiveFeed(isInitial = false) {
  if (isFetchingFeed) return;
  isFetchingFeed = true;

  try {
    const res = await fetch("/api/v1/tracking/live");
    if (!res.ok) throw new Error(`Live telemetry responded with HTTP ${res.status}`);
    const data = await res.json();

    const ambulances = data.ambulances || [];
    const hospitals = data.hospitals || [];

    updateAmbulancesOnMap(ambulances);
    updateHospitalsOnMap(hospitals);

    const updatedClock = document.getElementById("lastUpdatedClock");
    if (updatedClock) {
      updatedClock.textContent = data.timestamp ? `Updated: ${data.timestamp.split(" ")[1]}` : "Live";
    }

    // If an ambulance is currently selected, refresh its side panel telemetry
    if (selectedAmbulanceId) {
      const currentAmb = ambulances.find((a) => a.id === selectedAmbulanceId);
      if (currentAmb) {
        // Re-render side panel without resetting route alternative selection
        renderSidePanelTelemetry(currentAmb, false);

        // Update route polyline if vehicle stepped
        if (currentAmb.active_incident && currentAmb.active_incident.route_geometry) {
          updatePrimaryRouteGeometry(currentAmb);
        }
      }
    } else if (isInitial && ambulances.length > 0) {
      // On initial load, auto-select the first busy unit with active call if one exists
      const busyUnit = ambulances.find((a) => a.active_incident);
      if (busyUnit) {
        selectAmbulance(busyUnit, false);
      }
    }
  } catch (err) {
    console.warn("Live telemetry poll failed (will retry):", err);
    const updatedClock = document.getElementById("lastUpdatedClock");
    if (updatedClock) updatedClock.textContent = "Reconnecting...";
  } finally {
    isFetchingFeed = false;
  }
}

/* --------------------------------------------------------------------------
   Ambulance Markers Management
   -------------------------------------------------------------------------- */
function updateAmbulancesOnMap(ambulances) {
  ambulances.forEach((amb) => {
    const { id, code, driver, phone, vehicle, type, status, lat, lon, last_update, active_incident, is_stale } = amb;
    const isSelected = selectedAmbulanceId === id;

    const popupContent = `
      <div class="map-popup-card">
        <div class="popup-title">
          <span>${code}</span>
          <span class="badge badge-${status.toLowerCase().replace(/\s+/g, '-')}">${status}</span>
        </div>
        <div class="popup-row"><strong>Type:</strong> ${type} &bull; ${vehicle}</div>
        <div class="popup-row"><strong>Driver:</strong> ${driver} (${phone})</div>
        <div class="popup-row"><strong>GPS Freshness:</strong> ${formatFreshnessText(last_update, is_stale)}</div>
        ${
          active_incident
            ? `<div class="popup-active-incident">
                 🚨 <strong>Call:</strong> ${active_incident.code} (${active_incident.status})<br>
                 <strong>ETA:</strong> ${active_incident.eta_clock || active_incident.duration_minutes + ' min'} (${active_incident.distance_km} km)
               </div>`
            : `<div class="popup-row" style="color: #10b981;">✓ Unit Available on Standby</div>`
        }
        <div style="margin-top: 10px; display: flex; gap: 6px;">
          <button type="button" class="btn btn-primary btn-sm" onclick="selectAmbulanceById(${id})" style="font-size: 11px; padding: 3px 8px;">
            Inspect Telemetry
          </button>
          <a href="/ambulances/${id}" class="popup-link-btn" style="font-size: 11px; padding: 3px 8px;">Profile</a>
        </div>
      </div>
    `;

    if (ambulanceMarkers[id]) {
      // Smooth coordinate update
      ambulanceMarkers[id].setLatLng([lat, lon]);
      ambulanceMarkers[id].setIcon(createAmbulanceIcon(status, isSelected));
      ambulanceMarkers[id].setPopupContent(popupContent);
      ambulanceMarkers[id]._ambData = amb;
    } else {
      const marker = L.marker([lat, lon], {
        icon: createAmbulanceIcon(status, isSelected),
        title: `${code} (${status})`,
      }).bindPopup(popupContent);

      marker._ambData = amb;
      marker.on("click", () => {
        selectAmbulance(marker._ambData, true);
      });

      marker.addTo(mapInstance);
      ambulanceMarkers[id] = marker;
    }
  });
}

function updateHospitalsOnMap(hospitals) {
  hospitals.forEach((hosp) => {
    const { id, name, address, contact, lat, lon, services } = hosp;

    if (!hospitalMarkers[id]) {
      const popupContent = `
        <div class="map-popup-card">
          <div class="popup-title" style="color: #38bdf8;">🏥 ${name}</div>
          <div class="popup-row" style="font-size: 11px; color: #94a3b8;">${address}</div>
          <div class="popup-row"><strong>Direct Line:</strong> ${contact}</div>
          <div class="popup-row"><strong>Trauma Services:</strong> ${services}</div>
          <div class="popup-demo-tag">Registered Emergency Receiving Center</div>
        </div>
      `;

      const marker = L.marker([lat, lon], {
        icon: createHospitalIcon(),
        title: name,
      }).bindPopup(popupContent);

      marker.addTo(mapInstance);
      hospitalMarkers[id] = marker;
    }
  });
}

/* --------------------------------------------------------------------------
   Selection, Route Rendering & Alternative Routes
   -------------------------------------------------------------------------- */
function selectAmbulanceById(id) {
  if (ambulanceMarkers[id] && ambulanceMarkers[id]._ambData) {
    selectAmbulance(ambulanceMarkers[id]._ambData, true);
  }
}

function selectAmbulance(amb, shouldZoom = true) {
  selectedAmbulanceId = amb.id;
  selectedRouteIndex = 0;

  // Sync focus dropdown
  const focusSelect = document.getElementById("focusAmbulanceSelect");
  if (focusSelect) {
    focusSelect.value = String(amb.id);
  }

  // Refresh marker icon styles
  Object.keys(ambulanceMarkers).forEach((mid) => {
    const m = ambulanceMarkers[mid];
    if (m && m._ambData) {
      m.setIcon(createAmbulanceIcon(m._ambData.status, Number(mid) === amb.id));
    }
  });

  // Render Telemetry & ETA Side Panel
  renderSidePanelTelemetry(amb, true);

  // Clear previous route polylines & incident markers
  clearRouteLayers();

  if (amb.active_incident) {
    renderActiveMissionRoutes(amb, shouldZoom);
  } else if (shouldZoom && ambulanceMarkers[amb.id]) {
    mapInstance.flyTo(ambulanceMarkers[amb.id].getLatLng(), 15, { duration: 1.0 });
  }
}

function clearRouteLayers() {
  routePolylines.forEach((poly) => {
    try { mapInstance.removeLayer(poly); } catch (e) {}
  });
  routePolylines = [];
  routeAlternativesData = [];

  Object.values(incidentMarkers).forEach((marker) => {
    try { mapInstance.removeLayer(marker); } catch (e) {}
  });
  incidentMarkers = {};
}

async function renderActiveMissionRoutes(amb, shouldZoom) {
  const incident = amb.active_incident;
  if (!incident) return;

  // 1. Emergency Pickup Scene Marker
  const pickupMarker = L.marker([incident.lat, incident.lon], {
    icon: createEmergencyIcon(incident.priority),
    title: `Pickup Incident: ${incident.code}`,
  }).bindPopup(`
    <div class="map-popup-card">
      <div class="popup-title" style="color: #ef4444;">🚨 Incident ${incident.code}</div>
      <div class="popup-row"><strong>Pickup Address:</strong> ${incident.pickup_address}</div>
      <div class="popup-row"><strong>Priority:</strong> ${incident.priority}</div>
      <div class="popup-row"><strong>Status:</strong> ${incident.status}</div>
      <a href="/emergencies/${incident.id}" class="popup-link-btn" style="margin-top: 6px;">Open Incident Command</a>
    </div>
  `);
  pickupMarker.addTo(mapInstance);
  incidentMarkers["pickup"] = pickupMarker;

  // 2. Destination Hospital Marker (if designated)
  if (incident.destination_hospital && incident.destination_hospital.lat && incident.destination_hospital.lon) {
    const hosp = incident.destination_hospital;
    const destMarker = L.marker([hosp.lat, hosp.lon], {
      icon: createDestinationHospitalIcon(),
      title: `Destination Hospital: ${hosp.name}`,
    }).bindPopup(`
      <div class="map-popup-card">
        <div class="popup-title" style="color: #38bdf8;">🏥 Designated Facility: ${hosp.name}</div>
        <div class="popup-row">Assigned receiving trauma center for call ${incident.code}</div>
      </div>
    `);
    destMarker.addTo(mapInstance);
    incidentMarkers["destination"] = destMarker;
  }

  // 3. Draw Pre-calculated Primary Route Polyline (instant display without waiting)
  if (incident.route_geometry && incident.route_geometry.length > 0) {
    drawPolylines([
      {
        summary: "Primary Fastest Route",
        distance_km: incident.distance_km,
        duration_minutes: incident.duration_minutes,
        geometry: incident.route_geometry,
        is_recommended: true,
      }
    ]);
  }

  // 4. Query Route Engine for Live Alternatives & Duration Comparison
  try {
    const routeUrl = `/api/v1/routes/calculate?origin_lat=${amb.lat}&origin_lon=${amb.lon}&dest_lat=${incident.lat}&dest_lon=${incident.lon}`;
    const res = await fetch(routeUrl);
    if (res.ok) {
      const routeData = await res.json();
      buildRouteAlternatives(amb, routeData);
    }
  } catch (err) {
    console.warn("Could not fetch route alternatives (using primary geometry):", err);
  }

  // 5. Fit bounds to mission envelope
  if (shouldZoom && routePolylines.length > 0) {
    try {
      const group = new L.featureGroup([
        ambulanceMarkers[amb.id],
        pickupMarker,
        ...routePolylines,
      ]);
      mapInstance.fitBounds(group.getBounds().pad(0.18));
    } catch (e) {}
  }
}

function buildRouteAlternatives(amb, routeData) {
  const routes = [];

  if (routeData.recommended_route && routeData.recommended_route.geometry) {
    routes.push({
      summary: routeData.recommended_route.summary || "Fastest Available Road Route",
      distance_km: routeData.recommended_route.distance_km || 0.0,
      duration_minutes: routeData.recommended_route.duration_traffic_minutes || routeData.recommended_route.duration_minutes || 0.0,
      geometry: routeData.recommended_route.geometry,
      is_recommended: true,
      provider: routeData.provider_name,
      is_traffic: routeData.is_traffic_aware,
      disclaimer: routeData.disclaimer,
    });
  }

  if (routeData.alternatives && Array.isArray(routeData.alternatives)) {
    routeData.alternatives.forEach((alt, idx) => {
      if (alt.geometry && alt.geometry.length > 0) {
        routes.push({
          summary: alt.summary || `Alternative Route ${idx + 1}`,
          distance_km: alt.distance_km || 0.0,
          duration_minutes: alt.duration_traffic_minutes || alt.duration_minutes || 0.0,
          geometry: alt.geometry,
          is_recommended: false,
          provider: routeData.provider_name,
        });
      }
    });
  }

  if (routes.length > 0) {
    routeAlternativesData = routes;
    drawPolylines(routes);
    renderSidePanelTelemetry(amb, false);
  }
}

function drawPolylines(routes) {
  // Remove existing lines
  routePolylines.forEach((p) => {
    try { mapInstance.removeLayer(p); } catch (e) {}
  });
  routePolylines = [];

  routes.forEach((route, idx) => {
    const isSelected = idx === selectedRouteIndex;

    const style = isSelected
      ? {
          color: "#14b8a6", // Solid vibrant teal for active/fastest route
          weight: 5,
          opacity: 0.92,
          lineJoin: "round",
          lineCap: "round",
        }
      : {
          color: "#94a3b8", // Dashed slate for alternatives
          weight: 4,
          opacity: 0.65,
          dashArray: "6, 8",
          lineJoin: "round",
        };

    const polyline = L.polyline(route.geometry, style);
    polyline.bindTooltip(
      `<strong>${route.summary}</strong><br>${route.duration_minutes.toFixed(0)} min &bull; ${route.distance_km.toFixed(1)} km`,
      { sticky: true }
    );

    polyline.on("click", () => {
      switchActiveRoute(idx);
    });

    polyline.addTo(mapInstance);
    routePolylines.push(polyline);
  });
}

function switchActiveRoute(routeIdx) {
  if (!routeAlternativesData[routeIdx]) return;
  selectedRouteIndex = routeIdx;

  drawPolylines(routeAlternativesData);

  const amb = ambulanceMarkers[selectedAmbulanceId]?._ambData;
  if (amb) {
    renderSidePanelTelemetry(amb, false);
  }

  if (typeof showToast === "function") {
    const sel = routeAlternativesData[routeIdx];
    showToast(`Switched navigation view to: ${sel.summary} (~${sel.duration_minutes.toFixed(0)} mins)`, "info");
  }
}

function selectFastestRoute() {
  if (routeAlternativesData.length === 0) return;

  let minIdx = 0;
  let minDuration = routeAlternativesData[0].duration_minutes;

  routeAlternativesData.forEach((r, idx) => {
    if (r.duration_minutes < minDuration) {
      minDuration = r.duration_minutes;
      minIdx = idx;
    }
  });

  switchActiveRoute(minIdx);
}

function updatePrimaryRouteGeometry(amb) {
  if (routePolylines.length > 0 && amb.active_incident && amb.active_incident.route_geometry) {
    // Only update if no alternatives were manually chosen
    if (selectedRouteIndex === 0) {
      routePolylines[0].setLatLngs(amb.active_incident.route_geometry);
    }
  }
}

/* --------------------------------------------------------------------------
   Side Panel Telemetry & ETA Inspector
   -------------------------------------------------------------------------- */
function renderSidePanelTelemetry(amb, isFullReset = false) {
  const panel = document.getElementById("selectedAmbulancePanel");
  if (!panel) return;

  const incident = amb.active_incident;
  const activeRoute = routeAlternativesData[selectedRouteIndex] || (incident ? {
    summary: "Fastest Available Road Route",
    distance_km: incident.distance_km,
    duration_minutes: incident.duration_minutes,
    is_recommended: true,
  } : null);

  const etaMinutes = activeRoute ? Math.round(activeRoute.duration_minutes) : null;
  const etaClock = incident ? incident.eta_clock : "Pending";
  const distanceKm = activeRoute ? activeRoute.distance_km.toFixed(1) : (incident ? incident.distance_km.toFixed(1) : "0.0");

  const freshness = formatFreshnessBadge(amb.last_update, amb.is_stale);

  panel.innerHTML = `
    <!-- Vehicle Header -->
    <div class="selected-amb-header">
      <div>
        <h4 style="font-size: 16px; font-weight: 800; font-family: monospace; color: #fff; margin: 0;">${amb.code}</h4>
        <div style="font-size: 11px; color: var(--text-muted); margin-top: 2px;">${amb.type} &bull; ${amb.vehicle}</div>
      </div>
      <span class="badge badge-${amb.status.toLowerCase().replace(/\s+/g, '-')}">${amb.status}</span>
    </div>

    <!-- Active Call ETA Hero (if dispatched) -->
    ${
      incident
        ? `
        <div style="margin-top: 12px; margin-bottom: 14px;">
          <div style="background: linear-gradient(135deg, rgba(20, 184, 166, 0.12), rgba(56, 189, 248, 0.08)); border: 1px solid rgba(20, 184, 166, 0.3); border-radius: var(--radius-sm); padding: 14px; text-align: center;">
            <div style="font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; color: var(--accent-teal);">
              ESTIMATED TIME OF ARRIVAL
            </div>
            <div style="font-size: 36px; font-weight: 800; color: var(--accent-teal); line-height: 1.1; margin-top: 4px;">
              ${etaMinutes !== null ? etaMinutes + " min" : "Calculating..."}
            </div>
            <div style="font-size: 12px; font-weight: 600; color: #f8fafc; margin-top: 4px;">
              Est. Arrival Clock: <strong>${etaClock}</strong> &bull; ${distanceKm} km
            </div>
            <div style="font-size: 10px; color: var(--text-muted); margin-top: 6px;">
              Route Mode: <strong style="color: #94a3b8;">${incident.eta_type_label || 'Provider Road Estimate (OSRM)'}</strong>
            </div>
          </div>

          <!-- Non-fabricated Traffic Disclosure -->
          <div style="margin-top: 8px; padding: 6px 10px; background: rgba(255, 255, 255, 0.03); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); font-size: 10px; color: var(--text-muted); line-height: 1.35;">
            ℹ️ ${incident.traffic_disclaimer || 'Live traffic data unavailable. Travel times reflect speed on road network.'}
          </div>
        </div>
        `
        : ""
    }

    <!-- Telemetry Vitals -->
    <div style="margin-bottom: 14px;">
      <div class="detail-row"><span>Driver:</span> <strong>${amb.driver}</strong></div>
      <div class="detail-row"><span>Contact:</span> <strong>${amb.phone}</strong></div>
      <div class="detail-row"><span>Coordinates:</span> <strong>${amb.lat.toFixed(4)}, ${amb.lon.toFixed(4)}</strong></div>
      <div class="detail-row">
        <span>GPS Ping Freshness:</span> 
        ${freshness}
      </div>
      <div class="detail-row"><span>Last Timestamp:</span> <strong style="font-family: monospace;">${amb.last_update}</strong></div>
    </div>

    <!-- Active Call Mission Details & Alternatives -->
    ${
      incident
        ? `
        <div class="active-incident-box" style="margin-bottom: 14px;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
            <strong style="color: #ef4444; font-size: 12px;">🚨 Mission: ${incident.code}</strong>
            <span class="badge badge-${incident.priority.toLowerCase()}" style="font-size: 9px;">${incident.priority}</span>
          </div>
          <div style="color: #cbd5e1; font-size: 11px; margin-bottom: 4px;"><strong>Pickup:</strong> ${incident.pickup_address}</div>
          ${
            incident.destination_hospital
              ? `<div style="color: #38bdf8; font-size: 11px;"><strong>Trauma Facility:</strong> ${incident.destination_hospital.name}</div>`
              : `<div style="color: var(--text-muted); font-size: 10px;">Destination hospital not yet assigned.</div>`
          }
          <div style="margin-top: 8px;">
            <a href="/emergencies/${incident.id}" class="btn btn-primary btn-sm" style="width: 100%; font-size: 11px;">Open Incident Command</a>
          </div>
        </div>

        <!-- Route Alternatives & Fastest Available Selector -->
        ${
          routeAlternativesData.length > 1
            ? `
            <div style="margin-bottom: 14px;">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <span style="font-size: 11px; font-weight: 700; text-transform: uppercase; color: var(--text-secondary);">Route Navigation Options</span>
                <button type="button" class="btn btn-secondary btn-sm" onclick="selectFastestRoute()" style="font-size: 10px; padding: 2px 6px;">
                  ⚡ Fastest Route
                </button>
              </div>

              <div style="display: flex; flex-direction: column; gap: 6px;">
                ${routeAlternativesData
                  .map((r, idx) => {
                    const isCur = idx === selectedRouteIndex;
                    const diffMins = (r.duration_minutes - routeAlternativesData[0].duration_minutes).toFixed(0);
                    const diffText = idx === 0 ? "Fastest" : (diffMins > 0 ? `+${diffMins} min` : "Equal");

                    return `
                    <div class="route-option-card ${isCur ? 'active-route' : ''}" onclick="switchActiveRoute(${idx})">
                      <div class="route-option-header">
                        <strong style="font-size: 11px; color: ${isCur ? '#14b8a6' : '#fff'};">
                          ${r.summary}
                        </strong>
                        <span class="route-badge ${idx === 0 ? 'route-badge-recommended' : 'route-badge-alternative'}">
                          ${diffText}
                        </span>
                      </div>
                      <div style="font-size: 11px; color: var(--text-muted); display: flex; justify-content: space-between;">
                        <span>~${Math.round(r.duration_minutes)} mins (${r.distance_km.toFixed(1)} km)</span>
                        <span style="color: ${isCur ? '#14b8a6' : 'var(--text-muted)'}; font-weight: 600;">
                          ${isCur ? '● Selected View' : 'Select ↗'}
                        </span>
                      </div>
                    </div>
                  `;
                  })
                  .join("")}
              </div>
            </div>
            `
            : ""
        }
        `
        : `
        <div style="padding: 12px; background: rgba(16, 185, 129, 0.08); border: 1px solid rgba(16, 185, 129, 0.2); border-radius: var(--radius-sm); font-size: 11px; color: #a7f3d0; margin-bottom: 14px;">
          ✓ Unit is available and patrolling within primary grid. No active emergency calls dispatched.
        </div>
        `
    }

    <!-- Quick Vehicle Profile Action -->
    <a href="/ambulances/${amb.id}" class="btn btn-secondary btn-sm" style="width: 100%;">
      Inspect Vehicle Profile & Maintenance History
    </a>
  `;
}

function formatFreshnessBadge(lastUpdateStr, isStaleFlag) {
  if (isStaleFlag) {
    return `<span class="badge badge-high" style="font-size: 10px;">Stale (> 3 min)</span>`;
  }
  return `<span class="badge badge-available" style="font-size: 10px;">Fresh GPS Ping</span>`;
}

function formatFreshnessText(lastUpdateStr, isStaleFlag) {
  if (isStaleFlag) {
    return `<span style="color: #ef4444; font-weight: 600;">Stale (&gt;3m ago: ${lastUpdateStr})</span>`;
  }
  return `<span style="color: #10b981; font-weight: 600;">Fresh (${lastUpdateStr})</span>`;
}

/* --------------------------------------------------------------------------
   Controls & Simulated Movement Loops
   -------------------------------------------------------------------------- */
function bindMapControls() {
  // Manual Refresh
  const refreshBtn = document.getElementById("refreshMapBtn");
  if (refreshBtn) {
    refreshBtn.addEventListener("click", () => {
      fetchLiveFeed(false);
      if (typeof showToast === "function") showToast("Live radar telemetries refreshed", "info");
    });
  }

  // Auto Fit Bounds
  const fitBtn = document.getElementById("fitBoundsBtn");
  if (fitBtn) {
    fitBtn.addEventListener("click", () => {
      const markers = Object.values(ambulanceMarkers);
      if (markers.length > 0) {
        const group = new L.featureGroup(markers);
        mapInstance.fitBounds(group.getBounds().pad(0.15));
      }
    });
  }

  // Focus Vehicle Dropdown
  const focusSelect = document.getElementById("focusAmbulanceSelect");
  if (focusSelect) {
    focusSelect.addEventListener("change", (e) => {
      const ambId = Number(e.target.value);
      if (ambId && ambulanceMarkers[ambId] && ambulanceMarkers[ambId]._ambData) {
        selectAmbulance(ambulanceMarkers[ambId]._ambData, true);
        ambulanceMarkers[ambId].openPopup();
      }
    });
  }

  // Demonstration Simulation Movement Toggle
  const simToggleBtn = document.getElementById("simToggleBtn");
  if (simToggleBtn) {
    simToggleBtn.addEventListener("click", () => {
      isSimulationActive = !isSimulationActive;

      if (isSimulationActive) {
        simToggleBtn.classList.add("btn-danger");
        simToggleBtn.classList.remove("btn-secondary");
        simToggleBtn.innerHTML = `<span>■</span> Stop Simulation`;

        const banner = document.getElementById("simActiveBanner");
        if (banner) banner.style.display = "flex";

        if (typeof showToast === "function") {
          showToast("Demo Simulation Active: ambulances advancing along route waypoints", "warning");
        }

        // Trigger immediate step, then poll every 3 seconds
        triggerSimulationStep();
        simulationInterval = setInterval(triggerSimulationStep, 3000);
      } else {
        clearInterval(simulationInterval);
        simToggleBtn.classList.remove("btn-danger");
        simToggleBtn.classList.add("btn-secondary");
        simToggleBtn.innerHTML = `<span>▶</span> Simulate Fleet Movement`;

        const banner = document.getElementById("simActiveBanner");
        if (banner) banner.style.display = "none";

        if (typeof showToast === "function") {
          showToast("Demonstration movement ticks paused.", "info");
        }
      }
    });
  }
}

async function triggerSimulationStep() {
  try {
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute("content") || "";
    const res = await fetch("/api/v1/tracking/simulate-step", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken,
      },
    });
    if (res.ok) {
      fetchLiveFeed(false);
    }
  } catch (err) {
    console.warn("Simulation step tick failed:", err);
  }
}
