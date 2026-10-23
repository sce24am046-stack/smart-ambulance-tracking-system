from app.utils import rank_nearest_hospitals


def test_hospitals_directory_view(client):
    """Test public access to hospital directory."""
    res = client.get("/hospitals")
    assert res.status_code == 200
    assert b"Hospital Directory" in res.data
    assert b"Manipal Hospital" in res.data


def test_hospital_clinical_service_filter(app):
    """Test filtering hospitals by specialized clinical capability."""
    with app.app_context():
        # Filter for Burn Unit
        burn_hospitals = rank_nearest_hospitals(12.9716, 77.5946, service_keyword="Burn Unit")
        assert len(burn_hospitals) > 0
        for h in burn_hospitals:
            assert "Burn Unit" in h["services"]


def test_nearest_hospitals_distance_sorting(app):
    """Test that hospitals are strictly ordered ascending by Haversine distance."""
    with app.app_context():
        hospitals = rank_nearest_hospitals(12.9716, 77.5946)
        assert len(hospitals) >= 2
        for i in range(len(hospitals) - 1):
            assert hospitals[i]["distance_km"] <= hospitals[i + 1]["distance_km"]
