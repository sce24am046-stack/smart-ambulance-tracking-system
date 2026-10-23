"""
Tests for Live Tracking, ETA Engine, Routing Adapters, Rate Limiting, and Public Privacy.
"""

from datetime import datetime, timedelta
import pytest

from app.routing import (
    BaseRoutingProvider,
    OfflineFallbackProvider,
    get_cached_route,
    has_moved_significantly,
)
from app.security import (
    _last_telemetry_times,
    check_telemetry_rate_limit,
    generate_tracking_token,
    hash_token,
)
from app.utils import calculate_eta_metadata, format_eta_clock


def test_telemetry_rate_limiting():
    """Verify that location update frequency is strictly throttled to prevent spam."""
    _last_telemetry_times.clear()
    ambulance_id = 999
    min_interval = 2

    # First update should be allowed
    allowed, retry_after = check_telemetry_rate_limit(ambulance_id, min_interval_seconds=min_interval)
    assert allowed is True
    assert retry_after == 0

    # Immediate second update should be rejected with retry_after
    allowed2, retry_after2 = check_telemetry_rate_limit(ambulance_id, min_interval_seconds=min_interval)
    assert allowed2 is False
    assert retry_after2 > 0


def test_telemetry_future_timestamp_rejected(auth_client):
    """Ensure coordinates stamped with future times (>60s skew) are rejected with 422."""
    _last_telemetry_times.clear()
    future_time = (datetime.now() + timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")

    res = auth_client.put(
        "/api/v1/ambulances/1/location",
        json={
            "latitude": 12.9716,
            "longitude": 77.5946,
            "timestamp": future_time,
        },
    )
    assert res.status_code == 422
    data = res.get_json()
    assert "future" in data["message"].lower()


def test_telemetry_out_of_bounds_coordinates_rejected(auth_client):
    """Ensure invalid geographic latitude/longitude values are rejected with 422."""
    _last_telemetry_times.clear()
    res = auth_client.put(
        "/api/v1/ambulances/1/location",
        json={
            "latitude": 95.0,  # Invalid latitude (>90)
            "longitude": 77.5946,
        },
    )
    assert res.status_code == 422


def test_telemetry_unauthorized_rejection(client):
    """Ensure unauthenticated clients without API key cannot push coordinates."""
    res = client.put(
        "/api/v1/ambulances/1/location",
        json={"latitude": 12.9716, "longitude": 77.5946},
    )
    assert res.status_code == 401


def test_telemetry_api_key_authorized(client, app):
    """Ensure valid GPS hardware X-API-Key grants coordinate ingestion access."""
    _last_telemetry_times.clear()
    test_key = app.config.get("GPS_TRACKER_API_KEY", "resq-pulse-gps-tracker-dev-key")

    res = client.put(
        "/api/v1/ambulances/2/location",
        headers={"X-API-Key": test_key},
        json={"latitude": 12.9352, "longitude": 77.6245},
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    assert data["ambulance_id"] == 2


def test_public_tracking_privacy_redaction(client, app):
    """
    CRITICAL SECURITY CHECK:
    Public tracking URL and API must NEVER leak patient names, contact numbers,
    or driver telephone numbers.
    """
    with app.app_context():
        from app.db import get_db

        db = get_db()
        cur = db.execute(
            """
            SELECT tracking_token, patient_name, contact_number
            FROM emergency_requests
            WHERE tracking_token IS NOT NULL AND status IN ('Assigned', 'En Route')
            LIMIT 1
            """
        )
        req = cur.fetchone()

        if not req:
            cur = db.execute("SELECT tracking_token, patient_name, contact_number FROM emergency_requests LIMIT 1")
            req = cur.fetchone()

        token = req["tracking_token"]
        patient_name = req["patient_name"]
        patient_phone = req["contact_number"]

    # 1. Test Public HTML page
    res_html = client.get(f"/track/{token}")
    assert res_html.status_code == 200
    html_text = res_html.get_data(as_text=True)

    # Assert patient private details are completely absent
    assert patient_name not in html_text
    assert patient_phone not in html_text

    # 2. Test Public JSON API
    res_api = client.get(f"/api/v1/track/{token}/live")
    assert res_api.status_code == 200
    api_text = res_api.get_data(as_text=True)

    assert patient_name not in api_text
    assert patient_phone not in api_text
    assert "driver_phone" not in api_text


def test_public_tracking_token_revocation(client, app, auth_client):
    """Ensure revoked tokens return HTTP 403 Forbidden."""
    with app.app_context():
        from app.db import get_db

        db = get_db()
        cur = db.execute("SELECT id, tracking_token FROM emergency_requests WHERE tracking_token IS NOT NULL LIMIT 1")
        req = cur.fetchone()
        req_id = req["id"]
        token = req["tracking_token"]

    with auth_client.session_transaction() as sess:
        csrf_token = sess.get("_csrf_token", "test-csrf-token")

    # Dispatcher revokes access
    res_revoke = auth_client.post(
        f"/emergencies/{req_id}/revoke-token",
        data={"csrf_token": csrf_token},
        follow_redirects=True,
    )
    assert res_revoke.status_code == 200

    # Public client attempt to access revoked token returns 403
    res_track = client.get(f"/track/{token}")
    assert res_track.status_code == 403
    assert "Revoked" in res_track.get_data(as_text=True)

    # API attempt returns 403
    res_api = client.get(f"/api/v1/track/{token}/live")
    assert res_api.status_code == 403


def test_public_tracking_token_expiration(client, app):
    """Ensure expired tracking tokens return HTTP 410 Gone."""
    with app.app_context():
        from app.db import get_db

        db = get_db()
        expired_time = (datetime.now() - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
        token, token_hash, _ = generate_tracking_token()

        db.execute(
            """
            INSERT INTO emergency_requests (
                request_code, patient_name, contact_number, pickup_address,
                pickup_latitude, pickup_longitude, priority, suggested_priority, emergency_category,
                status, tracking_token, tracking_token_hash, tracking_token_expires_at,
                created_at, updated_at
            ) VALUES (
                'TEST-EXP-01', 'Private Patient', '9999999999', 'MG Road',
                12.9750, 77.6090, 'High', 'High', 'Cardiac Concern', 'Assigned',
                ?, ?, ?, datetime('now'), datetime('now')
            )
            """,
            (token, token_hash, expired_time),
        )
        db.commit()

    res = client.get(f"/track/{token}")
    assert res.status_code == 410
    assert "Expired" in res.get_data(as_text=True)

    # API also returns 410
    res_api = client.get(f"/api/v1/track/{token}/live")
    assert res_api.status_code == 410


def test_invalid_tracking_token_404(client):
    """Ensure non-existent token returns 404."""
    res = client.get("/track/completely-bogus-token-xyz-123456789")
    assert res.status_code == 404


def test_offline_fallback_routing_provider():
    """Verify that offline provider calculates distance and straight-line geometry gracefully."""
    provider = OfflineFallbackProvider()
    origin = (12.9716, 77.5946)
    dest = (12.9352, 77.6245)

    result = provider.calculate_route(origin[0], origin[1], dest[0], dest[1])

    assert result["is_traffic_aware"] is False
    assert result["recommended_route"]["distance_km"] > 0
    assert result["recommended_route"]["duration_minutes"] > 0
    assert len(result["recommended_route"]["geometry"]) >= 2
    assert "Straight-line" in result["provider_name"] or "Straight-line" in result["disclaimer"]


def test_eta_metadata_labeling():
    """Verify ETA labeling distinguishes traffic-aware vs standard road vs demonstration speed."""
    # 1. Traffic-aware
    meta_traffic = calculate_eta_metadata(5.0, 15.0, "Mapbox Directions (Traffic)", is_traffic_aware=True)
    assert meta_traffic["is_traffic_aware"] is True
    assert "Traffic-Aware" in meta_traffic["type_label"]
    assert meta_traffic["eta_clock"] is not None

    # 2. Road Provider (OSRM)
    meta_osrm = calculate_eta_metadata(5.0, 15.0, "OSRM OpenStreetMap", is_traffic_aware=False)
    assert meta_osrm["is_traffic_aware"] is False
    assert "Road Network" in meta_osrm["type_label"]
    assert "Live traffic congestion data unavailable" in meta_osrm["disclaimer"]

    # 3. Demonstration estimate (when stale)
    meta_stale = calculate_eta_metadata(5.0, 15.0, "OSRM", is_stale_telemetry=True)
    assert meta_stale["is_stale_telemetry"] is True


def test_has_moved_significantly():
    """Verify that movement threshold of 50m accurately detects vehicle transitions."""
    # Identical position
    assert has_moved_significantly(12.9716, 77.5946, 12.9716, 77.5946, threshold_meters=50.0) is False

    # Tiny jitter (~2 meters)
    assert has_moved_significantly(12.97160, 77.59460, 12.97161, 77.59461, threshold_meters=50.0) is False

    # Significant movement (~500 meters)
    assert has_moved_significantly(12.9716, 77.5946, 12.9750, 77.5980, threshold_meters=50.0) is True


def test_dispatcher_destination_and_recalculate_endpoints(auth_client, app):
    """Test dispatcher controls for setting hospital destination and recalculating route."""
    with app.app_context():
        from app.db import get_db

        db = get_db()
        cur = db.execute("SELECT id FROM emergency_requests WHERE assigned_ambulance_id IS NOT NULL LIMIT 1")
        req = cur.fetchone()
        req_id = req["id"]

    with auth_client.session_transaction() as sess:
        csrf_token = sess.get("_csrf_token", "test-csrf-token")

    # Set destination hospital to hospital ID 2
    res_dest = auth_client.post(
        f"/emergencies/{req_id}/destination",
        data={"csrf_token": csrf_token, "hospital_id": 2},
        follow_redirects=True,
    )
    assert res_dest.status_code == 200

    # Recalculate route
    res_recalc = auth_client.post(
        f"/emergencies/{req_id}/recalculate-route",
        data={"csrf_token": csrf_token},
        follow_redirects=True,
    )
    assert res_recalc.status_code == 200
