import os
import tempfile
import pytest
from app import create_app
from app.db import get_db, init_db, seed_demo_data
from werkzeug.security import generate_password_hash


@pytest.fixture
def app():
    """Create and configure a new test app instance for each test."""
    db_fd, db_path = tempfile.mkstemp(suffix=".sqlite3")

    test_app = create_app("testing")
    test_app.config.update({
        "DATABASE": db_path,
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "SECRET_KEY": "test-key-32-bytes-long-super-secret",
    })

    with test_app.app_context():
        init_db()
        seed_demo_data()

        # Seed standard test admin user
        db = get_db()
        db.execute(
            """
            INSERT OR REPLACE INTO administrators (username, password_hash, full_name, role)
            VALUES (?, ?, ?, ?)
            """,
            ("testadmin", generate_password_hash("CorrectPassword123!"), "Test Administrator", "Administrator"),
        )
        db.commit()

    yield test_app

    os.close(db_fd)
    if os.path.exists(db_path):
        try:
            os.unlink(db_path)
        except OSError:
            pass


@pytest.fixture
def client(app):
    """A test client for the app."""
    return app.test_client()


@pytest.fixture
def runner(app):
    """A test runner for the app's Click commands."""
    return app.test_cli_runner()


class AuthActions:
    def __init__(self, client):
        self._client = client

    def login(self, username="testadmin", password="CorrectPassword123!"):
        # In test mode, fetch session csrf token first
        with self._client.session_transaction() as sess:
            token = sess.get("_csrf_token", "test-csrf-token")
            sess["_csrf_token"] = token

        return self._client.post(
            "/auth/login",
            data={"username": username, "password": password, "csrf_token": token},
            follow_redirects=True,
        )

    def logout(self):
        return self._client.get("/auth/logout", follow_redirects=True)


@pytest.fixture
def auth(client):
    return AuthActions(client)


@pytest.fixture
def auth_client(client, auth):
    """Test client pre-authenticated with administrator session."""
    auth.login()
    return client
