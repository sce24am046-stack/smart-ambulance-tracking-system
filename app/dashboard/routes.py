from datetime import datetime, timedelta
from flask import Blueprint, jsonify, render_template
from app.db import get_db
from app.security import login_required

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")


@dashboard_bp.route("")
@dashboard_bp.route("/")
@login_required
def index():
    """Operations Dashboard: Real-time mission control center."""
    db = get_db()

    # 1. Ambulance Status Counts
    cur = db.execute(
        """
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN status = 'Available' THEN 1 ELSE 0 END) as available,
            SUM(CASE WHEN status = 'Busy' THEN 1 ELSE 0 END) as busy,
            SUM(CASE WHEN status = 'Out of Service' THEN 1 ELSE 0 END) as out_of_service
        FROM ambulances
        """
    )
    amb_counts = cur.fetchone()
    total_ambulances = amb_counts["total"] or 0
    available_ambulances = amb_counts["available"] or 0
    busy_ambulances = amb_counts["busy"] or 0
    out_of_service_ambulances = amb_counts["out_of_service"] or 0

    availability_pct = round((available_ambulances / total_ambulances * 100), 1) if total_ambulances > 0 else 0

    # 2. Emergency Request Counts
    cur = db.execute(
        """
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN status IN ('Pending', 'Assigned', 'En Route', 'Arrived') THEN 1 ELSE 0 END) as open_reqs,
            SUM(CASE WHEN priority = 'High' AND status IN ('Pending', 'Assigned', 'En Route', 'Arrived') THEN 1 ELSE 0 END) as high_priority,
            SUM(CASE WHEN status = 'Pending' THEN 1 ELSE 0 END) as pending_reqs,
            SUM(CASE WHEN status = 'Completed' THEN 1 ELSE 0 END) as completed_reqs
        FROM emergency_requests
        """
    )
    req_counts = cur.fetchone()
    total_requests = req_counts["total"] or 0
    open_requests = req_counts["open_reqs"] or 0
    high_priority_requests = req_counts["high_priority"] or 0
    pending_requests = req_counts["pending_reqs"] or 0

    # 3. Average Response Time calculation (assigned_at to arrived_at)
    # Using real recorded timestamps only - never fabricated
    cur = db.execute(
        """
        SELECT assigned_at, arrived_at, completed_at
        FROM emergency_requests
        WHERE assigned_at IS NOT NULL AND (arrived_at IS NOT NULL OR completed_at IS NOT NULL)
        """
    )
    rows = cur.fetchall()
    response_times_minutes = []
    for r in rows:
        try:
            t_start = datetime.strptime(r["assigned_at"], "%Y-%m-%d %H:%M:%S")
            end_val = r["arrived_at"] or r["completed_at"]
            t_end = datetime.strptime(end_val, "%Y-%m-%d %H:%M:%S")
            delta = (t_end - t_start).total_seconds() / 60.0
            if delta > 0:
                response_times_minutes.append(delta)
        except Exception:
            continue

    avg_response_time = (
        round(sum(response_times_minutes) / len(response_times_minutes), 1)
        if response_times_minutes
        else None
    )

    # 4. Priority Queue (Unresolved requests sorted by priority: High > Medium > Low, then created_at)
    cur = db.execute(
        """
        SELECT r.id, r.request_code, r.patient_name, r.emergency_category,
               r.pickup_address, r.priority, r.status, r.created_at,
               a.ambulance_code, a.driver_name
        FROM emergency_requests r
        LEFT JOIN ambulances a ON r.assigned_ambulance_id = a.id
        WHERE r.status IN ('Pending', 'Assigned', 'En Route', 'Arrived')
        ORDER BY 
            CASE r.priority 
                WHEN 'High' THEN 1 
                WHEN 'Medium' THEN 2 
                WHEN 'Low' THEN 3 
                ELSE 4 
            END ASC,
            r.created_at ASC
        LIMIT 10
        """
    )
    priority_queue = cur.fetchall()

    # 5. Recent Activity Log
    cur = db.execute(
        """
        SELECT id, event_type, record_type, record_id, actor_username, description, created_at
        FROM activity_logs
        ORDER BY created_at DESC
        LIMIT 8
        """
    )
    recent_activity = cur.fetchall()

    # 6. Trend data for Chart.js: Last 7 Days Request Counts
    seven_days_ago = (datetime.now() - timedelta(days=6)).replace(hour=0, minute=0, second=0)
    cur = db.execute(
        """
        SELECT DATE(created_at) as req_date, COUNT(*) as count
        FROM emergency_requests
        WHERE created_at >= ?
        GROUP BY DATE(created_at)
        ORDER BY req_date ASC
        """,
        (seven_days_ago.strftime("%Y-%m-%d %H:%M:%S"),),
    )
    trend_rows = dict(cur.fetchall())

    trend_labels = []
    trend_data = []
    for i in range(7):
        day_date = (seven_days_ago + timedelta(days=i)).strftime("%Y-%m-%d")
        day_label = (seven_days_ago + timedelta(days=i)).strftime("%b %d")
        trend_labels.append(day_label)
        trend_data.append(trend_rows.get(day_date, 0))

    return render_template(
        "dashboard/index.html",
        total_ambulances=total_ambulances,
        available_ambulances=available_ambulances,
        busy_ambulances=busy_ambulances,
        out_of_service_ambulances=out_of_service_ambulances,
        availability_pct=availability_pct,
        total_requests=total_requests,
        open_requests=open_requests,
        high_priority_requests=high_priority_requests,
        pending_requests=pending_requests,
        avg_response_time=avg_response_time,
        priority_queue=priority_queue,
        recent_activity=recent_activity,
        trend_labels=trend_labels,
        trend_data=trend_data,
    )
