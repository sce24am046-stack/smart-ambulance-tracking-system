from flask import Blueprint, jsonify, render_template, request
from app.db import get_db
from app.security import login_required
from app.utils import rank_nearest_hospitals, validate_coordinates

hospitals_bp = Blueprint("hospitals", __name__, url_prefix="/hospitals")

AVAILABLE_SERVICES = ["ICU", "Trauma", "Cardiac", "Emergency", "Burn Unit", "Pediatric"]


@hospitals_bp.route("")
@hospitals_bp.route("/")
def index():
    """Hospitals directory with search, clinical service filters, and proximity ranking."""
    db = get_db()

    search = (request.args.get("search") or "").strip()
    service_filter = (request.args.get("service") or "").strip()
    origin_lat_str = (request.args.get("lat") or "").strip()
    origin_lon_str = (request.args.get("lon") or "").strip()

    # Default origin: Bengaluru City Center (Cubbon Park)
    origin_lat = 12.9716
    origin_lon = 77.5946
    has_custom_origin = False

    if origin_lat_str and origin_lon_str:
        try:
            parsed_lat = float(origin_lat_str)
            parsed_lon = float(origin_lon_str)
            if validate_coordinates(parsed_lat, parsed_lon):
                origin_lat = parsed_lat
                origin_lon = parsed_lon
                has_custom_origin = True
        except ValueError:
            pass

    # Rank hospitals by distance
    hospitals = rank_nearest_hospitals(
        origin_lat,
        origin_lon,
        service_keyword=service_filter if service_filter else None,
        limit=50,
    )

    if search:
        search_lower = search.lower()
        hospitals = [
            h for h in hospitals
            if search_lower in h["name"].lower() or search_lower in h["address"].lower()
        ]

    return render_template(
        "hospitals/index.html",
        hospitals=hospitals,
        search=search,
        service_filter=service_filter,
        available_services=AVAILABLE_SERVICES,
        origin_lat=origin_lat,
        origin_lon=origin_lon,
        has_custom_origin=has_custom_origin,
    )


@hospitals_bp.route("/api/list")
def api_list():
    """Public API endpoint returning hospital directory for maps and external lookup."""
    db = get_db()
    cur = db.execute("SELECT id, name, address, contact_number, latitude, longitude, services, is_demo_data FROM hospitals")
    rows = [dict(r) for r in cur.fetchall()]
    return jsonify({
        "status": "success",
        "count": len(rows),
        "hospitals": rows,
        "disclaimer": "Sample demonstration directory. Geographic proximity does not guarantee emergency acceptance or bed availability.",
    })
