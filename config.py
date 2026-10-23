import os
from pathlib import Path
from dotenv import load_dotenv

# Base directory of the project
BASE_DIR = Path(__file__).resolve().parent

# Load environment variables from .env if present
load_dotenv(BASE_DIR / ".env")


class Config:
    """Base application configuration."""

    SECRET_KEY = os.getenv("SECRET_KEY", "resq-pulse-college-project-default-key-change-in-prod")
    INSTANCE_DIR = BASE_DIR / "instance"
    INSTANCE_DIR.mkdir(exist_ok=True)

    # SQLite Database Configuration
    DATABASE_NAME = os.getenv("DATABASE_PATH", "resq_pulse.db")
    if os.path.isabs(DATABASE_NAME):
        DATABASE = Path(DATABASE_NAME)
    else:
        DATABASE = INSTANCE_DIR / DATABASE_NAME

    # Session cookie hardening
    SESSION_COOKIE_HTTPONLY = os.getenv("SESSION_COOKIE_HTTPONLY", "True").lower() in ("true", "1", "yes")
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "False").lower() in ("true", "1", "yes")
    SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
    PERMANENT_SESSION_LIFETIME = 3600 * 8  # 8 hours

    # Smart Dispatch & Operation Thresholds
    ASSUMED_CITY_SPEED_KMH = float(os.getenv("ASSUMED_CITY_SPEED_KMH", "40.0"))
    STALE_LOCATION_THRESHOLD_MINUTES = int(os.getenv("STALE_LOCATION_THRESHOLD_MINUTES", "15"))

    # GPS API Key for automated tracker updates
    GPS_TRACKER_API_KEY = os.getenv("GPS_TRACKER_API_KEY", "resq-pulse-demo-gps-key")

    # Routing Provider Configuration
    # Supported: 'osrm' (free road routing), 'mapbox' (traffic-aware if key set), 'tomtom' (traffic-aware if key set), 'offline'
    ROUTING_PROVIDER = os.getenv("ROUTING_PROVIDER", "osrm").lower()
    ROUTING_API_KEY = os.getenv("ROUTING_API_KEY", "")
    ROUTING_CACHE_TTL_SECONDS = int(os.getenv("ROUTING_CACHE_TTL_SECONDS", "300"))
    ROUTING_TIMEOUT_SECONDS = float(os.getenv("ROUTING_TIMEOUT_SECONDS", "3.5"))

    # Live Radar Polling & Telemetry Throttle
    MAP_POLL_INTERVAL_SECONDS = int(os.getenv("MAP_POLL_INTERVAL_SECONDS", "4"))
    LOCATION_UPDATE_MIN_INTERVAL_SECONDS = int(os.getenv("LOCATION_UPDATE_MIN_INTERVAL_SECONDS", "2"))

    # Public Tracking Token Security
    TRACKING_TOKEN_EXPIRY_HOURS = int(os.getenv("TRACKING_TOKEN_EXPIRY_HOURS", "48"))

    # Rate limiting configuration (failed login attempts before temporary lockout)
    MAX_FAILED_LOGIN_ATTEMPTS = 5
    LOGIN_LOCKOUT_SECONDS = 300  # 5 minutes


class DevelopmentConfig(Config):
    DEBUG = True
    TESTING = False


class TestingConfig(Config):
    DEBUG = False
    TESTING = True
    SECRET_KEY = "test-secret-key-not-for-production"
    DATABASE = BASE_DIR / "instance" / "test_resq_pulse.db"
    SESSION_COOKIE_SECURE = False


class ProductionConfig(Config):
    DEBUG = False
    TESTING = False
    SESSION_COOKIE_SECURE = True


config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
