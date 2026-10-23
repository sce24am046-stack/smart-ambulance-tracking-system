from datetime import datetime
import sqlite3
from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from app.db import get_db
from app.security import log_activity, login_required
from app.utils import is_location_stale, validate_coordinates

ambulances_bp = Blueprint("ambulances", __name__, url_prefix="/ambulances")

ALLOWED_TYPES = (
    "Basic Life Support (BLS)",
    "Advanced Life Support (ALS)",
    "Patient Transport (PTS)",
)
ALLOWED_STATUSES = ("Available", "Busy", "Out of Service")


@ambulances_bp.route("")
@ambulances_bp.route("/")
@login_required
def index():
    """List ambulances with search, status/type filters, and pagination."""
    db = get_db()

    search = (request.args.get("search") or "").strip()
    status_filter = (request.args.get("status") or "").strip()
    type_filter = (request.args.get("type") or "").strip()

    page = request.args.get("page", 1, type=int)
    per_page = 10
    offset = (page - 1) * per_page

    query = "SELECT * FROM ambulances WHERE 1=1"
    params = []

    if search:
        query += " AND (ambulance_code LIKE ? OR driver_name LIKE ? OR vehicle_number LIKE ?)"
        like_search = f"%{search}%"
        params.extend([like_search, like_search, like_search])

    if status_filter and status_filter in ALLOWED_STATUSES:
        query += " AND status = ?"
        params.append(status_filter)

    if type_filter and type_filter in ALLOWED_TYPES:
        query += " AND ambulance_type = ?"
        params.append(type_filter)

    # Count total for pagination
    count_query = query.replace("SELECT *", "SELECT COUNT(*)")
    total_count = db.execute(count_query, params).fetchone()[0]

    query += " ORDER BY id ASC LIMIT ? OFFSET ?"
    params.extend([per_page, offset])

    ambulances = db.execute(query, params).fetchall()
    total_pages = max(1, (total_count + per_page - 1) // per_page)

    # Annotate freshness
    annotated = []
    for amb in ambulances:
        stale = is_location_stale(amb["last_location_update"])
        annotated.append({"data": amb, "is_stale": stale})

    return render_template(
        "ambulances/index.html",
        ambulances=annotated,
        search=search,
        status_filter=status_filter,
        type_filter=type_filter,
        page=page,
        total_pages=total_pages,
        total_count=total_count,
        allowed_types=ALLOWED_TYPES,
        allowed_statuses=ALLOWED_STATUSES,
    )


@ambulances_bp.route("/add", methods=["GET", "POST"])
@login_required
def add():
    """Register a new emergency ambulance vehicle in the fleet."""
    if request.method == "POST":
        code = (request.form.get("ambulance_code") or "").strip().upper()
        driver_name = (request.form.get("driver_name") or "").strip()
        driver_phone = (request.form.get("driver_phone") or "").strip()
        vehicle_number = (request.form.get("vehicle_number") or "").strip().upper()
        amb_type = (request.form.get("ambulance_type") or "").strip()
        status = (request.form.get("status") or "Available").strip()
        lat_str = (request.form.get("latitude") or "").strip()
        lon_str = (request.form.get("longitude") or "").strip()
        notes = (request.form.get("operational_notes") or "").strip()

        errors = []
        if not code or len(code) < 3:
            errors.append("Ambulance Code must be at least 3 characters.")
        if not driver_name:
            errors.append("Driver Name is required.")
        if not driver_phone:
            errors.append("Driver Contact Number is required.")
        if not vehicle_number:
            errors.append("Vehicle Registration Number is required.")
        if amb_type not in ALLOWED_TYPES:
            errors.append(f"Invalid ambulance type. Must be one of: {', '.join(ALLOWED_TYPES)}")
        if status not in ALLOWED_STATUSES:
            errors.append(f"Invalid status. Must be one of: {', '.join(ALLOWED_STATUSES)}")

        try:
            lat = float(lat_str)
            lon = float(lon_str)
            if not validate_coordinates(lat, lon):
                errors.append("Coordinates are outside valid geographical limits (-90 to 90, -180 to 180).")
        except ValueError:
            errors.append("Latitude and Longitude must be valid floating point numbers.")

        if errors:
            for err in errors:
                flash(err, "danger")
            return render_template("ambulances/add.html", allowed_types=ALLOWED_TYPES, allowed_statuses=ALLOWED_STATUSES, form=request.form)

        db = get_db()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        try:
            cur = db.execute(
                """
                INSERT INTO ambulances (ambulance_code, driver_name, driver_phone, vehicle_number,
                                       ambulance_type, status, latitude, longitude, last_location_update,
                                       operational_notes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (code, driver_name, driver_phone, vehicle_number, amb_type, status, lat, lon, now_str, notes, now_str, now_str),
            )
            db.commit()
            amb_id = cur.lastrowid
            log_activity("AMBULANCE_CREATED", f"Registered new ambulance {code} ({amb_type}) at [{lat}, {lon}].", record_type="ambulance", record_id=amb_id)
            flash(f"Ambulance {code} successfully added to the active fleet.", "success")
            return redirect(url_for("ambulances.detail", id=amb_id))
        except sqlite3.IntegrityError as exc:
            db.rollback()
            if "UNIQUE constraint failed" in str(exc) and "ambulance_code" in str(exc):
                flash(f"Ambulance code '{code}' already exists. Please choose a unique identifier.", "danger")
            else:
                flash("Database error: Unique constraint or validation failed.", "danger")
            return render_template("ambulances/add.html", allowed_types=ALLOWED_TYPES, allowed_statuses=ALLOWED_STATUSES, form=request.form)

    return render_template("ambulances/add.html", allowed_types=ALLOWED_TYPES, allowed_statuses=ALLOWED_STATUSES, form={})


@ambulances_bp.route("/<int:id>")
@login_required
def detail(id: int):
    """View full operational details of a specific ambulance."""
    db = get_db()
    cur = db.execute("SELECT * FROM ambulances WHERE id = ?", (id,))
    amb = cur.fetchone()
    if not amb:
        abort(404, description="Ambulance record not found.")

    # Find active assignment if any
    cur = db.execute(
        """
        SELECT * FROM emergency_requests 
        WHERE assigned_ambulance_id = ? AND status IN ('Assigned', 'En Route', 'Arrived')
        ORDER BY created_at DESC LIMIT 1
        """,
        (id,),
    )
    active_request = cur.fetchone()

    # Find recent logs
    cur = db.execute(
        """
        SELECT * FROM activity_logs 
        WHERE record_type = 'ambulance' AND record_id = ?
        ORDER BY created_at DESC LIMIT 10
        """,
        (id,),
    )
    logs = cur.fetchall()

    stale = is_location_stale(amb["last_location_update"])

    return render_template(
        "ambulances/detail.html",
        ambulance=amb,
        active_request=active_request,
        logs=logs,
        is_stale=stale,
    )


@ambulances_bp.route("/<int:id>/edit", methods=["GET", "POST"])
@login_required
def edit(id: int):
    """Update details, driver assignment, or maintenance status of an ambulance."""
    db = get_db()
    cur = db.execute("SELECT * FROM ambulances WHERE id = ?", (id,))
    amb = cur.fetchone()
    if not amb:
        abort(404, description="Ambulance not found.")

    if request.method == "POST":
        code = (request.form.get("ambulance_code") or "").strip().upper()
        driver_name = (request.form.get("driver_name") or "").strip()
        driver_phone = (request.form.get("driver_phone") or "").strip()
        vehicle_number = (request.form.get("vehicle_number") or "").strip().upper()
        amb_type = (request.form.get("ambulance_type") or "").strip()
        status = (request.form.get("status") or "").strip()
        lat_str = (request.form.get("latitude") or "").strip()
        lon_str = (request.form.get("longitude") or "").strip()
        notes = (request.form.get("operational_notes") or "").strip()

        errors = []
        if not code or len(code) < 3:
            errors.append("Ambulance Code must be at least 3 characters.")
        if not driver_name:
            errors.append("Driver Name is required.")
        if not driver_phone:
            errors.append("Driver Contact Number is required.")
        if not vehicle_number:
            errors.append("Vehicle Registration Number is required.")
        if amb_type not in ALLOWED_TYPES:
            errors.append("Invalid ambulance type.")
        if status not in ALLOWED_STATUSES:
            errors.append("Invalid status.")

        try:
            lat = float(lat_str)
            lon = float(lon_str)
            if not validate_coordinates(lat, lon):
                errors.append("Coordinates are outside valid boundaries (-90 to 90, -180 to 180).")
        except ValueError:
            errors.append("Latitude and Longitude must be valid numbers.")

        # Check if code already used by another record
        cur = db.execute("SELECT id FROM ambulances WHERE ambulance_code = ? AND id != ?", (code, id))
        if cur.fetchone():
            errors.append(f"Ambulance code '{code}' is already used by another vehicle.")

        if errors:
            for err in errors:
                flash(err, "danger")
            return render_template("ambulances/edit.html", ambulance=amb, allowed_types=ALLOWED_TYPES, allowed_statuses=ALLOWED_STATUSES)

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            db.execute(
                """
                UPDATE ambulances
                SET ambulance_code = ?, driver_name = ?, driver_phone = ?,
                    vehicle_number = ?, ambulance_type = ?, status = ?,
                    latitude = ?, longitude = ?, last_location_update = ?,
                    operational_notes = ?, updated_at = ?
                WHERE id = ?
                """,
                (code, driver_name, driver_phone, vehicle_number, amb_type, status, lat, lon, now_str, notes, now_str, id),
            )
            db.commit()
            log_activity("AMBULANCE_UPDATED", f"Updated details for ambulance {code} (Status: {status}).", record_type="ambulance", record_id=id)
            flash(f"Ambulance {code} successfully updated.", "success")
            return redirect(url_for("ambulances.detail", id=id))
        except sqlite3.IntegrityError:
            db.rollback()
            flash("Database error: Could not update ambulance.", "danger")

    return render_template(
        "ambulances/edit.html",
        ambulance=amb,
        allowed_types=ALLOWED_TYPES,
        allowed_statuses=ALLOWED_STATUSES,
    )


@ambulances_bp.route("/<int:id>/delete", methods=["POST"])
@login_required
def delete(id: int):
    """Safely remove an ambulance if not involved in any active emergencies."""
    db = get_db()
    cur = db.execute("SELECT ambulance_code FROM ambulances WHERE id = ?", (id,))
    amb = cur.fetchone()
    if not amb:
        abort(404, description="Ambulance not found.")

    code = amb["ambulance_code"]

    # Safe deletion check: prevent deletion if referenced by active emergencies
    cur = db.execute(
        """
        SELECT COUNT(*) FROM emergency_requests
        WHERE assigned_ambulance_id = ? AND status IN ('Pending', 'Assigned', 'En Route', 'Arrived')
        """,
        (id,),
    )
    active_count = cur.fetchone()[0]

    if active_count > 0:
        flash(
            f"Cannot delete ambulance {code}: Vehicle is currently assigned to an active emergency call. Reassign or resolve the emergency first.",
            "danger",
        )
        return redirect(url_for("ambulances.detail", id=id))

    try:
        db.execute("DELETE FROM ambulances WHERE id = ?", (id,))
        db.commit()
        log_activity("AMBULANCE_DELETED", f"Ambulance {code} removed from fleet records.", record_type="ambulance", record_id=id)
        flash(f"Ambulance {code} has been safely removed.", "info")
        return redirect(url_for("ambulances.index"))
    except Exception as exc:
        db.rollback()
        flash(f"Could not delete ambulance: {exc}", "danger")
        return redirect(url_for("ambulances.detail", id=id))
