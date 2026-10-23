-- ResQ Pulse: Smart Ambulance Tracking System
-- Database Schema for SQLite

PRAGMA foreign_keys = ON;

-- 1. Administrators Table
CREATE TABLE IF NOT EXISTS administrators (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'Administrator',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP
);

-- 2. Ambulances Table
CREATE TABLE IF NOT EXISTS ambulances (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ambulance_code TEXT UNIQUE NOT NULL COLLATE NOCASE,
    driver_name TEXT NOT NULL,
    driver_phone TEXT NOT NULL,
    vehicle_number TEXT NOT NULL COLLATE NOCASE,
    ambulance_type TEXT NOT NULL CHECK(ambulance_type IN ('Basic Life Support (BLS)', 'Advanced Life Support (ALS)', 'Patient Transport (PTS)')),
    status TEXT NOT NULL CHECK(status IN ('Available', 'Busy', 'Out of Service')) DEFAULT 'Available',
    latitude REAL NOT NULL CHECK(latitude >= -90.0 AND latitude <= 90.0),
    longitude REAL NOT NULL CHECK(longitude >= -180.0 AND longitude <= 180.0),
    last_location_update TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_telemetry_received_at TIMESTAMP,
    operational_notes TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 3. Hospitals Directory Table
CREATE TABLE IF NOT EXISTS hospitals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    address TEXT NOT NULL,
    contact_number TEXT NOT NULL,
    latitude REAL NOT NULL CHECK(latitude >= -90.0 AND latitude <= 90.0),
    longitude REAL NOT NULL CHECK(longitude >= -180.0 AND longitude <= 180.0),
    services TEXT NOT NULL,
    is_demo_data INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 4. Emergency Requests Table
CREATE TABLE IF NOT EXISTS emergency_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_code TEXT UNIQUE NOT NULL COLLATE NOCASE,
    patient_name TEXT NOT NULL,
    contact_number TEXT NOT NULL,
    emergency_category TEXT NOT NULL CHECK(emergency_category IN ('Accident', 'Medical Emergency', 'Cardiac Concern', 'Other')),
    pickup_address TEXT NOT NULL,
    pickup_latitude REAL NOT NULL CHECK(pickup_latitude >= -90.0 AND pickup_latitude <= 90.0),
    pickup_longitude REAL NOT NULL CHECK(pickup_longitude >= -180.0 AND pickup_longitude <= 180.0),
    notes TEXT,
    priority TEXT NOT NULL CHECK(priority IN ('High', 'Medium', 'Low')) DEFAULT 'Medium',
    suggested_priority TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('Pending', 'Assigned', 'En Route', 'Arrived', 'Completed', 'Cancelled')) DEFAULT 'Pending',
    assigned_ambulance_id INTEGER,
    destination_hospital_id INTEGER,
    tracking_token TEXT UNIQUE,
    tracking_token_hash TEXT,
    tracking_token_expires_at TIMESTAMP,
    tracking_token_revoked INTEGER NOT NULL DEFAULT 0,
    route_geojson TEXT,
    route_distance_km REAL,
    route_duration_minutes REAL,
    route_provider TEXT,
    route_traffic_aware INTEGER NOT NULL DEFAULT 0,
    route_last_calculated TIMESTAMP,
    assigned_at TIMESTAMP,
    arrived_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (assigned_ambulance_id) REFERENCES ambulances(id) ON DELETE SET NULL,
    FOREIGN KEY (destination_hospital_id) REFERENCES hospitals(id) ON DELETE SET NULL
);

-- 5. Activity Logs Table
CREATE TABLE IF NOT EXISTS activity_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    record_type TEXT,
    record_id INTEGER,
    actor_username TEXT NOT NULL DEFAULT 'System',
    description TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Database Performance Indexes
CREATE INDEX IF NOT EXISTS idx_ambulances_code ON ambulances(ambulance_code);
CREATE INDEX IF NOT EXISTS idx_ambulances_status ON ambulances(status);
CREATE INDEX IF NOT EXISTS idx_requests_code ON emergency_requests(request_code);
CREATE INDEX IF NOT EXISTS idx_requests_status ON emergency_requests(status);
CREATE INDEX IF NOT EXISTS idx_requests_priority ON emergency_requests(priority);
CREATE INDEX IF NOT EXISTS idx_requests_created ON emergency_requests(created_at);
CREATE INDEX IF NOT EXISTS idx_requests_assigned_ambulance ON emergency_requests(assigned_ambulance_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_requests_tracking_token ON emergency_requests(tracking_token);
CREATE INDEX IF NOT EXISTS idx_requests_token_hash ON emergency_requests(tracking_token_hash);
CREATE INDEX IF NOT EXISTS idx_activity_created ON activity_logs(created_at);
