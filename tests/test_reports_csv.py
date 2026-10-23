from app.db import get_db, init_db
from app.security import sanitize_csv_cell


def test_csv_formula_injection_sanitization():
    """
    Test defense against CSV Injection / Formula Injection (CWE-1236).
    Cells starting with =, +, -, @, tab, or newline must be safely neutralized with a leading apostrophe.
    """
    assert sanitize_csv_cell("=1+1") == "'=1+1"
    assert sanitize_csv_cell("+cmd|' /C calc'!A0") == "'+cmd|' /C calc'!A0"
    assert sanitize_csv_cell("-5+2") == "'-5+2"
    assert sanitize_csv_cell("@SUM(1,2)") == "'@SUM(1,2)"
    assert sanitize_csv_cell("\tDDE") == "'\tDDE"
    assert sanitize_csv_cell("\rDDE") == "'\rDDE"

    # Benign strings and numbers must remain unchanged
    assert sanitize_csv_cell("Rahul Sharma") == "Rahul Sharma"
    assert sanitize_csv_cell("REQ-2026-0001") == "REQ-2026-0001"
    assert sanitize_csv_cell(123) == "123"
    assert sanitize_csv_cell(None) == ""


def test_csv_export_requires_authentication(client):
    """Verify that sensitive operational exports are barred from unauthenticated callers."""
    res = client.get("/reports/export/csv")
    assert res.status_code == 302
    assert "/auth/login" in res.headers["Location"]


def test_authenticated_csv_export(auth_client):
    """Test authorized generation of the emergency incident CSV report."""
    res = auth_client.get("/reports/export/csv")
    assert res.status_code == 200
    assert "text/csv" in res.content_type
    assert b"Request Code,Patient Name,Contact Number" in res.data
    assert b"REQ-2026-" in res.data


def test_database_initialization(app):
    """Verify that init_db initializes the required SQLite tables and indexes."""
    with app.app_context():
        init_db()
        db = get_db()
        cur = db.execute(
            """
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name IN ('administrators', 'ambulances', 'hospitals', 'emergency_requests', 'activity_logs')
            """
        )
        tables = [row["name"] for row in cur.fetchall()]
        assert "administrators" in tables
        assert "ambulances" in tables
        assert "hospitals" in tables
        assert "emergency_requests" in tables
        assert "activity_logs" in tables
