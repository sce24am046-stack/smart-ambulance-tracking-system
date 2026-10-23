from datetime import datetime, timedelta
import json
import math
import secrets
from flask import Blueprint, abort, current_app, jsonify, render_template, request, session
from app.db import get_db
from app.routing import get_cached_route, get_routing_provider, has_moved_significantly
from app.security import check_telemetry_rate_limit, csrf_exempt, log_activity, login_required
from app.utils import (
    calculate_eta_metadata,
    format_eta_clock,
    is_location_stale,
    recalculate_active_route,
    validate_coordinates,
)

tracking_bp = Blueprint("tracking", __name__)


@tracking_bp.route("/tracking")
@login_required
def live_map():
    """Interactive Leaflet Ambulance Tracking Map Command Console with fastest-route navigation."""
    db = get_db()

    # Load all ambulances
    cur = db.execute("SELECT * FROM ambulances ORDER BY ambulance_code ASC")
    amb_rows = cur.fetchall()

    # Load all hospitals
    cur = db.execute("SELECT * FROM hospitals ORDER BY name ASC")
    hospitals = cur.fetchall()

    # Load active emergencies with route metadata
    cur = db.execute(
        """
        SELECT r.id, r.request_code, r.pickup_address, r.pickup_latitude, r.pickup_longitude,
               r.priority, r.status, r.emergency_category, r.assigned_ambulance_id,
               r.route_geojson, r.route_distance_km, r.route_duration_minutes,
               r.route_provider, r.route_traffic_aware, r.route_last_calculated,
               r.destination_hospital_id,
               a.ambulance_code, a.driver_name, a.latitude as amb_lat, a.longitude as amb_lon,
               h.name as destination_hospital_name, h.latitude as hosp_lat, h.longitude as hosp_lon
        FROM emergency_requests r
        LEFT JOIN ambulances a ON r.assigned_ambulance_id = a.id
        LEFT JOIN hospitals h ON r.destination_hospital_id = h.id
        WHERE r.status IN ('Pending', 'Assigned', 'En Route', 'Arrived')
        ORDER BY r.created_at DESC
        """
    )
    active_emergencies = cur.fetchall()

    ambulances = []
    for a in amb_rows:
        stale = is_location_stale(a["last_location_update"])
        ambulances.append({"data": a, "is_stale": stale})

    return render_template(
        "tracking/live_map.html",
        ambulances=ambulances,
        hospitals=hospitals,
        active_emergencies=active_emergencies,
        poll_interval=current_app.config.get("MAP_POLL_INTERVAL_SECONDS", 4),
        routing_provider=current_app.config.get("ROUTING_PROVIDER", "osrm"),
    )


@tracking_bp.route("/api/v1/tracking/live")
@login_required
def api_live_feed():
    """
    JSON feed providing real-time vehicle coordinates, status, assigned active incident targets,
    fastest-route polylines, and live ETA estimations.
    """
    db = get_db()

    # Query ambulances with linked active incident and route data
    cur = db.execute(
        """
        SELECT a.id, a.ambulance_code, a.driver_name, a.driver_phone, a.vehicle_number,
               a.ambulance_type, a.status, a.latitude, a.longitude, a.last_location_update,
               r.id as active_request_id, r.request_code as active_request_code,
               r.pickup_address, r.pickup_latitude, r.pickup_longitude, r.priority,
               r.status as request_status, r.route_geojson, r.route_distance_km,
               r.route_duration_minutes, r.route_provider, r.route_traffic_aware,
               r.route_last_calculated, r.destination_hospital_id,
               h.name as hospital_name, h.latitude as hosp_lat, h.longitude as hosp_lon
        FROM ambulances a
        LEFT JOIN emergency_requests r ON a.id = r.assigned_ambulance_id AND r.status IN ('Assigned', 'En Route', 'Arrived')
        LEFT JOIN hospitals h ON r.destination_hospital_id = h.id
        ORDER BY a.ambulance_code ASC
        """
    )

    ambulances = []
    for row in cur.fetchall():
        stale = is_location_stale(row["last_location_update"])

        active_incident = None
        if row["active_request_id"]:
            # Parse route geometry if present
            route_coords = []
            if row["route_geojson"]:
                try:
                    route_coords = json.loads(row["route_geojson"])
                except Exception:
                    route_coords = []

            dur_mins = row["route_duration_minutes"] or 0.0
            dist_km = row["route_distance_km"] or 0.0
            provider_str = row["route_provider"] or "OSRM"
            is_traffic = bool(row["route_traffic_aware"])

            eta_meta = calculate_eta_metadata(
                dist_km,
                dur_mins,
                provider_str,
                is_traffic_aware=is_traffic,
                is_stale_telemetry=stale,
                calculated_at=row["route_last_calculated"],
            )

            active_incident = {
                "id": row["active_request_id"],
                "code": row["active_request_code"],
                "pickup_address": row["pickup_address"],
                "lat": row["pickup_latitude"],
                "lon": row["pickup_longitude"],
                "priority": row["priority"],
                "status": row["request_status"],
                "route_geometry": route_coords,
                "distance_km": dist_km,
                "duration_minutes": dur_mins,
                "eta_clock": eta_meta["eta_clock"],
                "eta_type": eta_meta["eta_type"],
                "eta_type_label": eta_meta["type_label"],
                "is_traffic_aware": eta_meta["is_traffic_aware"],
                "traffic_disclaimer": eta_meta["disclaimer"],
                "last_calculated": row["route_last_calculated"],
                "destination_hospital": {
                    "id": row["destination_hospital_id"],
                    "name": row["hospital_name"],
                    "lat": row["hosp_lat"],
                    "lon": row["hosp_lon"],
                } if row["destination_hospital_id"] else None,
            }

        ambulances.append({
            "id": row["id"],
            "code": row["ambulance_code"],
            "driver": row["driver_name"],
            "phone": row["driver_phone"],
            "vehicle": row["vehicle_number"],
            "type": row["ambulance_type"],
            "status": row["status"],
            "lat": row["latitude"],
            "lon": row["longitude"],
            "last_update": row["last_location_update"],
            "is_stale": stale,
            "active_incident": active_incident,
        })

    cur = db.execute("SELECT id, name, address, contact_number, latitude, longitude, services FROM hospitals")
    hospitals = [
        {
            "id": h["id"],
            "name": h["name"],
            "address": h["address"],
            "contact": h["contact_number"],
            "lat": h["latitude"],
            "lon": h["longitude"],
            "services": h["services"],
        }
        for h in cur.fetchall()
    ]

    return jsonify({
        "status": "success",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "ambulances": ambulances,
        "hospitals": hospitals,
        "routing_provider": current_app.config.get("ROUTING_PROVIDER", "osrm"),
        "demo_notice": "DEMO MODE — SIMULATED LOCATIONS (Bengaluru Area)",
    })


@tracking_bp.route("/api/v1/ambulances/<int:id>/location", methods=["PUT", "POST"])
@csrf_exempt
def update_location(id: int):
    """
    AUTHORIZED LOCATION INGESTION API:
    Receives automated coordinates from vehicle GPS hardware or driver mobile terminal.
    Validates:
    - User authorization (session or X-API-Key)
    - Ambulance identifier
    - Latitude and longitude boundaries
    - Timestamp validity
    - Location update frequency (rate limiting)
    """
    # 1. Authorization Check
    api_key = request.headers.get("X-API-Key") or request.headers.get("Authorization", "").replace("Bearer ", "")
    expected_key = current_app.config.get("GPS_TRACKER_API_KEY")

    has_session_auth = session.get("user_id") is not None
    has_api_key_auth = bool(api_key and expected_key and api_key == expected_key)

    if not (has_session_auth or has_api_key_auth):
        return jsonify({"error": "Unauthorized", "message": "Valid session or X-API-Key header required."}), 401

    # 2. Update Frequency Rate Limiting
    min_interval = current_app.config.get("LOCATION_UPDATE_MIN_INTERVAL_SECONDS", 2)
    allowed, retry_after = check_telemetry_rate_limit(id, min_interval_seconds=min_interval)
    if not allowed:
        return jsonify({
            "error": "Rate Limit Exceeded",
            "message": f"Telemetry updates throttled. Maximum update frequency is once every {min_interval}s.",
            "retry_after_seconds": retry_after,
        }), 429

    payload = request.get_json(silent=True) or request.form
    if not payload:
        return jsonify({"error": "Bad Request", "message": "Missing coordinates payload."}), 400

    lat_val = payload.get("latitude") or payload.get("lat")
    lon_val = payload.get("longitude") or payload.get("lon")
    ts_val = payload.get("timestamp") or payload.get("time")

    # 3. Validate Coordinates
    try:
        lat = float(lat_val)
        lon = float(lon_val)
        if not validate_coordinates(lat, lon):
            return jsonify({"error": "Validation Error", "message": "Coordinates out of earthly bounds (-90 to 90, -180 to 180)."}), 422
    except (ValueError, TypeError):
        return jsonify({"error": "Validation Error", "message": "Latitude and longitude must be valid floating point numbers."}), 422

    # 4. Validate Timestamp
    now = datetime.now()
    if ts_val:
        try:
            # Accepts ISO format or YYYY-MM-DD HH:MM:SS
            ts_str = str(ts_val).replace("T", " ")[:19]
            parsed_ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
            # Disallow future timestamps with 60s tolerance for clock skew
            if parsed_ts > now + timedelta(seconds=60):
                return jsonify({"error": "Validation Error", "message": "Telemetry timestamp cannot be in the future."}), 422
            timestamp_to_store = ts_str
        except Exception:
            return jsonify({"error": "Validation Error", "message": "Invalid timestamp format. Expected ISO-8601 or YYYY-MM-DD HH:MM:SS."}), 422
    else:
        timestamp_to_store = now.strftime("%Y-%m-%d %H:%M:%S")

    db = get_db()
    cur = db.execute("SELECT id, ambulance_code, status, latitude, longitude FROM ambulances WHERE id = ?", (id,))
    amb = cur.fetchone()
    if not amb:
        return jsonify({"error": "Not Found", "message": "Ambulance ID does not exist."}), 404

    old_lat = amb["latitude"]
    old_lon = amb["longitude"]

    # 5. Store latest coordinates and timestamps in SQLite
    db.execute(
        """
        UPDATE ambulances 
        SET latitude = ?, longitude = ?, last_location_update = ?,
            last_telemetry_received_at = ?, updated_at = ?
        WHERE id = ?
        """,
        (lat, lon, timestamp_to_store, now.strftime("%Y-%m-%d %H:%M:%S"), now.strftime("%Y-%m-%d %H:%M:%S"), id),
    )
    db.commit()

    # 6. Recalculate ETA and route if vehicle is on active emergency call and moved significantly
    route_updated = False
    cur = db.execute(
        "SELECT id FROM emergency_requests WHERE assigned_ambulance_id = ? AND status IN ('Assigned', 'En Route') LIMIT 1",
        (id,),
    )
    active_req = cur.fetchone()
    if active_req:
        # Check if ambulance moved > 50 meters
        if has_moved_significantly(old_lat, old_lon, lat, lon, threshold_meters=50.0):
            recalculate_active_route(active_req["id"])
            route_updated = True

    return jsonify({
        "status": "success",
        "message": f"Location updated for {amb['ambulance_code']}",
        "ambulance_id": id,
        "ambulance_code": amb["ambulance_code"],
        "latitude": lat,
        "longitude": lon,
        "timestamp": timestamp_to_store,
        "route_recalculated": route_updated,
    })


@tracking_bp.route("/api/v1/routes/calculate", methods=["GET", "POST"])
@login_required
def calculate_route_api():
    """
    FASTEST-ROUTE NAVIGATION API:
    Calculates primary and alternative road routes between coordinates, comparing durations
    and identifying the fastest available option.
    """
    data = request.get_json(silent=True) or request.args
    orig_lat = data.get("origin_lat")
    orig_lon = data.get("origin_lon")
    dest_lat = data.get("dest_lat")
    dest_lon = data.get("dest_lon")

    try:
        o_lat = float(orig_lat)
        o_lon = float(orig_lon)
        d_lat = float(dest_lat)
        d_lon = float(dest_lon)
        if not (validate_coordinates(o_lat, o_lon) and validate_coordinates(d_lat, d_lon)):
            return jsonify({"error": "Validation Error", "message": "Coordinates outside geographic bounds."}), 422
    except (ValueError, TypeError):
        return jsonify({"error": "Validation Error", "message": "Origin and destination coordinates required."}), 400

    provider = get_routing_provider()
    route_result = get_cached_route(
        o_lat,
        o_lon,
        d_lat,
        d_lon,
        provider=provider,
        ttl_seconds=current_app.config.get("ROUTING_CACHE_TTL_SECONDS", 300),
    )

    rec_route = route_result.get("recommended_route", {})
    dist_km = rec_route.get("distance_km", 0.0)
    dur_mins = rec_route.get("duration_traffic_minutes") or rec_route.get("duration_minutes", 0.0)

    eta_meta = calculate_eta_metadata(
        dist_km,
        dur_mins,
        route_result.get("provider_name", "OSRM"),
        is_traffic_aware=route_result.get("is_traffic_aware", False),
    )
    route_result["eta_metadata"] = eta_meta

    return jsonify(route_result)


@tracking_bp.route("/api/v1/tracking/simulate-step", methods=["POST"])
@login_required
def simulate_movement_step():
    """
    OPTIONAL DEMO SIMULATION STEP:
    Simulates vehicle progress along actual calculated road polylines toward the incident.
    Clearly labeled and strictly separate from real GPS updates.
    """
    db = get_db()
    cur = db.execute(
        """
        SELECT a.id, a.ambulance_code, a.status, a.latitude, a.longitude,
               r.id as request_id, r.pickup_latitude, r.pickup_longitude,
               r.route_geojson, r.route_distance_km, r.route_duration_minutes
        FROM ambulances a
        LEFT JOIN emergency_requests r ON a.id = r.assigned_ambulance_id AND r.status IN ('Assigned', 'En Route')
        WHERE a.status IN ('Available', 'Busy')
        """
    )
    ambulances = cur.fetchall()
    updated_records = []
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Step distance: ~150-250 meters per simulation tick (~0.002 degrees)
    STEP_SIZE = 0.0020

    for amb in ambulances:
        curr_lat = amb["latitude"]
        curr_lon = amb["longitude"]
        req_id = amb["request_id"]

        new_lat, new_lon = curr_lat, curr_lon

        if amb["status"] == "Busy" and amb["pickup_latitude"] and amb["pickup_longitude"]:
            target_lat = amb["pickup_latitude"]
            target_lon = amb["pickup_longitude"]

            # If a calculated route polyline is available, step toward next polyline node!
            polyline = []
            if amb["route_geojson"]:
                try:
                    polyline = json.loads(amb["route_geojson"])
                except Exception:
                    polyline = []

            advanced_along_poly = False
            if polyline and len(polyline) > 2:
                # Find closest waypoint on polyline and move toward next one
                closest_idx = 0
                min_d = float("inf")
                for p_idx, pt in enumerate(polyline):
                    d = math.hypot(pt[0] - curr_lat, pt[1] - curr_lon)
                    if d < min_d:
                        min_d = d
                        closest_idx = p_idx

                next_idx = min(closest_idx + 1, len(polyline) - 1)
                next_pt = polyline[next_idx]
                d_lat = next_pt[0] - curr_lat
                d_lon = next_pt[1] - curr_lon
                dist = math.hypot(d_lat, d_lon)

                if dist > STEP_SIZE:
                    new_lat = curr_lat + (d_lat / dist) * STEP_SIZE
                    new_lon = curr_lon + (d_lon / dist) * STEP_SIZE
                else:
                    new_lat = next_pt[0]
                    new_lon = next_pt[1]
                advanced_along_poly = True

            if not advanced_along_poly:
                d_lat = target_lat - curr_lat
                d_lon = target_lon - curr_lon
                dist = math.hypot(d_lat, d_lon)
                if dist > STEP_SIZE:
                    new_lat = curr_lat + (d_lat / dist) * STEP_SIZE
                    new_lon = curr_lon + (d_lon / dist) * STEP_SIZE
                else:
                    new_lat = target_lat
                    new_lon = target_lon
        else:
            # Gentle realistic patrol jitter (within 0.0004 deg)
            jitter_lat = (secrets.randbelow(100) - 50) / 120000.0
            jitter_lon = (secrets.randbelow(100) - 50) / 120000.0
            new_lat = curr_lat + jitter_lat
            new_lon = curr_lon + jitter_lon

        # Update in database
        db.execute(
            """
            UPDATE ambulances 
            SET latitude = ?, longitude = ?, last_location_update = ?, updated_at = ?
            WHERE id = ?
            """,
            (round(new_lat, 5), round(new_lon, 5), now_str, now_str, amb["id"]),
        )
        updated_records.append({
            "id": amb["id"],
            "code": amb["ambulance_code"],
            "lat": round(new_lat, 5),
            "lon": round(new_lon, 5),
        })

        # Recalculate route ETA if on active mission
        if req_id:
            recalculate_active_route(req_id)

    db.commit()

    return jsonify({
        "status": "success",
        "simulated_count": len(updated_records),
        "updated": updated_records,
        "timestamp": now_str,
        "disclaimer": "Simulated demonstration movement. Not linked to actual vehicle telemetry.",
    })
