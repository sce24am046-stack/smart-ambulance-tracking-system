from app.db import get_db
from app.utils import estimate_travel_time, haversine_distance, rank_available_ambulances


def test_haversine_distance_calculation():
    """Verify great-circle spherical distance using Haversine formula."""
    # Cubbon Park to Koramangala (~5.1 - 5.2 km)
    dist = haversine_distance(12.9716, 77.5946, 12.9352, 77.6245)
    assert 5.0 <= dist <= 5.4

    # Distance to identical point is 0
    assert haversine_distance(12.9716, 77.5946, 12.9716, 77.5946) == 0.0


def test_travel_time_estimation():
    """Verify estimated travel time calculation with configurable speed."""
    # 20 km at 40 km/h should be 30.0 minutes
    assert estimate_travel_time(20.0, speed_kmh=40.0) == 30.0

    # 10 km at 60 km/h should be 10.0 minutes
    assert estimate_travel_time(10.0, speed_kmh=60.0) == 10.0


def test_smart_dispatch_ranking(app):
    """Verify that rank_available_ambulances only ranks Available units and orders by distance."""
    with app.app_context():
        # Pickup at MG Road (12.9716, 77.5946)
        candidates = rank_available_ambulances(12.9716, 77.5946)

        assert len(candidates) > 0
        # All candidates must have status == 'Available'
        for c in candidates:
            assert c["status"] == "Available"

        # Candidates must be strictly ordered ascending by distance
        for i in range(len(candidates) - 1):
            assert candidates[i]["distance_km"] <= candidates[i + 1]["distance_km"]

        # First rank must be #1
        assert candidates[0]["rank"] == 1


def test_atomic_ambulance_assignment(app, auth_client):
    """
    Test Smart Dispatch Assist assignment:
    Ambulance is marked Busy, Request is updated to Assigned, transaction committed.
    """
    with auth_client.session_transaction() as sess:
        token = sess["_csrf_token"]

    # REQ-2026-0002 (id 2) is currently Pending
    # AMB-101 (id 1) is Available
    res = auth_client.post(
        "/emergencies/2/assign",
        data={"csrf_token": token, "ambulance_id": 1},
        follow_redirects=True,
    )
    assert res.status_code == 200

    with app.app_context():
        db = get_db()
        req = db.execute("SELECT status, assigned_ambulance_id, assigned_at FROM emergency_requests WHERE id = 2").fetchone()
        assert req["status"] == "Assigned"
        assert req["assigned_ambulance_id"] == 1
        assert req["assigned_at"] is not None

        amb = db.execute("SELECT status FROM ambulances WHERE id = 1").fetchone()
        assert amb["status"] == "Busy"


def test_prevent_conflicting_assignment_to_busy_ambulance(app, auth_client):
    """
    Test concurrency safety:
    Attempting to assign an ambulance that is already Busy must be rejected.
    """
    with auth_client.session_transaction() as sess:
        token = sess["_csrf_token"]

    # In seed data, AMB-103 (id 3) is already Busy
    res = auth_client.post(
        "/emergencies/3/assign",  # REQ-2026-0003
        data={"csrf_token": token, "ambulance_id": 3},
        follow_redirects=True,
    )
    assert res.status_code == 200
    assert b"Dispatch Conflict" in res.data or b"no longer available" in res.data

    with app.app_context():
        db = get_db()
        req = db.execute("SELECT status, assigned_ambulance_id FROM emergency_requests WHERE id = 3").fetchone()
        # Request should still remain Pending
        assert req["status"] == "Pending"
        assert req["assigned_ambulance_id"] is None
