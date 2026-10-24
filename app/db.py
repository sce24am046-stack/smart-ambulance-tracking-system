import hashlib
import secrets
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from flask import current_app, g
from werkzeug.security import generate_password_hash


def _create_token(expiry_hours=48):
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    expires_at = (datetime.now() + timedelta(hours=expiry_hours)).strftime("%Y-%m-%d %H:%M:%S")
    return raw_token, token_hash, expires_at


def get_db():
    """Retrieve or open the SQLite database connection for the current context."""
    if "db" not in g:
        db_path = current_app.config["DATABASE"]
        # Ensure parent directory exists
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        g.db = sqlite3.connect(db_path, detect_types=sqlite3.PARSE_DECLTYPES)
        g.db.row_factory = sqlite3.Row
        # Enforce foreign key constraints in SQLite
        g.db.execute("PRAGMA foreign_keys = ON;")
        # Ensure schema migrations are applied
        migrate_db(g.db)
    return g.db


def close_db(e=None):
    """Close the SQLite database connection at the end of the request context."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def migrate_db(db=None):
    """Safely apply schema migrations to existing database without data loss."""
    if db is None:
        db = get_db()

    # If the database is completely empty (fresh cloud deployment), auto-initialize schema and demo seed!
    cur = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='administrators'")
    if not cur.fetchone():
        _execute_schema()
        _execute_seed()
        return

    # 1. Ambulances Table Migrations
    amb_cols = [row[1] for row in db.execute("PRAGMA table_info(ambulances)").fetchall()]
    if amb_cols and "last_telemetry_received_at" not in amb_cols:
        db.execute("ALTER TABLE ambulances ADD COLUMN last_telemetry_received_at TIMESTAMP;")

    # 2. Emergency Requests Table Migrations
    req_cols = [row[1] for row in db.execute("PRAGMA table_info(emergency_requests)").fetchall()]
    if req_cols:
        new_cols = {
            "destination_hospital_id": "INTEGER REFERENCES hospitals(id) ON DELETE SET NULL",
            "tracking_token": "TEXT",
            "tracking_token_hash": "TEXT",
            "tracking_token_expires_at": "TIMESTAMP",
            "tracking_token_revoked": "INTEGER NOT NULL DEFAULT 0",
            "route_geojson": "TEXT",
            "route_distance_km": "REAL",
            "route_duration_minutes": "REAL",
            "route_provider": "TEXT",
            "route_traffic_aware": "INTEGER NOT NULL DEFAULT 0",
            "route_last_calculated": "TIMESTAMP",
        }

        for col_name, col_def in new_cols.items():
            if col_name not in req_cols:
                db.execute(f"ALTER TABLE emergency_requests ADD COLUMN {col_name} {col_def};")

        # Create indexes
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_requests_tracking_token ON emergency_requests(tracking_token);")
        db.execute("CREATE INDEX IF NOT EXISTS idx_requests_token_hash ON emergency_requests(tracking_token_hash);")

        # Populate missing tracking tokens for existing requests
        cur = db.execute("SELECT id FROM emergency_requests WHERE tracking_token IS NULL")
        missing_token_rows = cur.fetchall()
        for r in missing_token_rows:
            raw_tok, tok_hash, exp_str = _create_token()
            db.execute(
                "UPDATE emergency_requests SET tracking_token = ?, tracking_token_hash = ?, tracking_token_expires_at = ? WHERE id = ?",
                (raw_tok, tok_hash, exp_str, r["id"]),
            )

        db.commit()


def init_db(app=None):
    """Execute the schema file to initialize database tables and indexes."""
    if app:
        with app.app_context():
            _execute_schema()
    else:
        _execute_schema()


def _execute_schema():
    db = get_db()
    schema_path = Path(current_app.root_path) / "schema.sql"
    with open(schema_path, "r", encoding="utf-8") as f:
        db.executescript(f.read())
    db.commit()


def seed_demo_data(app=None):
    """Seed the database with realistic demonstration records for the Bengaluru area."""
    if app:
        with app.app_context():
            _execute_seed()
    else:
        _execute_seed()


def _execute_seed():
    db = get_db()

    # Check if hospitals already exist to avoid duplicate seeding
    cur = db.cursor()
    cur.execute("SELECT COUNT(*) FROM hospitals")
    if cur.fetchone()[0] > 0:
        return  # Already seeded

    # 1. Seed Demonstration Hospitals (Bengaluru Area)
    hospitals = [
        (
            "Manipal Hospital - Old Airport Road",
            "98, HAL Old Airport Rd, Kodihalli, Bengaluru, Karnataka 560017",
            "+91-80-2502-4444",
            12.9592,
            77.6534,
            "ICU, Trauma, Cardiac, Emergency, Pediatric, Burn Unit",
            1,
        ),
        (
            "Fortis Hospital - Bannerghatta Road",
            "154/9, Bannerghatta Main Rd, Opposite IIM-B, Bengaluru, Karnataka 560076",
            "+91-80-6621-4444",
            12.8931,
            77.5979,
            "ICU, Trauma, Cardiac, Emergency, Neurological Care",
            1,
        ),
        (
            "Apollo Hospital - Sheshadripuram",
            "1, Platform Rd, Sheshadripuram, Bengaluru, Karnataka 560020",
            "+91-80-4668-8888",
            12.9899,
            77.5756,
            "ICU, Cardiac, Emergency, Oncology, Trauma",
            1,
        ),
        (
            "Victoria Hospital - Medical College Campus",
            "Fort Rd, Near City Market, Kalasipalya, Bengaluru, Karnataka 560002",
            "+91-80-2670-1150",
            12.9634,
            77.5751,
            "Trauma, Emergency, Burn Unit, ICU, General Medicine",
            1,
        ),
        (
            "St. John's Medical College Hospital",
            "Sarjapur Main Road, John Nagar, Koramangala, Bengaluru, Karnataka 560034",
            "+91-80-2206-5000",
            12.9345,
            77.6192,
            "ICU, Trauma, Cardiac, Emergency, Pediatric, Stroke Unit",
            1,
        ),
        (
            "Manipal Hospital - Yeshwanthpur",
            "26/4, Brigade Gateway, Beside Metro, Yeshwanthpur, Bengaluru, Karnataka 560055",
            "+91-80-6165-6666",
            13.0183,
            77.5562,
            "ICU, Emergency, Cardiac, Trauma",
            1,
        ),
    ]

    cur.executemany(
        """
        INSERT INTO hospitals (name, address, contact_number, latitude, longitude, services, is_demo_data)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        hospitals,
    )

    # 2. Seed Demonstration Ambulances (Bengaluru Area)
    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")

    ambulances = [
        (
            "AMB-101",
            "Ramesh Kumar",
            "+91-98765-43210",
            "KA-01-EA-1011",
            "Advanced Life Support (ALS)",
            "Available",
            12.9716,
            77.5946,
            now_str,
            "Equipped with cardiac monitor, defibrillator, ventilator, and IV infusion pumps.",
            now_str,
            now_str,
        ),
        (
            "AMB-102",
            "Suresh Naik",
            "+91-98765-43211",
            "KA-01-EA-2022",
            "Basic Life Support (BLS)",
            "Available",
            12.9352,
            77.6245,
            now_str,
            "Equipped with portable oxygen, automated external defibrillator (AED), and patient immobilization kit.",
            now_str,
            now_str,
        ),
        (
            "AMB-103",
            "Priya Sharma",
            "+91-98765-43212",
            "KA-05-EA-3033",
            "Advanced Life Support (ALS)",
            "Busy",
            12.9784,
            77.6408,
            now_str,
            "Currently assigned to Emergency REQ-2026-0001 (Domlur Flyover incident).",
            now_str,
            now_str,
        ),
        (
            "AMB-104",
            "Manjunath Gowda",
            "+91-98765-43213",
            "KA-04-EA-4044",
            "Basic Life Support (BLS)",
            "Available",
            12.9279,
            77.5837,
            now_str,
            "Stationed at Jayanagar 4th Block emergency hub. Ready for dispatch.",
            now_str,
            now_str,
        ),
        (
            "AMB-105",
            "Mohammed Rafi",
            "+91-98765-43214",
            "KA-02-EA-5055",
            "Patient Transport (PTS)",
            "Available",
            13.0298,
            77.5683,
            now_str,
            "Dedicated non-critical transport vehicle with wheelchair ramp and stretcher.",
            now_str,
            now_str,
        ),
        (
            "AMB-106",
            "Anand Verma",
            "+91-98765-43215",
            "KA-03-EA-6066",
            "Advanced Life Support (ALS)",
            "Out of Service",
            12.9830,
            77.7289,
            (now - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S"),
            "Undergoing scheduled 10,000 km hydraulic brake and electrical diagnostic inspection.",
            now_str,
            now_str,
        ),
    ]

    cur.executemany(
        """
        INSERT INTO ambulances (ambulance_code, driver_name, driver_phone, vehicle_number,
                               ambulance_type, status, latitude, longitude, last_location_update,
                               operational_notes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ambulances,
    )

    # 3. Seed Demonstration Emergency Requests
    time_20m_ago = (now - timedelta(minutes=20)).strftime("%Y-%m-%d %H:%M:%S")
    time_15m_ago = (now - timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M:%S")
    time_10m_ago = (now - timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
    time_5m_ago = (now - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
    time_yesterday_1 = (now - timedelta(days=1, hours=3)).strftime("%Y-%m-%d %H:%M:%S")
    time_yesterday_2 = (now - timedelta(days=1, hours=2, minutes=48)).strftime("%Y-%m-%d %H:%M:%S")
    time_yesterday_3 = (now - timedelta(days=1, hours=2, minutes=35)).strftime("%Y-%m-%d %H:%M:%S")

    tok1, tok1_h, exp1 = _create_token(48)
    tok2, tok2_h, exp2 = _create_token(48)
    tok3, tok3_h, exp3 = _create_token(48)
    tok0, tok0_h, exp0 = _create_token(48)

    requests = [
        # Active assigned request linked to AMB-103 (id 3), Destination Hospital: Manipal Hospital (id 1)
        (
            "REQ-2026-0001",
            "Rahul Mehta",
            "+91-98450-11223",
            "Accident",
            "Near Domlur Flyover, Inner Ring Road, Domlur, Bengaluru",
            12.9609,
            77.6387,
            "Two-wheeler collision with minor head injury. Conscious, bleeding controlled with pressure.",
            "High",
            "High",
            "En Route",
            3,
            1,  # destination_hospital_id (Manipal Hospital)
            tok1,
            tok1_h,
            exp1,
            time_15m_ago,
            None,
            None,
            time_20m_ago,
            time_15m_ago,
        ),
        # Pending high priority request, Destination Hospital: Fortis (id 2)
        (
            "REQ-2026-0002",
            "Ananya Sen",
            "+91-98800-44556",
            "Cardiac Concern",
            "27th Main Rd, Sector 1, HSR Layout, Bengaluru",
            12.9121,
            77.6446,
            "Acute chest tightness radiating to left shoulder and diaphoresis in 58yo male.",
            "High",
            "High",
            "Pending",
            None,
            2,
            tok2,
            tok2_h,
            exp2,
            None,
            None,
            None,
            time_10m_ago,
            time_10m_ago,
        ),
        # Pending medium priority request
        (
            "REQ-2026-0003",
            "Kiran Rao",
            "+91-99000-77889",
            "Medical Emergency",
            "8th Cross, Sampige Road, Malleshwaram, Bengaluru",
            13.0031,
            77.5714,
            "Severe respiratory distress and asthmatic wheezing; nebulizer ineffective.",
            "Medium",
            "Medium",
            "Pending",
            None,
            3,  # Apollo Hospital (id 3)
            tok3,
            tok3_h,
            exp3,
            None,
            None,
            None,
            time_5m_ago,
            time_5m_ago,
        ),
        # Completed historical request with realistic response time (13 mins)
        (
            "REQ-2026-0000",
            "Venkatesh Murthy",
            "+91-97400-33221",
            "Medical Emergency",
            "100 Feet Rd, Indiranagar, Bengaluru",
            12.9719,
            77.6412,
            "Elderly patient fall with suspected hip fracture. Successfully transported to Manipal Hospital.",
            "Medium",
            "Medium",
            "Completed",
            1,
            1,
            tok0,
            tok0_h,
            exp0,
            time_yesterday_1,
            time_yesterday_2,
            time_yesterday_3,
            time_yesterday_1,
            time_yesterday_3,
        ),
    ]

    cur.executemany(
        """
        INSERT INTO emergency_requests (
            request_code, patient_name, contact_number, emergency_category,
            pickup_address, pickup_latitude, pickup_longitude, notes,
            priority, suggested_priority, status, assigned_ambulance_id,
            destination_hospital_id, tracking_token, tracking_token_hash, tracking_token_expires_at,
            assigned_at, arrived_at, completed_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        requests,
    )

    # 4. Seed Activity Logs
    activity_entries = [
        (
            "SYSTEM_INIT",
            "system",
            None,
            "System",
            "ResQ Pulse Smart Ambulance Tracking demonstration database initialized.",
            (now - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S"),
        ),
        (
            "AMBULANCE_REGISTERED",
            "ambulance",
            1,
            "System",
            "Ambulance AMB-101 (ALS) registered and marked Available.",
            (now - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S"),
        ),
        (
            "REQUEST_CREATED",
            "emergency_request",
            1,
            "Dispatcher",
            "Emergency REQ-2026-0001 registered for Domlur Flyover accident.",
            time_20m_ago,
        ),
        (
            "AMBULANCE_ASSIGNED",
            "emergency_request",
            1,
            "Dispatcher",
            "Ambulance AMB-103 assigned to REQ-2026-0001 using Smart Dispatch Assist.",
            time_15m_ago,
        ),
        (
            "STATUS_CHANGED",
            "emergency_request",
            1,
            "Dispatcher",
            "Request REQ-2026-0001 updated status from Assigned to En Route.",
            time_10m_ago,
        ),
        (
            "REQUEST_CREATED",
            "emergency_request",
            2,
            "Citizen (Web)",
            "Emergency REQ-2026-0002 submitted via public emergency portal.",
            time_10m_ago,
        ),
    ]

    cur.executemany(
        """
        INSERT INTO activity_logs (event_type, record_type, record_id, actor_username, description, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        activity_entries,
    )

    db.commit()
