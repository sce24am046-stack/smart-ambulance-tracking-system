from app.security import (
    hash_password,
    is_login_locked,
    record_failed_login,
    reset_failed_logins,
    verify_password,
)


def test_password_hashing():
    """Verify password hashing produces salted, verifiable hashes."""
    raw_pass = "SecureEmergencyPass2026!"
    hashed = hash_password(raw_pass)

    assert hashed != raw_pass
    assert verify_password(hashed, raw_pass) is True
    assert verify_password(hashed, "WrongPassword") is False


def test_login_success(auth, client):
    """Test successful administrator login."""
    res = auth.login("testadmin", "CorrectPassword123!")
    assert res.status_code == 200
    assert b"Operations Dashboard" in res.data or b"Mission Control" in res.data


def test_login_failure_wrong_password(auth):
    """Test failure with wrong password returns generic error."""
    res = auth.login("testadmin", "WrongPassword!")
    assert res.status_code == 200
    assert b"Invalid username or password" in res.data


def test_login_failure_unknown_user(auth):
    """Test failure with unknown user returns identical generic error without account enumeration."""
    res = auth.login("nonexistent_user", "SomePassword!")
    assert res.status_code == 200
    assert b"Invalid username or password" in res.data


def test_logout(auth, client):
    """Test logout removes session and restricts protected routes."""
    auth.login()
    res = auth.logout()
    assert res.status_code == 200

    # Protected dashboard should now redirect to login
    dash_res = client.get("/dashboard")
    assert dash_res.status_code == 302
    assert "/auth/login" in dash_res.headers["Location"]


def test_login_rate_limiting(app):
    """Test rate limiting locks after 5 consecutive failures."""
    with app.app_context():
        ident = "test_rate_ip"
        reset_failed_logins(ident)

        for _ in range(4):
            record_failed_login(ident)
            assert is_login_locked(ident) is False

        record_failed_login(ident)
        assert is_login_locked(ident) is True

        reset_failed_logins(ident)
        assert is_login_locked(ident) is False
