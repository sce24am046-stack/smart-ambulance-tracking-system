def test_public_landing_page(client):
    """Test public access to home landing page."""
    res = client.get("/")
    assert res.status_code == 200
    assert b"RESQ PULSE" in res.data
    assert b"Every Second Matters" in res.data


def test_protected_routes_require_authentication(client):
    """Verify that all core operations routes reject unauthenticated sessions."""
    protected_urls = [
        "/dashboard",
        "/ambulances",
        "/ambulances/add",
        "/emergencies",
        "/emergencies/new",
        "/tracking",
        "/reports",
        "/reports/fleet-health",
    ]

    for url in protected_urls:
        res = client.get(url)
        assert res.status_code == 302, f"URL {url} failed to protect unauthenticated access."
        assert "/auth/login" in res.headers["Location"]


def test_csrf_protection_on_post(client):
    """Verify that state-changing requests without valid CSRF token are blocked."""
    # Attempting POST without CSRF token
    res = client.post(
        "/emergency/register",
        data={
            "patient_name": "Test Name",
            "contact_number": "+91-99999-11111",
            "emergency_category": "Accident",
            "pickup_address": "Test Street",
        },
    )
    # Must fail with 400 Bad Request
    assert res.status_code == 400
    assert b"CSRF" in res.data or b"Bad Request" in res.data


def test_gps_location_api_requires_auth(client):
    """Verify that location update endpoint requires valid session or X-API-Key."""
    # Unauthenticated request without header
    res = client.put(
        "/api/v1/ambulances/1/location",
        json={"latitude": 12.9800, "longitude": 77.6100},
    )
    assert res.status_code == 401

    # Request with valid X-API-Key
    res_auth = client.put(
        "/api/v1/ambulances/1/location",
        json={"latitude": 12.9800, "longitude": 77.6100},
        headers={"X-API-Key": "resq-pulse-demo-gps-key"},
    )
    assert res_auth.status_code == 200
    data = res_auth.get_json()
    assert data["status"] == "success"
    assert data["latitude"] == 12.9800
