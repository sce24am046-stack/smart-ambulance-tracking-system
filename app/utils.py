import json
import math
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from flask import current_app
from app.db import get_db

EARTH_RADIUS_KM = 6371.0


def format_eta_clock(duration_minutes: float) -> str:
    """Format duration into estimated clock arrival time (e.g., '10:45 PM')."""
    if duration_minutes is None or duration_minutes <= 0:
        return "Now"
    arrival_time = datetime.now() + timedelta(minutes=float(duration_minutes))
    return arrival_time.strftime("%I:%M %p")


def calculate_eta_metadata(
    distance_km: float,
    duration_minutes: float,
    provider_name: str,
    is_traffic_aware: bool = False,
    is_stale_telemetry: bool = False,
    calculated_at: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Constructs standardized ETA metadata compliant with project requirements.
    Never claims traffic accuracy when data is stale or provider lacks traffic feeds.
    """
    now_str = calculated_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if is_traffic_aware and not is_stale_telemetry:
        eta_type = "provider-traffic"
        type_label = f"Live Traffic-Aware ETA ({provider_name})"
        disclaimer = "Incorporates real-time traffic sensor feeds. Traffic conditions fluctuate dynamically."
    elif "OSRM" in provider_name or "OpenStreetMap" in provider_name or "Road" in provider_name:
        eta_type = "provider-road"
        type_label = f"Road Network Routing ({provider_name})"
        disclaimer = "Calculated via actual street network geometry. Live traffic congestion data unavailable."
    else:
        eta_type = "demonstration-speed"
        type_label = "Demonstration Estimate (Distance & Speed)"
        disclaimer = "Preliminary straight-line estimate using assumed 40 km/h city velocity. Actual road navigation varies."

    if is_stale_telemetry:
        disclaimer += " Warning: Vehicle telemetry is older than freshness threshold."

    return {
        "duration_minutes": round(duration_minutes, 1),
        "eta_clock": format_eta_clock(duration_minutes),
        "distance_km": round(distance_km, 2),
        "eta_type": eta_type,
        "type_label": type_label,
        "is_traffic_aware": is_traffic_aware and not is_stale_telemetry,
        "is_stale_telemetry": is_stale_telemetry,
        "last_calculated": now_str,
        "disclaimer": disclaimer,
    }


def recalculate_active_route(request_id: int, force_refresh: bool = False) -> Optional[Dict[str, Any]]:
    """
    Recalculates road navigation and ETA for an active emergency request from its
    assigned ambulance coordinates to the pickup address (and destination hospital if assigned).
    """
    from app.routing import get_cached_route, get_routing_provider

    db = get_db()
    cur = db.execute(
        """
        SELECT r.id, r.request_code, r.pickup_latitude, r.pickup_longitude,
               r.status, r.assigned_ambulance_id, r.destination_hospital_id,
               r.route_geojson, r.route_distance_km, r.route_duration_minutes,
               r.route_provider, r.route_traffic_aware, r.route_last_calculated,
               a.latitude as amb_lat, a.longitude as amb_lon, a.last_location_update
        FROM emergency_requests r
        LEFT JOIN ambulances a ON r.assigned_ambulance_id = a.id
        WHERE r.id = ?
        """,
        (request_id,),
    )
    row = cur.fetchone()
    if not row or not row["assigned_ambulance_id"] or row["amb_lat"] is None:
        return None

    # Calculate route from ambulance to emergency scene
    amb_lat = row["amb_lat"]
    amb_lon = row["amb_lon"]
    pickup_lat = row["pickup_latitude"]
    pickup_lon = row["pickup_longitude"]

    provider = get_routing_provider()
    route_data = get_cached_route(
        amb_lat,
        amb_lon,
        pickup_lat,
        pickup_lon,
        provider=provider,
        ttl_seconds=current_app.config.get("ROUTING_CACHE_TTL_SECONDS", 300),
        force_refresh=force_refresh,
    )

    rec_route = route_data.get("recommended_route", {})
    dist_km = rec_route.get("distance_km", 0.0)
    dur_mins = rec_route.get("duration_traffic_minutes") or rec_route.get("duration_minutes", 0.0)
    route_json = json.dumps(rec_route.get("geometry", []))
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    db.execute(
        """
        UPDATE emergency_requests
        SET route_geojson = ?, route_distance_km = ?, route_duration_minutes = ?,
            route_provider = ?, route_traffic_aware = ?, route_last_calculated = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            route_json,
            dist_km,
            dur_mins,
            route_data.get("provider_name", "OSRM"),
            1 if route_data.get("is_traffic_aware") else 0,
            now_str,
            now_str,
            request_id,
        ),
    )
    db.commit()

    is_stale = is_location_stale(row["last_location_update"])
    route_data["eta_metadata"] = calculate_eta_metadata(
        dist_km,
        dur_mins,
        route_data.get("provider_name", "OSRM"),
        is_traffic_aware=route_data.get("is_traffic_aware", False),
        is_stale_telemetry=is_stale,
        calculated_at=now_str,
    )

    return route_data


def validate_coordinates(lat: float, lon: float) -> bool:
    """Validate that coordinates are within permissible earthly ranges."""
    try:
        lat_f = float(lat)
        lon_f = float(lon)
        return -90.0 <= lat_f <= 90.0 and -180.0 <= lon_f <= 180.0
    except (ValueError, TypeError):
        return False


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great-circle distance between two points on Earth using the Haversine formula.
    
    Returns:
        Distance in kilometers rounded to two decimal places.
    """
    lat1_rad = math.radians(float(lat1))
    lon1_rad = math.radians(float(lon1))
    lat2_rad = math.radians(float(lat2))
    lon2_rad = math.radians(float(lon2))

    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad

    a = math.sin(dlat / 2.0) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))

    distance = EARTH_RADIUS_KM * c
    return round(distance, 2)


def estimate_travel_time(distance_km: float, speed_kmh: Optional[float] = None) -> float:
    """
    Estimate straight-line travel time in minutes based on assumed city travel speed.
    Note: Real travel times depend on live traffic, road geometry, and traffic signals.
    """
    if speed_kmh is None:
        speed_kmh = current_app.config.get("ASSUMED_CITY_SPEED_KMH", 40.0)
    if speed_kmh <= 0:
        speed_kmh = 40.0

    travel_hours = distance_km / speed_kmh
    travel_minutes = travel_hours * 60.0
    return round(max(travel_minutes, 1.0), 1)


def suggest_priority(category: str, notes: str = "") -> Dict[str, str]:
    """
    Transparent rule-based priority recommendation engine.
    College project note: Rule-based recommendation for educational triage demonstration;
    not intended for actual medical diagnosis.
    """
    category_lower = (category or "").strip().lower()
    notes_lower = (notes or "").strip().lower()

    if category_lower == "cardiac concern":
        return {
            "priority": "High",
            "rationale": "Cardiac symptoms carry acute risk of myocardial infarction or arrhythmia; immediate Advanced Life Support is prioritized.",
        }
    elif category_lower == "accident":
        # Check notes for severe trauma signals
        if any(w in notes_lower for w in ("unconscious", "head injury", "severe", "crush", "heavy bleeding")):
            return {
                "priority": "High",
                "rationale": "Accident report indicates high-energy impact, severe bleeding, or altered consciousness; top priority trauma response recommended.",
            }
        return {
            "priority": "High",
            "rationale": "Trauma and road accidents require rapid scene assessment and trauma protocol activation.",
        }
    elif category_lower == "medical emergency":
        if any(w in notes_lower for w in ("breathing", "choking", "seizure", "stroke", "unresponsive")):
            return {
                "priority": "High",
                "rationale": "Medical report cites respiratory compromise or neurological signs; elevated to High priority.",
            }
        return {
            "priority": "Medium",
            "rationale": "Acute medical condition requiring rapid assessment and stabilized ambulance transport.",
        }
    else:  # "Other"
        return {
            "priority": "Low",
            "rationale": "Routine patient transport or non-urgent medical assist where vital stability is not immediately compromised.",
        }


def rank_available_ambulances(
    pickup_lat: float,
    pickup_lon: float,
    preferred_type: Optional[str] = None,
    limit: int = 5,
) -> List[Dict]:
    """
    SMART DISPATCH ASSIST:
    Identifies available ambulances, computes straight-line distance & estimated travel time,
    and returns ranked candidates with clear decision rationales.
    """
    db = get_db()
    speed_kmh = current_app.config.get("ASSUMED_CITY_SPEED_KMH", 40.0)

    # Fetch ambulances marked 'Available'
    cur = db.execute(
        """
        SELECT id, ambulance_code, driver_name, driver_phone, vehicle_number,
               ambulance_type, status, latitude, longitude, last_location_update, operational_notes
        FROM ambulances
        WHERE status = 'Available'
        """
    )
    rows = cur.fetchall()

    candidates = []
    for row in rows:
        amb_lat = row["latitude"]
        amb_lon = row["longitude"]

        dist = haversine_distance(pickup_lat, pickup_lon, amb_lat, amb_lon)
        est_time = estimate_travel_time(dist, speed_kmh)

        # Build transparent explanation
        notes = []
        if preferred_type and preferred_type in row["ambulance_type"]:
            notes.append(f"Direct match for preferred {preferred_type} capability.")
        elif "Advanced Life Support" in row["ambulance_type"]:
            notes.append("Equipped with ALS advanced resuscitation systems.")
        else:
            notes.append(f"{row['ambulance_type']} ready for immediate deployment.")

        is_stale = is_location_stale(row["last_location_update"])
        if is_stale:
            notes.append("Warning: GPS coordinates older than freshness threshold.")

        candidates.append({
            "id": row["id"],
            "ambulance_code": row["ambulance_code"],
            "driver_name": row["driver_name"],
            "driver_phone": row["driver_phone"],
            "vehicle_number": row["vehicle_number"],
            "ambulance_type": row["ambulance_type"],
            "status": row["status"],
            "latitude": amb_lat,
            "longitude": amb_lon,
            "last_location_update": row["last_location_update"],
            "distance_km": dist,
            "estimated_minutes": est_time,
            "is_stale": is_stale,
            "operational_notes": row["operational_notes"],
            "explanation": " ".join(notes),
        })

    # Sort strictly by distance ascending (closest first)
    candidates.sort(key=lambda x: x["distance_km"])

    # Add ranking badge
    for idx, c in enumerate(candidates, start=1):
        c["rank"] = idx

    return candidates[:limit]


def rank_nearest_hospitals(
    origin_lat: float,
    origin_lon: float,
    service_keyword: Optional[str] = None,
    limit: int = 10,
) -> List[Dict]:
    """
    Calculates distance and travel time to all registered hospitals,
    optionally filtering by required clinical service.
    """
    db = get_db()
    speed_kmh = current_app.config.get("ASSUMED_CITY_SPEED_KMH", 40.0)

    query = "SELECT id, name, address, contact_number, latitude, longitude, services, is_demo_data FROM hospitals"
    params = []

    if service_keyword and service_keyword.strip():
        query += " WHERE services LIKE ?"
        params.append(f"%{service_keyword.strip()}%")

    cur = db.execute(query, params)
    rows = cur.fetchall()

    hospitals = []
    for r in rows:
        dist = haversine_distance(origin_lat, origin_lon, r["latitude"], r["longitude"])
        est_time = estimate_travel_time(dist, speed_kmh)
        hospitals.append({
            "id": r["id"],
            "name": r["name"],
            "address": r["address"],
            "contact_number": r["contact_number"],
            "latitude": r["latitude"],
            "longitude": r["longitude"],
            "services": r["services"],
            "is_demo_data": bool(r["is_demo_data"]),
            "distance_km": dist,
            "estimated_minutes": est_time,
        })

    hospitals.sort(key=lambda x: x["distance_km"])
    for idx, h in enumerate(hospitals, start=1):
        h["rank"] = idx

    return hospitals[:limit]


def is_location_stale(timestamp_val, threshold_minutes: Optional[int] = None) -> bool:
    """Determine whether recorded GPS coordinates have exceeded the freshness threshold."""
    if not timestamp_val:
        return True
    if threshold_minutes is None:
        threshold_minutes = current_app.config.get("STALE_LOCATION_THRESHOLD_MINUTES", 15)

    try:
        if isinstance(timestamp_val, str):
            # Parse typical SQLite timestamp formats
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
                try:
                    dt = datetime.strptime(timestamp_val, fmt)
                    break
                except ValueError:
                    continue
            else:
                return False
        elif isinstance(timestamp_val, datetime):
            dt = timestamp_val
        else:
            return False

        delta = datetime.now() - dt
        return delta > timedelta(minutes=threshold_minutes)
    except Exception:
        return False
