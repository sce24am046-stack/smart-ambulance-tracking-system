import functools
import hashlib
import hmac
import secrets
import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Tuple
from flask import (
    abort,
    current_app,
    flash,
    g,
    jsonify,
    redirect,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash


# ---------------------------------------------------------------------------
# Rate Limiting for Login Protection
# ---------------------------------------------------------------------------
_failed_login_attempts = defaultdict(list)


def record_failed_login(identifier: str) -> None:
    """Record a failed login attempt for the given identifier (IP or username)."""
    now = time.time()
    _failed_login_attempts[identifier].append(now)


def is_login_locked(identifier: str) -> bool:
    """Check if the given identifier is temporarily locked out due to excessive failed attempts."""
    max_attempts = current_app.config.get("MAX_FAILED_LOGIN_ATTEMPTS", 5)
    lockout_seconds = current_app.config.get("LOGIN_LOCKOUT_SECONDS", 300)
    now = time.time()

    # Retain only attempts within the lockout window
    valid_attempts = [t for t in _failed_login_attempts[identifier] if now - t < lockout_seconds]
    _failed_login_attempts[identifier] = valid_attempts
    return len(valid_attempts) >= max_attempts


def reset_failed_logins(identifier: str) -> None:
    """Reset failed login attempts upon successful authentication."""
    if identifier in _failed_login_attempts:
        del _failed_login_attempts[identifier]


# ---------------------------------------------------------------------------
# Telemetry Update Frequency / Rate Limiting
# ---------------------------------------------------------------------------
_last_telemetry_times = {}


def check_telemetry_rate_limit(ambulance_id: int, min_interval_seconds: float = 2.0) -> Tuple[bool, float]:
    """
    Enforce location update frequency limits per ambulance.
    Returns (is_allowed, retry_after_seconds).
    """
    now = time.time()
    last_time = _last_telemetry_times.get(ambulance_id, 0.0)
    elapsed = now - last_time

    if elapsed < min_interval_seconds:
        retry_after = round(min_interval_seconds - elapsed, 2)
        return False, retry_after

    _last_telemetry_times[ambulance_id] = now
    return True, 0.0


# ---------------------------------------------------------------------------
# Public Emergency Tracking Token Security
# ---------------------------------------------------------------------------
def generate_tracking_token(expiry_hours: int = 48) -> Tuple[str, str, str]:
    """
    Generate an unguessable high-entropy tracking token for an emergency call.
    Returns (raw_token, token_hash, expires_at_str).
    """
    raw_token = secrets.token_urlsafe(32)  # 43 chars of high entropy
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    expires_at = (datetime.now() + timedelta(hours=expiry_hours)).strftime("%Y-%m-%d %H:%M:%S")
    return raw_token, token_hash, expires_at


def hash_token(token: str) -> str:
    """Hash raw tracking token using SHA-256 for secure DB lookup."""
    if not token:
        return ""
    return hashlib.sha256(token.strip().encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# CSRF Protection Helpers
# ---------------------------------------------------------------------------
def generate_csrf_token() -> str:
    """Generate or retrieve the CSRF token stored in the user's session."""
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_hex(32)
    return session["_csrf_token"]


def csrf_exempt(view_func):
    """Decorator to mark a view as exempt from CSRF validation."""
    view_func._csrf_exempt = True
    return view_func


def validate_csrf():
    """Verify CSRF token for state-changing HTTP methods unless route is exempt."""
    if request.method in ("POST", "PUT", "DELETE", "PATCH"):
        # Check if the view function is marked as CSRF exempt
        if request.endpoint:
            view_func = current_app.view_functions.get(request.endpoint)
            if getattr(view_func, "_csrf_exempt", False):
                return

        # Check for GPS API key authentication if applicable
        api_key_header = request.headers.get("X-API-Key") or request.headers.get("Authorization")
        expected_key = current_app.config.get("GPS_TRACKER_API_KEY")
        if api_key_header and expected_key and (api_key_header == expected_key or api_key_header == f"Bearer {expected_key}"):
            return  # Authenticated by API key header

        # Form token or custom header
        client_token = request.form.get("csrf_token") or request.headers.get("X-CSRFToken")
        session_token = session.get("_csrf_token")

        if not client_token or not session_token or not hmac.compare_digest(client_token, session_token):
            if request.path.startswith("/api/"):
                abort(403, description="CSRF token validation failed or missing.")
            flash("Security check failed (CSRF token missing or expired). Please try again.", "danger")
            abort(400, description="Invalid CSRF token")


# ---------------------------------------------------------------------------
# Authentication & Authorization Decorator
# ---------------------------------------------------------------------------
def login_required(view):
    """Protect views requiring active administrator / dispatcher authentication."""
    @functools.wraps(view)
    def wrapped_view(*args, **kwargs):
        if not session.get("user_id"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "Unauthorized", "message": "Authentication required to access this resource."}), 401
            flash("Authentication required. Please log in to access the emergency operations center.", "warning")
            return redirect(url_for("auth.login", next=request.full_path if request.query_string else request.path))
        return view(*args, **kwargs)
    return wrapped_view


# ---------------------------------------------------------------------------
# Password Management
# ---------------------------------------------------------------------------
def hash_password(password: str) -> str:
    """Generate secure password hash using Werkzeug's modern scrypt/pbkdf2."""
    return generate_password_hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """Verify password against stored hash."""
    return check_password_hash(password_hash, password)


# ---------------------------------------------------------------------------
# Activity Logging
# ---------------------------------------------------------------------------
def log_activity(event_type: str, description: str, record_type: str = None, record_id: int = None, actor: str = None):
    """
    Safely record an event in activity_logs table.
    Enforces that passwords, secrets, or raw sensitive medical details are never recorded.
    """
    from app.db import get_db

    db = get_db()
    if not actor:
        actor = session.get("username", "System")

    # Sanitize description - prevent logging raw sensitive phrases
    safe_desc = description[:500]

    try:
        db.execute(
            """
            INSERT INTO activity_logs (event_type, record_type, record_id, actor_username, description)
            VALUES (?, ?, ?, ?, ?)
            """,
            (event_type, record_type, record_id, actor, safe_desc),
        )
        db.commit()
    except Exception as exc:
        current_app.logger.warning(f"Failed to record activity log: {exc}")


# ---------------------------------------------------------------------------
# Spreadsheet / CSV Formula Injection Sanitization (CWE-1236)
# ---------------------------------------------------------------------------
def sanitize_csv_cell(value) -> str:
    """
    Neutralize CSV / Excel formula injection by prepending a single quote
    if the string value starts with '=', '+', '-', '@', tab, or carriage return.
    """
    if value is None:
        return ""
    str_val = str(value)
    if str_val and str_val[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + str_val
    return str_val
