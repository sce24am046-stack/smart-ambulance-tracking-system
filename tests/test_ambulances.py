from app.db import get_db


def test_ambulance_list(auth_client):
    """Test authenticated access to ambulance fleet registry."""
    res = auth_client.get("/ambulances")
    assert res.status_code == 200
    assert b"Fleet Registry" in res.data
    assert b"AMB-101" in res.data


def test_add_ambulance_success(app, auth_client):
    """Test adding a new ambulance vehicle."""
    with auth_client.session_transaction() as sess:
        token = sess["_csrf_token"]

    res = auth_client.post(
        "/ambulances/add",
        data={
            "csrf_token": token,
            "ambulance_code": "AMB-999",
            "driver_name": "Ravi Shastri",
            "driver_phone": "+91-98888-11111",
            "vehicle_number": "KA-01-EA-9999",
            "ambulance_type": "Advanced Life Support (ALS)",
            "status": "Available",
            "latitude": "12.9750",
            "longitude": "77.6000",
            "operational_notes": "Test ALS vehicle with oxygen and defibrillator",
        },
        follow_redirects=True,
    )
    assert res.status_code == 200
    assert b"AMB-999" in res.data

    with app.app_context():
        db = get_db()
        cur = db.execute("SELECT * FROM ambulances WHERE ambulance_code = 'AMB-999'")
        amb = cur.fetchone()
        assert amb is not None
        assert amb["driver_name"] == "Ravi Shastri"
        assert amb["status"] == "Available"


def test_add_duplicate_ambulance_code_rejected(auth_client):
    """Test that adding an existing ambulance code is rejected."""
    with auth_client.session_transaction() as sess:
        token = sess["_csrf_token"]

    # AMB-101 already exists from seed
    res = auth_client.post(
        "/ambulances/add",
        data={
            "csrf_token": token,
            "ambulance_code": "AMB-101",
            "driver_name": "Duplicate Driver",
            "driver_phone": "+91-98888-22222",
            "vehicle_number": "KA-01-EA-0000",
            "ambulance_type": "Basic Life Support (BLS)",
            "status": "Available",
            "latitude": "12.9750",
            "longitude": "77.6000",
        },
        follow_redirects=True,
    )
    assert res.status_code == 200
    assert b"already exists" in res.data


def test_invalid_coordinates_rejected(auth_client):
    """Test that coordinates outside earthly boundaries are rejected."""
    with auth_client.session_transaction() as sess:
        token = sess["_csrf_token"]

    res = auth_client.post(
        "/ambulances/add",
        data={
            "csrf_token": token,
            "ambulance_code": "AMB-888",
            "driver_name": "Test Driver",
            "driver_phone": "+91-98888-33333",
            "vehicle_number": "KA-01-EA-8888",
            "ambulance_type": "Basic Life Support (BLS)",
            "status": "Available",
            "latitude": "195.0",  # Out of bounds (>90)
            "longitude": "77.6000",
        },
        follow_redirects=True,
    )
    assert res.status_code == 200
    assert b"Coordinates are outside valid" in res.data or b"boundaries" in res.data


def test_safe_delete_prevention_on_active_request(app, auth_client):
    """Test that an ambulance assigned to an active emergency cannot be deleted."""
    with auth_client.session_transaction() as sess:
        token = sess["_csrf_token"]

    # In seed data, AMB-103 (id 3) is assigned to REQ-2026-0001 (En Route)
    res = auth_client.post(
        "/ambulances/3/delete",
        data={"csrf_token": token},
        follow_redirects=True,
    )
    assert res.status_code == 200
    assert b"Cannot delete ambulance" in res.data

    with app.app_context():
        db = get_db()
        cur = db.execute("SELECT id FROM ambulances WHERE id = 3")
        assert cur.fetchone() is not None  # Must still exist!
