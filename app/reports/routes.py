import csv
from datetime import datetime, timedelta
import io
from flask import (
    Blueprint,
    Response,
    current_app,
    flash,
    render_template,
    request,
)
from app.db import get_db
from app.security import log_activity, login_required, sanitize_csv_cell
from app.utils import is_location_stale

reports_bp = Blueprint("reports", __name__, url_prefix="/reports")


@reports_bp.route("")
@reports_bp.route("/")
@login_required
def index():
    """Operational analytics, breakdowns, and audit reports."""
    db = get_db()

    start_date = request.args.get("start_date", "").strip()
    end_date = request.args.get("end_date", "").strip()

    query_filter = " WHERE 1=1"
    params = []

    if start_date:
        query_filter += " AND created_at >= ?"
        params.append(f"{start_date} 00:00:00")
    if end_date:
        query_filter += " AND created_at <= ?"
        params.append(f"{end_date} 23:59:59")

    # 1. Total Requests
    total_cur = db.execute(f"SELECT COUNT(*) FROM emergency_requests {query_filter}", params)
    total_requests = total_cur.fetchone()[0]

    # 2. Requests by Status
    status_cur = db.execute(
        f"SELECT status, COUNT(*) as count FROM emergency_requests {query_filter} GROUP BY status ORDER BY count DESC",
        params,
    )
    status_data = status_cur.fetchall()

    # 3. Requests by Priority
    priority_cur = db.execute(
        f"SELECT priority, COUNT(*) as count FROM emergency_requests {query_filter} GROUP BY priority ORDER BY count DESC",
        params,
    )
    priority_data = priority_cur.fetchall()

    # 4. Requests by Emergency Category
    category_cur = db.execute(
        f"SELECT emergency_category, COUNT(*) as count FROM emergency_requests {query_filter} GROUP BY emergency_category ORDER BY count DESC",
        params,
    )
    category_data = category_cur.fetchall()

    # 5. Ambulance Fleet Utilization
    fleet_cur = db.execute(
        """
        SELECT a.ambulance_code, a.ambulance_type, a.status, a.last_location_update,
               COUNT(r.id) as total_assigned,
               SUM(CASE WHEN r.status = 'Completed' THEN 1 ELSE 0 END) as completed_missions
        FROM ambulances a
        LEFT JOIN emergency_requests r ON a.id = r.assigned_ambulance_id
        GROUP BY a.id
        ORDER BY completed_missions DESC, total_assigned DESC
        """
    )
    fleet_utilization = []
    for f in fleet_cur.fetchall():
        fleet_utilization.append({
            "code": f["ambulance_code"],
            "type": f["ambulance_type"],
            "status": f["status"],
            "last_update": f["last_location_update"],
            "is_stale": is_location_stale(f["last_location_update"]),
            "total_assigned": f["total_assigned"],
            "completed_missions": f["completed_missions"],
        })

    return render_template(
        "reports/index.html",
        total_requests=total_requests,
        status_data=status_data,
        priority_data=priority_data,
        category_data=category_data,
        fleet_utilization=fleet_utilization,
        start_date=start_date,
        end_date=end_date,
    )


@reports_bp.route("/fleet-health")
@login_required
def fleet_health():
    """Fleet Health & Telemetry Freshness Audit Console."""
    db = get_db()
    stale_threshold = current_app.config.get("STALE_LOCATION_THRESHOLD_MINUTES", 15)

    cur = db.execute("SELECT * FROM ambulances ORDER BY status ASC, ambulance_code ASC")
    rows = cur.fetchall()

    healthy_count = 0
    stale_count = 0
    out_of_service_count = 0

    fleet = []
    for r in rows:
        stale = is_location_stale(r["last_location_update"], stale_threshold)
        if r["status"] == "Out of Service":
            out_of_service_count += 1
        elif stale:
            stale_count += 1
        else:
            healthy_count += 1

        fleet.append({
            "id": r["id"],
            "code": r["ambulance_code"],
            "driver": r["driver_name"],
            "phone": r["driver_phone"],
            "vehicle": r["vehicle_number"],
            "type": r["ambulance_type"],
            "status": r["status"],
            "lat": r["latitude"],
            "lon": r["longitude"],
            "last_update": r["last_location_update"],
            "is_stale": stale,
            "notes": r["operational_notes"],
        })

    return render_template(
        "reports/fleet_health.html",
        fleet=fleet,
        healthy_count=healthy_count,
        stale_count=stale_count,
        out_of_service_count=out_of_service_count,
        stale_threshold=stale_threshold,
    )


@reports_bp.route("/export/csv")
@login_required
def export_csv():
    """
    SECURE CSV REPORT EXPORT:
    Enforces authorization check and sanitizes all cell contents against spreadsheet formula injection (CWE-1236).
    """
    db = get_db()

    start_date = request.args.get("start_date", "").strip()
    end_date = request.args.get("end_date", "").strip()
    status_filter = request.args.get("status", "").strip()

    query = """
        SELECT r.request_code, r.patient_name, r.contact_number, r.emergency_category,
               r.pickup_address, r.priority, r.suggested_priority, r.status,
               a.ambulance_code, a.driver_name, r.assigned_at, r.arrived_at,
               r.completed_at, r.created_at
        FROM emergency_requests r
        LEFT JOIN ambulances a ON r.assigned_ambulance_id = a.id
        WHERE 1=1
    """
    params = []

    if start_date:
        query += " AND r.created_at >= ?"
        params.append(f"{start_date} 00:00:00")
    if end_date:
        query += " AND r.created_at <= ?"
        params.append(f"{end_date} 23:59:59")
    if status_filter:
        query += " AND r.status = ?"
        params.append(status_filter)

    query += " ORDER BY r.created_at DESC"
    records = db.execute(query, params).fetchall()

    # Generate CSV using in-memory string buffer
    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)

    # Headers
    headers = [
        "Request Code",
        "Patient Name",
        "Contact Number",
        "Category",
        "Pickup Address",
        "Priority",
        "Suggested Priority",
        "Status",
        "Assigned Ambulance",
        "Driver Name",
        "Assigned At",
        "Arrived At",
        "Completed At",
        "Created At",
    ]
    writer.writerow(headers)

    # Sanitize every single data cell to protect against formula injection
    for row in records:
        sanitized_row = [sanitize_csv_cell(row[col]) for col in range(len(headers))]
        writer.writerow(sanitized_row)

    output.seek(0)
    filename = f"emergency_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    log_activity(
        "REPORT_EXPORT",
        f"Exported emergency requests CSV report ({len(records)} records).",
        record_type="system",
    )

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
