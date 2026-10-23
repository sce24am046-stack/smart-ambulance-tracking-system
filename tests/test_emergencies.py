from app.db import get_db
from app.utils import suggest_priority


def test_suggest_priority_rules():
    """Test rule-based priority engine for emergency categories."""
    p_cardiac = suggest_priority("Cardiac Concern")
    assert p_cardiac["priority"] == "High"

    p_accident = suggest_priority("Accident")
    assert p_accident["priority"] == "High"

    p_med = suggest_priority("Medical Emergency")
    assert p_med["priority"] == "Medium"

    p_other = suggest_priority("Other")
    assert p_other["priority"] == "Low"


def test_public_emergency_registration(app, client):
    """Test citizen public emergency request submission."""
    with client.session_transaction() as sess:
        token = sess.get("_csrf_token", "test-token")
        sess["_csrf_token"] = token

    res = client.post(
        "/emergency/register",
        data={
            "csrf_token": token,
            "patient_name": "Deepak Patel",
            "contact_number": "+91-99887-76655",
            "emergency_category": "Cardiac Concern",
            "pickup_address": "Near MG Road Metro Station, Bengaluru",
            "pickup_latitude": "12.9756",
            "pickup_longitude": "77.6066",
            "notes": "Patient experiencing sudden chest pain and shortness of breath.",
        },
        follow_redirects=True,
    )
    assert res.status_code == 200
    assert b"Emergency Call Logged" in res.data
    assert b"REQ-" in res.data

    with app.app_context():
        db = get_db()
        cur = db.execute("SELECT * FROM emergency_requests WHERE patient_name = 'Deepak Patel'")
        req = cur.fetchone()
        assert req is not None
        assert req["priority"] == "High"
        assert req["status"] == "Pending"


def test_public_track_privacy_redaction(app, client):
    """Verify that public tracking views strictly conceal patient private names and phone numbers."""
    with app.app_context():
        db = get_db()
        cur = db.execute("SELECT request_code, patient_name, contact_number FROM emergency_requests WHERE id = 1")
        req = cur.fetchone()
        code = req["request_code"]
        secret_name = req["patient_name"].encode("utf-8")
        secret_phone = req["contact_number"].encode("utf-8")

    res = client.get(f"/emergency/track/{code}")
    assert res.status_code == 200
    assert code.encode("utf-8") in res.data
    # Private patient details MUST NOT be exposed in the public view
    assert secret_name not in res.data
    assert secret_phone not in res.data


def test_status_lifecycle_and_ambulance_release(app, auth_client):
    """
    Test transition of emergency request:
    When transitioning to Completed or Cancelled, assigned ambulance must be automatically freed to Available.
    """
    with auth_client.session_transaction() as sess:
        token = sess["_csrf_token"]

    # REQ-2026-0001 (id 1) is currently assigned to AMB-103 (id 3, status Busy)
    with app.app_context():
        db = get_db()
        amb = db.execute("SELECT status FROM ambulances WHERE id = 3").fetchone()
        assert amb["status"] == "Busy"

    # Transition to Arrived
    res = auth_client.post(
        "/emergencies/1/status",
        data={"csrf_token": token, "status": "Arrived"},
        follow_redirects=True,
    )
    assert res.status_code == 200

    with app.app_context():
        db = get_db()
        req = db.execute("SELECT status, arrived_at FROM emergency_requests WHERE id = 1").fetchone()
        assert req["status"] == "Arrived"
        assert req["arrived_at"] is not None

    # Transition to Completed
    res = auth_client.post(
        "/emergencies/1/status",
        data={"csrf_token": token, "status": "Completed"},
        follow_redirects=True,
    )
    assert res.status_code == 200

    with app.app_context():
        db = get_db()
        req = db.execute("SELECT status, completed_at FROM emergency_requests WHERE id = 1").fetchone()
        assert req["status"] == "Completed"
        assert req["completed_at"] is not None

        # Ambulance AMB-103 (id 3) MUST now be freed back to 'Available'!
        amb = db.execute("SELECT status FROM ambulances WHERE id = 3").fetchone()
        assert amb["status"] == "Available"
