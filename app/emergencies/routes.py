from datetime import datetime, timedelta
import json
import re
import secrets
from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from app.db import get_db
from app.security import (
    generate_tracking_token,
    hash_token,
    log_activity,
    login_required,
)
from app.utils import (
    calculate_eta_metadata,
    haversine_distance,
    is_location_stale,
    rank_available_ambulances,
    rank_nearest_hospitals,
    recalculate_active_route,
    suggest_priority,
    validate_coordinates,
)

emergencies_bp = Blueprint("emergencies", __name__)

ALLOWED_CATEGORIES = ("Accident", "Medical Emergency", "Cardiac Concern", "Other")
ALLOWED_PRIORITIES = ("High", "Medium", "Low")
ALLOWED_STATUSES = ("Pending", "Assigned", "En Route", "Arrived", "Completed", "Cancelled")


def _generate_unique_code() -> str:
    """Generate a clean, collision-free human-readable request tracking code."""
    db = get_db()
    for _ in range(10):
        year = datetime.now().year
        suffix = secrets.token_hex(2).upper()
        code = f"REQ-{year}-{suffix}"
        cur = db.execute("SELECT id FROM emergency_requests WHERE request_code = ?", (code,))
        if not cur.fetchone():
            return code
    return f"REQ-{datetime.now().strftime('%Y%m%d%H%M%S')}"


# ===========================================================================
# 1. PUBLIC CITIZEN EMERGENCY PORTAL & SECURE TRACKING
# ===========================================================================

@emergencies_bp.route("/emergency/register", methods=["GET", "POST"])
def public_register():
    """Citizen emergency registration portal (Public Access)."""
    if request.method == "POST":
        patient_name = (request.form.get("patient_name") or "").strip()
        contact_number = (request.form.get("contact_number") or "").strip()
        category = (request.form.get("emergency_category") or "").strip()
        address = (request.form.get("pickup_address") or "").strip()
        lat_str = (request.form.get("pickup_latitude") or "").strip()
        lon_str = (request.form.get("pickup_longitude") or "").strip()
        notes = (request.form.get("notes") or "").strip()

        errors = []
        if not patient_name or len(patient_name) < 2:
            errors.append("Patient or caller name is required (at least 2 characters).")

        clean_phone = re.sub(r"[\s\-\(\)]", "", contact_number)
        if not clean_phone or not re.match(r"^\+?[0-9]{10,15}$", clean_phone):
            errors.append("Please enter a valid 10-15 digit contact phone number.")

        if category not in ALLOWED_CATEGORIES:
            errors.append(f"Invalid emergency category. Must be one of: {', '.join(ALLOWED_CATEGORIES)}")

        if not address or len(address) < 5:
            errors.append("Pickup address details are required (minimum 5 characters).")

        try:
            lat = float(lat_str)
            lon = float(lon_str)
            if not validate_coordinates(lat, lon):
                errors.append("Geographical coordinates outside valid bounds.")
        except (ValueError, TypeError):
            lat = 12.9716
            lon = 77.5946

        if errors:
            for err in errors:
                flash(err, "danger")
            return render_template(
                "emergencies/public_request.html",
                categories=ALLOWED_CATEGORIES,
                form=request.form,
            )

        priority_rec = suggest_priority(category, notes)
        assigned_priority = priority_rec["priority"]

        db = get_db()
        req_code = _generate_unique_code()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Generate secure unguessable tracking token with 48h expiration
        expiry_hours = current_app.config.get("TRACKING_TOKEN_EXPIRY_HOURS", 48)
        raw_token, token_hash, expires_at = generate_tracking_token(expiry_hours=expiry_hours)

        db.execute(
            """
            INSERT INTO emergency_requests (
                request_code, patient_name, contact_number, emergency_category,
                pickup_address, pickup_latitude, pickup_longitude, notes,
                priority, suggested_priority, status, tracking_token,
                tracking_token_hash, tracking_token_expires_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Pending', ?, ?, ?, ?, ?)
            """,
            (
                req_code,
                patient_name,
                contact_number,
                category,
                address,
                lat,
                lon,
                notes,
                assigned_priority,
                assigned_priority,
                raw_token,
                token_hash,
                expires_at,
                now_str,
                now_str,
            ),
        )
        db.commit()

        log_activity(
            "REQUEST_CREATED",
            f"Public emergency request {req_code} registered ({category}, Priority: {assigned_priority}).",
            record_type="emergency_request",
            actor="Citizen Portal",
        )

        return redirect(url_for("emergencies.public_success", request_code=req_code))

    return render_template("emergencies/public_request.html", categories=ALLOWED_CATEGORIES, form={})


@emergencies_bp.route("/emergency/success/<request_code>")
def public_success(request_code: str):
    """Public confirmation page displaying request reference, secure tracking link, and triage advice."""
    db = get_db()
    cur = db.execute(
        """
        SELECT request_code, emergency_category, pickup_address, priority, status,
               tracking_token, created_at
        FROM emergency_requests WHERE request_code = ?
        """,
        (request_code,),
    )
    req = cur.fetchone()
    if not req:
        abort(404, description="Emergency reference not found.")

    return render_template("emergencies/public_success.html", request=req)


@emergencies_bp.route("/track/<token>")
def track_by_token(token: str):
    """
    SECURE PUBLIC-FACING LIVE TRACKING PAGE:
    Accessed via unguessable 43-character token.
    Enforces strict privacy: patient names, phone numbers, and driver personal info are redacted.
    Checks token revocation and expiration.
    """
    db = get_db()
    tok_hash = hash_token(token)

    cur = db.execute(
        """
        SELECT r.id, r.request_code, r.emergency_category, r.pickup_address,
               r.pickup_latitude, r.pickup_longitude, r.priority, r.status,
               r.tracking_token, r.tracking_token_expires_at, r.tracking_token_revoked,
               r.route_geojson, r.route_distance_km, r.route_duration_minutes,
               r.route_provider, r.route_traffic_aware, r.route_last_calculated,
               r.created_at, r.updated_at,
               a.id as amb_id, a.ambulance_code, a.ambulance_type,
               a.latitude as amb_lat, a.longitude as amb_lon, a.last_location_update,
               h.id as hosp_id, h.name as hospital_name, h.address as hospital_address,
               h.latitude as hosp_lat, h.longitude as hosp_lon
        FROM emergency_requests r
        LEFT JOIN ambulances a ON r.assigned_ambulance_id = a.id
        LEFT JOIN hospitals h ON r.destination_hospital_id = h.id
        WHERE r.tracking_token = ? OR r.tracking_token_hash = ?
        """,
        (token, tok_hash),
    )
    req = cur.fetchone()

    if not req:
        return render_template("emergencies/track_error.html", error_title="Invalid Tracking Link", error_message="This emergency tracking link does not exist. Please check your reference URL."), 404

    # Check if revoked by authorized staff
    if req["tracking_token_revoked"]:
        return render_template("emergencies/track_error.html", error_title="Tracking Access Revoked", error_message="Access to this public tracking page has been revoked by emergency operations dispatch."), 403

    # Check expiration
    if req["tracking_token_expires_at"]:
        exp_time = req["tracking_token_expires_at"]
        if not isinstance(exp_time, datetime):
            try:
                exp_str = str(exp_time).replace("T", " ")[:19]
                exp_time = datetime.strptime(exp_str, "%Y-%m-%d %H:%M:%S")
            except Exception:
                exp_time = None

        if exp_time and datetime.now() > exp_time:
            return render_template(
                "emergencies/track_error.html",
                error_title="Tracking Link Expired",
                error_message="This emergency tracking link has expired. The incident session is no longer active.",
            ), 410

    # Calculate ETA & Freshness
    is_stale = is_location_stale(req["last_location_update"]) if req["amb_id"] else False
    dist_km = req["route_distance_km"] or 0.0
    dur_mins = req["route_duration_minutes"] or 0.0

    eta_meta = calculate_eta_metadata(
        dist_km,
        dur_mins,
        req["route_provider"] or "OSRM",
        is_traffic_aware=bool(req["route_traffic_aware"]),
        is_stale_telemetry=is_stale,
        calculated_at=req["route_last_calculated"],
    )

    route_coords = []
    if req["route_geojson"]:
        try:
            route_coords = json.loads(req["route_geojson"])
        except Exception:
            route_coords = []

    return render_template(
        "emergencies/public_track.html",
        request=req,
        token=token,
        eta_meta=eta_meta,
        route_coords=route_coords,
        is_stale=is_stale,
        poll_interval=current_app.config.get("MAP_POLL_INTERVAL_SECONDS", 4),
    )


@emergencies_bp.route("/api/v1/track/<token>/live")
def public_track_api(token: str):
    """
    JSON feed for public live tracking auto-refresh.
    Strictly sanitizes and omits all private patient records.
    """
    db = get_db()
    tok_hash = hash_token(token)

    cur = db.execute(
        """
        SELECT r.request_code, r.emergency_category, r.pickup_address,
               r.pickup_latitude, r.pickup_longitude, r.priority, r.status,
               r.tracking_token_revoked, r.tracking_token_expires_at,
               r.route_geojson, r.route_distance_km, r.route_duration_minutes,
               r.route_provider, r.route_traffic_aware, r.route_last_calculated,
               r.updated_at,
               a.id as amb_id, a.ambulance_code, a.ambulance_type,
               a.latitude as amb_lat, a.longitude as amb_lon, a.last_location_update,
               h.name as hospital_name, h.latitude as hosp_lat, h.longitude as hosp_lon
        FROM emergency_requests r
        LEFT JOIN ambulances a ON r.assigned_ambulance_id = a.id
        LEFT JOIN hospitals h ON r.destination_hospital_id = h.id
        WHERE r.tracking_token = ? OR r.tracking_token_hash = ?
        """,
        (token, tok_hash),
    )
    req = cur.fetchone()

    if not req:
        return jsonify({"error": "Not Found", "message": "Invalid tracking token"}), 404

    if req["tracking_token_revoked"]:
        return jsonify({"error": "Revoked", "message": "Tracking access revoked by dispatch"}), 403

    if req["tracking_token_expires_at"]:
        exp_time = req["tracking_token_expires_at"]
        if not isinstance(exp_time, datetime):
            try:
                exp_str = str(exp_time).replace("T", " ")[:19]
                exp_time = datetime.strptime(exp_str, "%Y-%m-%d %H:%M:%S")
            except Exception:
                exp_time = None

        if exp_time and datetime.now() > exp_time:
            return jsonify({"error": "Expired", "message": "Tracking link has expired"}), 410

    is_stale = is_location_stale(req["last_location_update"]) if req["amb_id"] else False
    dist_km = req["route_distance_km"] or 0.0
    dur_mins = req["route_duration_minutes"] or 0.0

    eta_meta = calculate_eta_metadata(
        dist_km,
        dur_mins,
        req["route_provider"] or "OSRM",
        is_traffic_aware=bool(req["route_traffic_aware"]),
        is_stale_telemetry=is_stale,
        calculated_at=req["route_last_calculated"],
    )

    route_coords = []
    if req["route_geojson"]:
        try:
            route_coords = json.loads(req["route_geojson"])
        except Exception:
            route_coords = []

    return jsonify({
        "status": "success",
        "request_code": req["request_code"],
        "category": req["emergency_category"],
        "pickup": {
            "address": req["pickup_address"],
            "lat": req["pickup_latitude"],
            "lon": req["pickup_longitude"],
        },
        "ambulance": {
            "code": req["ambulance_code"],
            "type": req["ambulance_type"],
            "lat": req["amb_lat"],
            "lon": req["amb_lon"],
            "last_update": req["last_location_update"],
            "is_stale": is_stale,
        } if req["amb_id"] else None,
        "destination_hospital": {
            "name": req["hospital_name"],
            "lat": req["hosp_lat"],
            "lon": req["hosp_lon"],
        } if req["hospital_name"] else None,
        "request_status": req["status"],
        "eta": eta_meta,
        "route_geometry": route_coords,
        "demo_mode": True,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })


# Legacy redirect helper for request_code
@emergencies_bp.route("/emergency/track/<request_code>")
def public_track(request_code: str):
    """Lookup unguessable token for request_code and render public tracking console."""
    db = get_db()
    cur = db.execute("SELECT tracking_token FROM emergency_requests WHERE request_code = ?", (request_code,))
    row = cur.fetchone()
    if row and row["tracking_token"]:
        return track_by_token(row["tracking_token"])
    abort(404, description="Tracking code not found.")


# ===========================================================================
# 2. INTERNAL DISPATCHER OPERATIONS (AUTHENTICATED)
# ===========================================================================

@emergencies_bp.route("/emergencies")
@login_required
def index():
    """Operations queue: view, filter, and search all emergency requests."""
    db = get_db()

    search = (request.args.get("search") or "").strip()
    status_filter = (request.args.get("status") or "").strip()
    priority_filter = (request.args.get("priority") or "").strip()
    category_filter = (request.args.get("category") or "").strip()

    page = request.args.get("page", 1, type=int)
    per_page = 12
    offset = (page - 1) * per_page

    query = """
        SELECT r.*, a.ambulance_code, a.driver_name, a.driver_phone, h.name as hospital_name
        FROM emergency_requests r
        LEFT JOIN ambulances a ON r.assigned_ambulance_id = a.id
        LEFT JOIN hospitals h ON r.destination_hospital_id = h.id
        WHERE 1=1
    """
    params = []

    if search:
        query += " AND (r.request_code LIKE ? OR r.patient_name LIKE ? OR r.pickup_address LIKE ?)"
        like_term = f"%{search}%"
        params.extend([like_term, like_term, like_term])

    if status_filter and status_filter in ALLOWED_STATUSES:
        query += " AND r.status = ?"
        params.append(status_filter)

    if priority_filter and priority_filter in ALLOWED_PRIORITIES:
        query += " AND r.priority = ?"
        params.append(priority_filter)

    if category_filter and category_filter in ALLOWED_CATEGORIES:
        query += " AND r.emergency_category = ?"
        params.append(category_filter)

    count_query = query.replace("SELECT r.*, a.ambulance_code, a.driver_name, a.driver_phone, h.name as hospital_name", "SELECT COUNT(*)")
    total_count = db.execute(count_query, params).fetchone()[0]

    query += """
        ORDER BY 
            CASE r.status
                WHEN 'Pending' THEN 1
                WHEN 'Assigned' THEN 2
                WHEN 'En Route' THEN 3
                WHEN 'Arrived' THEN 4
                WHEN 'Completed' THEN 5
                ELSE 6
            END ASC,
            CASE r.priority
                WHEN 'High' THEN 1
                WHEN 'Medium' THEN 2
                WHEN 'Low' THEN 3
                ELSE 4
            END ASC,
            r.created_at DESC
        LIMIT ? OFFSET ?
    """
    params.extend([per_page, offset])

    requests_list = db.execute(query, params).fetchall()
    total_pages = max(1, (total_count + per_page - 1) // per_page)

    return render_template(
        "emergencies/index.html",
        requests=requests_list,
        search=search,
        status_filter=status_filter,
        priority_filter=priority_filter,
        category_filter=category_filter,
        page=page,
        total_pages=total_pages,
        total_count=total_count,
        allowed_categories=ALLOWED_CATEGORIES,
        allowed_priorities=ALLOWED_PRIORITIES,
        allowed_statuses=ALLOWED_STATUSES,
    )


@emergencies_bp.route("/emergencies/new", methods=["GET", "POST"])
@login_required
def create():
    """Internal dispatcher creation of an emergency incident call."""
    db = get_db()
    cur = db.execute("SELECT id, name FROM hospitals ORDER BY name ASC")
    hospitals = cur.fetchall()

    if request.method == "POST":
        patient_name = (request.form.get("patient_name") or "").strip()
        contact_number = (request.form.get("contact_number") or "").strip()
        category = (request.form.get("emergency_category") or "").strip()
        address = (request.form.get("pickup_address") or "").strip()
        lat_str = (request.form.get("pickup_latitude") or "").strip()
        lon_str = (request.form.get("pickup_longitude") or "").strip()
        notes = (request.form.get("notes") or "").strip()
        override_priority = (request.form.get("priority") or "").strip()
        destination_hospital_id = request.form.get("destination_hospital_id", type=int)

        errors = []
        if not patient_name:
            errors.append("Patient name is required.")
        if not contact_number:
            errors.append("Contact number is required.")
        if category not in ALLOWED_CATEGORIES:
            errors.append("Invalid emergency category.")
        if not address:
            errors.append("Pickup address is required.")

        try:
            lat = float(lat_str)
            lon = float(lon_str)
            if not validate_coordinates(lat, lon):
                errors.append("Invalid geographic coordinates.")
        except (ValueError, TypeError):
            errors.append("Latitude and longitude must be valid decimal numbers.")

        suggested = suggest_priority(category, notes)["priority"]
        chosen_priority = override_priority if override_priority in ALLOWED_PRIORITIES else suggested

        if errors:
            for err in errors:
                flash(err, "danger")
            return render_template(
                "emergencies/create.html",
                categories=ALLOWED_CATEGORIES,
                priorities=ALLOWED_PRIORITIES,
                hospitals=hospitals,
                form=request.form,
            )

        req_code = _generate_unique_code()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        expiry_hours = current_app.config.get("TRACKING_TOKEN_EXPIRY_HOURS", 48)
        raw_token, token_hash, expires_at = generate_tracking_token(expiry_hours=expiry_hours)

        cur = db.execute(
            """
            INSERT INTO emergency_requests (
                request_code, patient_name, contact_number, emergency_category,
                pickup_address, pickup_latitude, pickup_longitude, notes,
                priority, suggested_priority, status, destination_hospital_id,
                tracking_token, tracking_token_hash, tracking_token_expires_at,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Pending', ?, ?, ?, ?, ?, ?)
            """,
            (
                req_code,
                patient_name,
                contact_number,
                category,
                address,
                lat,
                lon,
                notes,
                chosen_priority,
                suggested,
                destination_hospital_id,
                raw_token,
                token_hash,
                expires_at,
                now_str,
                now_str,
            ),
        )
        db.commit()
        new_id = cur.lastrowid

        log_activity(
            "REQUEST_CREATED",
            f"Dispatcher registered emergency {req_code} ({category}, Priority: {chosen_priority}).",
            record_type="emergency_request",
            record_id=new_id,
        )
        flash(f"Emergency request {req_code} registered. Proceed with Smart Dispatch Assist.", "success")
        return redirect(url_for("emergencies.detail", id=new_id))

    return render_template(
        "emergencies/create.html",
        categories=ALLOWED_CATEGORIES,
        priorities=ALLOWED_PRIORITIES,
        hospitals=hospitals,
        form={},
    )


@emergencies_bp.route("/emergencies/<int:id>")
@login_required
def detail(id: int):
    """View detailed request console, timeline, and candidate dispatch recommendations."""
    db = get_db()

    cur = db.execute(
        """
        SELECT r.*, a.ambulance_code, a.driver_name, a.driver_phone, a.vehicle_number, a.ambulance_type,
               a.latitude as amb_lat, a.longitude as amb_lon, a.last_location_update,
               h.name as destination_hospital_name, h.address as destination_hospital_address,
               h.latitude as hosp_lat, h.longitude as hosp_lon
        FROM emergency_requests r
        LEFT JOIN ambulances a ON r.assigned_ambulance_id = a.id
        LEFT JOIN hospitals h ON r.destination_hospital_id = h.id
        WHERE r.id = ?
        """,
        (id,),
    )
    req = cur.fetchone()
    if not req:
        abort(404, description="Emergency request not found.")

    # Get SMART DISPATCH ASSIST candidates if request is Pending or Assigned
    candidates = rank_available_ambulances(req["pickup_latitude"], req["pickup_longitude"], limit=5)

    # Get Nearest Hospitals
    hospitals = rank_nearest_hospitals(req["pickup_latitude"], req["pickup_longitude"], limit=6)

    # All hospitals for destination selection
    cur = db.execute("SELECT id, name, address FROM hospitals ORDER BY name ASC")
    all_hospitals = cur.fetchall()

    # Activity logs for this request
    cur = db.execute(
        """
        SELECT * FROM activity_logs 
        WHERE record_type = 'emergency_request' AND record_id = ?
        ORDER BY created_at DESC
        """,
        (id,),
    )
    logs = cur.fetchall()

    # Route and ETA metadata
    is_stale = is_location_stale(req["last_location_update"]) if req["assigned_ambulance_id"] else False
    eta_meta = calculate_eta_metadata(
        req["route_distance_km"] or 0.0,
        req["route_duration_minutes"] or 0.0,
        req["route_provider"] or "OSRM",
        is_traffic_aware=bool(req["route_traffic_aware"]),
        is_stale_telemetry=is_stale,
        calculated_at=req["route_last_calculated"],
    )

    route_coords = []
    if req["route_geojson"]:
        try:
            route_coords = json.loads(req["route_geojson"])
        except Exception:
            route_coords = []

    return render_template(
        "emergencies/detail.html",
        request=req,
        candidates=candidates,
        hospitals=hospitals,
        logs=logs,
        eta_meta=eta_meta,
        route_coords=route_coords,
        is_stale=is_stale,
        all_hospitals=all_hospitals,
        allowed_statuses=ALLOWED_STATUSES,
        allowed_priorities=ALLOWED_PRIORITIES,
    )


@emergencies_bp.route("/emergencies/<int:id>/assign", methods=["POST"])
@login_required
def assign_ambulance(id: int):
    """
    SMART DISPATCH ASSIGNMENT:
    Executes an atomic database transaction to assign an available ambulance.
    Immediately triggers fastest-route calculation.
    """
    ambulance_id = request.form.get("ambulance_id", type=int)
    destination_hospital_id = request.form.get("destination_hospital_id", type=int)

    if not ambulance_id:
        flash("Please select a candidate ambulance to assign.", "warning")
        return redirect(url_for("emergencies.detail", id=id))

    db = get_db()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        db.execute("BEGIN IMMEDIATE TRANSACTION;")

        cur = db.execute("SELECT request_code, status, assigned_ambulance_id FROM emergency_requests WHERE id = ?", (id,))
        req = cur.fetchone()
        if not req:
            db.rollback()
            abort(404, description="Request not found.")

        if req["status"] in ("Completed", "Cancelled"):
            db.rollback()
            flash(f"Cannot assign ambulance: Request {req['request_code']} is already {req['status']}.", "warning")
            return redirect(url_for("emergencies.detail", id=id))

        cur = db.execute("SELECT ambulance_code, status FROM ambulances WHERE id = ?", (ambulance_id,))
        amb = cur.fetchone()
        if not amb:
            db.rollback()
            flash("Selected ambulance does not exist.", "danger")
            return redirect(url_for("emergencies.detail", id=id))

        if amb["status"] != "Available":
            db.rollback()
            flash(
                f"Dispatch Conflict: Ambulance {amb['ambulance_code']} is no longer available (current status: {amb['status']}).",
                "danger",
            )
            return redirect(url_for("emergencies.detail", id=id))

        # If previous ambulance was assigned, release it
        if req["assigned_ambulance_id"] and req["assigned_ambulance_id"] != ambulance_id:
            db.execute("UPDATE ambulances SET status = 'Available', updated_at = ? WHERE id = ?", (now_str, req["assigned_ambulance_id"]))

        # Mark chosen ambulance as Busy
        db.execute("UPDATE ambulances SET status = 'Busy', updated_at = ? WHERE id = ?", (now_str, ambulance_id))

        # Update emergency request
        if destination_hospital_id:
            db.execute(
                """
                UPDATE emergency_requests 
                SET status = 'Assigned', assigned_ambulance_id = ?, destination_hospital_id = ?,
                    assigned_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (ambulance_id, destination_hospital_id, now_str, now_str, id),
            )
        else:
            db.execute(
                """
                UPDATE emergency_requests 
                SET status = 'Assigned', assigned_ambulance_id = ?, assigned_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (ambulance_id, now_str, now_str, id),
            )

        db.commit()

        # Recalculate route and ETA immediately
        recalculate_active_route(id, force_refresh=True)

        log_activity(
            "AMBULANCE_ASSIGNED",
            f"Assigned ambulance {amb['ambulance_code']} to emergency {req['request_code']}.",
            record_type="emergency_request",
            record_id=id,
        )
        flash(f"Ambulance {amb['ambulance_code']} successfully dispatched and locked to request {req['request_code']}.", "success")
    except Exception as exc:
        db.rollback()
        flash(f"Failed to assign ambulance: {exc}", "danger")

    return redirect(url_for("emergencies.detail", id=id))


@emergencies_bp.route("/emergencies/<int:id>/destination", methods=["POST"])
@login_required
def set_destination(id: int):
    """Assign or update the target trauma receiving hospital for an emergency call."""
    hospital_id = request.form.get("hospital_id", type=int)
    db = get_db()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    db.execute(
        "UPDATE emergency_requests SET destination_hospital_id = ?, updated_at = ? WHERE id = ?",
        (hospital_id, now_str, id),
    )
    db.commit()

    recalculate_active_route(id, force_refresh=True)
    flash("Destination hospital updated.", "info")
    return redirect(url_for("emergencies.detail", id=id))


@emergencies_bp.route("/emergencies/<int:id>/revoke-token", methods=["POST"])
@login_required
def revoke_tracking_token(id: int):
    """Authorized dispatcher action to revoke public tracking access for a call."""
    db = get_db()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    db.execute(
        "UPDATE emergency_requests SET tracking_token_revoked = 1, updated_at = ? WHERE id = ?",
        (now_str, id),
    )
    db.commit()

    log_activity("TOKEN_REVOKED", f"Public tracking link access revoked for emergency request ID {id}.", record_type="emergency_request", record_id=id)
    flash("Public live tracking access has been revoked for this incident.", "warning")
    return redirect(url_for("emergencies.detail", id=id))


@emergencies_bp.route("/emergencies/<int:id>/refresh-token", methods=["POST"])
@login_required
def refresh_tracking_token(id: int):
    """Generate a fresh unguessable tracking token and restore access."""
    db = get_db()
    expiry_hours = current_app.config.get("TRACKING_TOKEN_EXPIRY_HOURS", 48)
    raw_token, token_hash, expires_at = generate_tracking_token(expiry_hours=expiry_hours)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    db.execute(
        """
        UPDATE emergency_requests
        SET tracking_token = ?, tracking_token_hash = ?, tracking_token_expires_at = ?,
            tracking_token_revoked = 0, updated_at = ?
        WHERE id = ?
        """,
        (raw_token, token_hash, expires_at, now_str, id),
    )
    db.commit()

    log_activity("TOKEN_REFRESHED", f"Regenerated public tracking token for emergency ID {id}.", record_type="emergency_request", record_id=id)
    flash("New secure public tracking token generated.", "success")
    return redirect(url_for("emergencies.detail", id=id))


@emergencies_bp.route("/emergencies/<int:id>/recalculate-route", methods=["POST"])
@login_required
def recalculate_route_endpoint(id: int):
    """Force an on-demand road route & ETA recalculation."""
    res = recalculate_active_route(id, force_refresh=True)
    if res:
        flash("Route and ETA recalculation completed.", "info")
    else:
        flash("Could not calculate route: Verify that an ambulance with valid coordinates is assigned.", "warning")
    return redirect(url_for("emergencies.detail", id=id))


@emergencies_bp.route("/emergencies/<int:id>/status", methods=["POST"])
@login_required
def update_status(id: int):
    """Transition emergency lifecycle status and update vehicle availability when resolved."""
    new_status = (request.form.get("status") or "").strip()
    if new_status not in ALLOWED_STATUSES:
        flash("Invalid status transition.", "danger")
        return redirect(url_for("emergencies.detail", id=id))

    db = get_db()
    cur = db.execute("SELECT * FROM emergency_requests WHERE id = ?", (id,))
    req = cur.fetchone()
    if not req:
        abort(404, description="Request not found.")

    old_status = req["status"]
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    arrived_at = req["arrived_at"]
    completed_at = req["completed_at"]

    if new_status == "Arrived" and not arrived_at:
        arrived_at = now_str
    elif new_status == "Completed" and not completed_at:
        completed_at = now_str

    try:
        db.execute("BEGIN IMMEDIATE TRANSACTION;")

        # If transitioning to Completed or Cancelled, free up the assigned ambulance!
        if new_status in ("Completed", "Cancelled") and req["assigned_ambulance_id"]:
            db.execute(
                "UPDATE ambulances SET status = 'Available', updated_at = ? WHERE id = ?",
                (now_str, req["assigned_ambulance_id"]),
            )

        db.execute(
            """
            UPDATE emergency_requests
            SET status = ?, arrived_at = ?, completed_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (new_status, arrived_at, completed_at, now_str, id),
        )

        db.commit()

        log_activity(
            "STATUS_CHANGED",
            f"Emergency {req['request_code']} transitioned from '{old_status}' to '{new_status}'.",
            record_type="emergency_request",
            record_id=id,
        )
        flash(f"Status updated to '{new_status}'.", "info")
    except Exception as exc:
        db.rollback()
        flash(f"Failed to update status: {exc}", "danger")

    return redirect(url_for("emergencies.detail", id=id))


@emergencies_bp.route("/emergencies/<int:id>/priority", methods=["POST"])
@login_required
def update_priority(id: int):
    """Dispatcher manual override of triage priority."""
    new_priority = (request.form.get("priority") or "").strip()
    if new_priority not in ALLOWED_PRIORITIES:
        flash("Invalid priority level.", "danger")
        return redirect(url_for("emergencies.detail", id=id))

    db = get_db()
    cur = db.execute("SELECT request_code, priority FROM emergency_requests WHERE id = ?", (id,))
    req = cur.fetchone()
    if not req:
        abort(404, description="Request not found.")

    old_pri = req["priority"]
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    db.execute("UPDATE emergency_requests SET priority = ?, updated_at = ? WHERE id = ?", (new_priority, now_str, id))
    db.commit()

    log_activity(
        "PRIORITY_CHANGED",
        f"Emergency {req['request_code']} priority overridden by dispatcher: {old_pri} -> {new_priority}.",
        record_type="emergency_request",
        record_id=id,
    )
    flash(f"Priority changed to {new_priority}.", "info")
    return redirect(url_for("emergencies.detail", id=id))
