# RESQ PULSE — Smart Ambulance Tracking System
> **Tagline:** Every Second Matters.  
> **Academic Classification:** College Mini-Project / Final Year Demonstration Project  
> **Technology Stack:** Python Flask 3.0, SQLite3, Leaflet.js, OpenStreetMap, Chart.js, Vanilla JavaScript, CSS3  

---

## 1. Project Abstract

In emergency medical services (EMS), response latency directly correlates with patient survival rates. Traditional ambulance dispatch relies heavily on manual telephonic triage, voice radio coordination, and static fleet deployments without real-time geographical visibility. 

**RESQ PULSE** (Smart Ambulance Tracking System) is a full-stack emergency response operations web application designed to bridge the critical gap between emergency callers, dispatch operators, emergency vehicle fleets, and regional trauma centers. The platform introduces **Smart Dispatch Assist**, an algorithmic recommendation engine employing the spherical **Haversine formula** to compute great-circle distances and estimate transit times across available fleet units. Paired with an interactive **Leaflet.js & OpenStreetMap** command center radar, role-based session authentication, transparent priority triage rules, and safe multi-tier SQLite database transactions, ResQ Pulse provides end-to-end incident management while safeguarding patient privacy.

---

## 2. Problem Statement

Existing emergency response management systems in many municipal and regional setups suffer from:
1. **Lack of Real-Time Geospatial Visibility:** Dispatchers often coordinate via voice calls without an interactive map showing live vehicle locations.
2. **Suboptimal Vehicle Allocation:** Ambulances are dispatched based on arbitrary depot stations rather than proximity to the incident scene.
3. **Double-Booking & Dispatch Collisions:** Without transactional database concurrency controls, two dispatchers can inadvertently assign the same vehicle to concurrent emergencies.
4. **Data Privacy Vulnerabilities:** Public incident tracking endpoints often leak sensitive caller phone numbers, patient names, and medical details.
5. **Vulnerability to Injection Attacks:** Exported incident records frequently lack protection against spreadsheet formula injection (CWE-1236).

---

## 3. Project Objectives

- **Develop a Centralized Operations Dashboard:** Provide real-time KPIs on fleet availability, open incidents, priority queues, and activity timelines.
- **Implement Smart Dispatch Assist:** Compute straight-line distances and estimated travel times using the Haversine formula to rank available ambulances with transparent rationale.
- **Provide Interactive Geospatial Tracking:** Display ambulances, hospitals, and emergency coordinates on an OpenStreetMap Leaflet interface with status-specific markers and telemetry indicators.
- **Implement Robust Authentication & CSRF Defense:** Enforce Werkzeug salted password hashing, rate-limited login defense, and session-tied CSRF token verification.
- **Build a Privacy-Safe Citizen Portal:** Enable public users to lodge emergency requests and monitor progress through anonymized reference codes without exposing private data.
- **Ensure Database Integrity:** Employ normalized SQLite tables with foreign keys (`PRAGMA foreign_keys = ON;`), database transactions, and parameterized SQL queries.

---

## 4. System Scope

### Included in Scope:
- Citizen emergency incident registration with auto-suggested triage priority.
- Protected dispatcher operations dashboard with Chart.js analytics.
- Full CRUD management of fleet vehicles with coordinate validation and safe deletion guards.
- Live Leaflet.js command radar with status-colored beacons and location freshness indicators.
- Real-time road routing navigation via Open Source Routing Machine (OSRM) and configurable traffic provider adapters.
- Dynamic Estimated Arrival Time (ETA in minutes, clock arrival time, and distance remaining) with honest, non-fabricated traffic disclosures.
- Alternative road route evaluation and interactive "Fastest Available Route" switcher.
- Secure token-based citizen tracking portal (`/track/<token>`) strictly concealing caller identities, patient names, and phone numbers.
- Dispatcher controls for public link revocation, token regeneration, and destination hospital selection.
- Rate-limited GPS hardware telemetry ingestion API (`PUT /api/v1/ambulances/<id>/location`) with future timestamp validation.
- Demonstration simulation movement mode advancing vehicles along route polylines.
- Hospital directory with distance calculation and clinical specialty filtering (ICU, Trauma, Cardiac, Burn Unit).
- Secure CSV export with formula injection mitigation.
- Automated testing suite with 44 unit and integration tests (100% pass rate).

### Project Limitations & Demonstration Notice:
> **ACADEMIC DEMONSTRATION NOTICE:**  
> ResQ Pulse is an educational college mini-project. It does not contact actual 108/112/911 emergency services, dispatch real road vehicles, or process real clinical patient records. All vehicle coordinates and hospital directories represent simulated demonstration models for the Bengaluru metropolitan region.

---

## 5. Existing System vs. Proposed System

| Feature / Aspect | Traditional / Existing System | RESQ PULSE (Proposed System) |
| :--- | :--- | :--- |
| **Fleet Tracking** | Telephonic check-ins, manual whiteboards | Real-time Leaflet radar with status beacons |
| **Dispatch Logic** | Manual guess by dispatcher | Algorithmic ranking via Haversine formula |
| **Concurrency Safety** | Verbal confirmation (prone to double-booking) | Atomic SQLite transactions (`BEGIN IMMEDIATE`) |
| **Public Tracking** | None, or exposes private caller data | Privacy-redacted public reference portal |
| **Hospital Routing** | Driver discretion | Nearest specialized facility proximity lookup |
| **Report Exporting** | Raw text / unescaped CSV | CWE-1236 Formula-sanitized CSV exports |

---

## 6. Functional & Non-Functional Requirements

### Functional Requirements:
1. **Public Emergency Booking:** Citizens can register emergency calls with auto-detected GPS coordinates and symptom categories.
2. **Triage Suggestion:** Transparent rule-based priority assignment (Cardiac/Accident -> High; Medical -> Medium; Other -> Low).
3. **Smart Dispatch Assist:** Identifies all `Available` units, calculates distance using Haversine, estimates ETA at assumed speed, and presents ranked choices.
4. **Incident Lifecycle:** State transitions (`Pending` -> `Assigned` -> `En Route` -> `Arrived` -> `Completed` / `Cancelled`). Resolving an incident automatically frees the ambulance back to `Available`.
5. **Fleet Telemetry API:** Authorized endpoint (`PUT /api/v1/ambulances/<id>/location`) supporting GPS hardware updates with API key authentication.
6. **Hospital Proximity Search:** Distance computation and clinical capability filtering.
7. **CSV Exporting:** Filtered emergency request downloads with formula-injection neutralization.

### Non-Functional Requirements:
- **Security:** Werkzeug password hashing (scrypt/pbkdf2), session cookie hardening (`HttpOnly`, `SameSite=Lax`), CSRF protection on all mutating requests.
- **Reliability:** Graceful handling of missing records, duplicate vehicle codes, invalid GPS inputs, and offline map tiles.
- **Maintainability:** Modular Flask Blueprints, separation of concerns, parameterized SQL queries.
- **Usability:** High-contrast emergency command-center UI, responsive desktop sidebar / mobile drawer, dark/light theme toggle.

---

## 7. Technology Stack

### Frontend:
- **HTML5 & CSS3:** Semantic markup with custom CSS variables, glassmorphic dark navy aesthetic, and responsive flex/grid layouts.
- **Vanilla JavaScript (ES6+):** Sidebar controls, theme toggling, live timers, confirmation modals, and toast notifications (zero bloated frameworks).
- **Leaflet.js (v1.9.4):** Lightweight, open-source mobile-friendly interactive maps.
- **OpenStreetMap:** Community-driven global map tile provider.
- **Chart.js (v4.4.1):** Clean responsive canvas charts for 7-day incident trends and status distributions.
- **Jinja2:** Server-rendered templates with contextual processors.

### Backend:
- **Python (v3.11+):** Core language.
- **Flask (v3.0.3):** Lightweight WSGI web framework.
- **Werkzeug (v3.0.3):** Comprehensive WSGI utility library and secure password hashing.
- **Python-dotenv (v1.0.1):** 12-factor application configuration loading.
- **Built-in CSV & Math Modules:** Standard library tools for calculations and sanitized data exports.

### Database:
- **SQLite3:** Embedded relational database with foreign key enforcement (`PRAGMA foreign_keys = ON;`) and multi-column indexes.

### Automated Testing:
- **Pytest (v8.2.2):** Automated unit and integration testing suite.

---

## 8. System Architecture

```
                                  [ Browser / Client ]
                                           |
                    +----------------------+----------------------+
                    |                                             |
             (Public User)                                (Dispatcher / Admin)
          Public Landing Page                          Operations Dashboard
        Emergency Registration                        Live Tracking Radar Map
          Privacy Status View                         Ambulance Management
                    |                                  Reports & CSV Export
                    |                                             |
                    +----------------------+----------------------+
                                           |
                                   [ HTTP / HTTPS ]
                                           |
                              +-------------------------+
                              |   Flask Application     |
                              |   (create_app Factory)  |
                              +-------------------------+
                                 |         |         |
          +----------------------+         |         +----------------------+
          |                                |                                |
   [ Blueprints ]                  [ Security Layer ]               [ Core Engines ]
   - auth_bp                       - CSRF Validation                - Haversine Distance
   - dashboard_bp                  - Session Auth Guard             - ETA Calculator
   - ambulances_bp                 - Rate Limiter                   - Priority Rule Triage
   - emergencies_bp                - Password Hasher                - Sanitized CSV Builder
   - hospitals_bp                  - Activity Logger
   - tracking_bp
   - reports_bp
          |                                |                                |
          +--------------------------------+--------------------------------+
                                           |
                           [ SQLite Database (resq_pulse.db) ]
                           - administrators
                           - ambulances (PRAGMA foreign_keys = ON)
                           - emergency_requests
                           - hospitals
                           - activity_logs
```

---

## 9. Database Schema

The normalized SQLite database schema contains five core tables with indexes:

```sql
PRAGMA foreign_keys = ON;

-- 1. Administrators
CREATE TABLE administrators (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'Administrator',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP
);

-- 2. Ambulances
CREATE TABLE ambulances (
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

-- 3. Hospitals Directory
CREATE TABLE hospitals (
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

-- 4. Emergency Requests
CREATE TABLE emergency_requests (
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
    route_distance_km REAL DEFAULT 0.0,
    route_duration_minutes REAL DEFAULT 0.0,
    route_provider TEXT DEFAULT 'OSRM',
    route_traffic_aware INTEGER DEFAULT 0,
    route_last_calculated TIMESTAMP,
    assigned_at TIMESTAMP,
    arrived_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (assigned_ambulance_id) REFERENCES ambulances(id) ON DELETE SET NULL,
    FOREIGN KEY (destination_hospital_id) REFERENCES hospitals(id) ON DELETE SET NULL
);

-- 5. Activity Logs
CREATE TABLE activity_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    record_type TEXT,
    record_id INTEGER,
    actor_username TEXT NOT NULL DEFAULT 'System',
    description TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

---

## 10. Simulated Tracking vs. Real GPS Tracking

A common question in engineering vivas is: *How does this demonstration tracking compare to real-world vehicle tracking?*

| Characteristic | ResQ Pulse Simulation Mode | Real-World GPS Fleet Integration |
| :--- | :--- | :--- |
| **Hardware Requirement** | None (runs in browser/server memory) | On-board OBD-II GPS Tracker or Mobile Terminal |
| **Data Transmission** | Client-triggered HTTP polling / step vectors | GSM / 4G LTE cellular data or satellite telemetry |
| **Ingestion Protocol** | `POST /api/v1/tracking/simulate-step` | `PUT /api/v1/ambulances/<id>/location` with API key |
| **Accuracy** | Calculated coordinate drift | Real satellite trilateration (3-5 meter accuracy) |
| **Road Geometry** | Straight-line vector stepping | Road network routing (OSRM, Google Maps API) |
| **Status in ResQ Pulse** | Available as a demonstration feature | Fully architected API endpoint ready for hardware |

---

## 11. Installation & Execution Guide (Windows)

### Step 1: Open Terminal in Project Folder
Navigate to the project root directory in PowerShell:
```powershell
cd "c:\Users\ADMIN\OneDrive\Desktop\new ambulance"
```

### Step 2: Virtual Environment Setup
If not already created, create and activate a Python virtual environment:
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### Step 3: Install Dependencies
```powershell
pip install -r requirements.txt
```

### Step 4: Configure Environment Variables
Copy `.env.example` to `.env`:
```powershell
Copy-Item .env.example .env
```

### Step 5: Initialize and Seed Database
Run the CLI commands to initialize tables and seed realistic Bengaluru demonstration records:
```powershell
python cli.py init-db
python cli.py seed-db
```

### Step 6: Create Administrator Account
Create the administrator credentials securely:
```powershell
python cli.py create-admin --username admin --name "System Administrator" --password "Admin@12345"
```
*(You may also omit `--password` to be prompted interactively with masked input).*

### Step 7: Start the Application Server
```powershell
python run.py
```
The server will bind to `http://127.0.0.1:5000`.

### Step 8: Access the Application
- **Public Landing Page:** `http://127.0.0.1:5000/`
- **Dispatcher Operations Login:** `http://127.0.0.1:5000/auth/login`
  - **Username:** `admin`
  - **Password:** `Admin@12345`
- **Public Emergency Request Form:** `http://127.0.0.1:5000/emergency/register`
- **Hospital Directory:** `http://127.0.0.1:5000/hospitals`

---

## 12. Running Automated Tests

ResQ Pulse comes with 44 comprehensive automated tests using `pytest` and an isolated temporary SQLite database:

```powershell
.\venv\Scripts\python.exe -m pytest -v
```

### Test Suite Coverage:
- `tests/test_ambulances.py`: Fleet list, vehicle addition, unique ambulance code constraints, coordinate boundary checks, and safe deletion prevention on active calls.
- `tests/test_auth.py`: Salted password hashing, login success, generic error handling on wrong password and non-existent username, session termination on logout, and rate-limiting lockout.
- `tests/test_dispatch_engine.py`: Haversine formula distance calculation, travel time estimation, candidate ranking, atomic database transaction assignment, and double-booking conflict prevention.
- `tests/test_emergencies.py`: Public incident intake, automatic priority suggestion, public tracking privacy redaction, and automatic ambulance release on call completion.
- `tests/test_hospitals.py`: Directory view, clinical service filtering, and distance sorting.
- `tests/test_reports_csv.py`: CWE-1236 spreadsheet formula injection neutralization, export authorization, and database table initialization.
- `tests/test_security.py`: Public landing page, protected route authorization checks, CSRF rejection on raw POST requests, and API key authentication on the GPS location ingestion endpoint.
- `tests/test_routing_and_tracking.py`: Telemetry update rate limiting (throttling to 2s intervals with 429 status), future timestamp rejection (422), coordinate boundary validation (422), unguessable token generation and verification, patient PII concealment, token revocation (403), token expiration (410), OSRM and offline fallback routing providers, dynamic ETA metadata categorization, and dispatcher route recalculation endpoints.

---

## 13. Sample Demonstration Workflow

Follow this step-by-step workflow for a live college project demonstration:

1. **Visit Landing Page:** Open `http://127.0.0.1:5000/` to inspect the product branding, live radar preview, workflow description, and demonstration disclaimer.
2. **Citizen Registers Emergency:** Click **"Request Emergency Ambulance"** or navigate to `http://127.0.0.1:5000/emergency/register`.
   - Enter Patient Name: *Aarav Sharma*
   - Phone: `+91-98765-43210`
   - Category: `Cardiac Concern`
   - Pickup Address: *MG Road Metro Station, Bengaluru*
   - Click **"Auto-Detect GPS Location"** or use default coordinates `[12.9716, 77.5946]`.
   - Submit call and note the unique tracking code (e.g., `REQ-2026-XXXX`).
3. **Inspect Citizen Privacy Tracking:** Click **"Track Ambulance Status Live"**. Notice that patient name and phone number are concealed.
4. **Dispatcher Login:** Open `http://127.0.0.1:5000/auth/login` and log in with `admin` / `Admin@12345`.
5. **Review Dashboard:** Observe the live KPI cards, fleet availability percentage, 7-day trend chart, and priority queue showing Aarav Sharma's High priority call at the top.
6. **Smart Dispatch Assist:** Click **"Dispatch Assist"** next to the incident.
   - Observe candidate ambulances ranked by Haversine distance and travel time.
   - Click **"Assign Unit"** to execute the atomic transaction.
   - Notice the chosen ambulance status transitions to `Busy`.
7. **Inspect Live Tracking Map:** Navigate to **"Live Tracking Map"**.
   - Watch vehicle markers color-coded by status.
   - Click **"Simulate Fleet Movement"** to observe simulated GPS ticks moving the assigned ambulance toward the incident.
8. **Handover & Completion:** Open the emergency details, transition status to `Arrived`, then `Completed`.
   - Notice that the ambulance is automatically freed back to `Available` on the radar and dashboard!
9. **Export Audit Report:** Go to **"Analytics & Reports"** and click **"Export Sanitized CSV Report"** to download the sanitized mission history.

---

## 14. Screenshots Section & Capture Guide

To document actual application screenshots for your college project report or presentation:

1. **Public Landing Page:** Navigate to `http://127.0.0.1:5000/` in full-screen mode (Press `F11`), take a screenshot (`Win + Shift + S`), and save as `docs/screenshots/01_landing_page.png`.
2. **Dispatcher Authentication:** Navigate to `http://127.0.0.1:5000/auth/login`, capture the command-center login screen, and save as `docs/screenshots/02_login_screen.png`.
3. **Mission Control Dashboard:** Log in and capture the 8 KPI cards, Chart.js trend, and priority queue. Save as `docs/screenshots/03_operations_dashboard.png`.
4. **Live Leaflet Tracking Map:** Navigate to `/tracking`, center the Bengaluru fleet, capture the status-colored markers and telemetry side-panel. Save as `docs/screenshots/04_live_tracking_map.png`.
5. **Smart Dispatch Assist:** Open any pending incident, capture the Haversine distance ranking candidates table, and save as `docs/screenshots/05_smart_dispatch_assist.png`.
6. **Hospital Directory:** Navigate to `/hospitals`, capture the clinical service filters, and save as `docs/screenshots/06_hospital_directory.png`.
7. **Fleet Health Console:** Navigate to `/reports/fleet-health`, capture the telemetry freshness indicators, and save as `docs/screenshots/07_fleet_health.png`.

---

## 15. Comprehensive College Viva Questions & Answers

### Q1: What is Flask, and why was it chosen for this project?
**Answer:** Flask is a lightweight Python WSGI web framework based on Werkzeug and Jinja2. It was chosen because of its modular architecture, simplicity, low overhead, and ability to easily implement custom security features (such as CSRF protection and session rate-limiting) without unnecessary enterprise bloat.

### Q2: What is SQLite, and how does it maintain ACID properties?
**Answer:** SQLite is a serverless, self-contained, transactional SQL database engine. It stores the entire database in a single cross-platform disk file. It maintains ACID properties (Atomicity, Consistency, Isolation, Durability) through write-ahead logging (WAL) and database locking mechanisms. In this project, foreign keys are strictly enforced using `PRAGMA foreign_keys = ON;`.

### Q3: What is the Haversine formula, and why is it necessary?
**Answer:** The Haversine formula calculates the great-circle distance between two points on the surface of a sphere given their latitudes and longitudes:
$$d = 2R \arcsin\left(\sqrt{\sin^2\left(\frac{\Delta\phi}{2}\right) + \cos(\phi_1)\cos(\phi_2)\sin^2\left(\frac{\Delta\lambda}{2}\right)}\right)$$
where $R$ is Earth's mean radius ($6371.0\text{ km}$). It is necessary because treating Earth as a flat Cartesian plane ($x, y$) results in significant distortion over geographical distances due to the planet's spherical curvature.

### Q4: What is the difference between straight-line distance and road distance?
**Answer:** Straight-line (Euclidean / Haversine) distance measures the direct line-of-sight across the Earth's surface ("as the crow flies"). Road distance accounts for the actual road network, one-way streets, flyovers, terrain barriers, and traffic signals. In our project, straight-line distance is used for rapid candidate triage and is accompanied by an explicit disclaimer that actual routing requires navigation APIs.

### Q5: How are passwords secured in this application?
**Answer:** Passwords are never stored in plaintext. They are hashed using Werkzeug's `generate_password_hash()`, which implements modern one-way salted hashing algorithms (such as scrypt or PBKDF2 with HMAC-SHA256). When authenticating, `check_password_hash()` compares the hash in constant time to prevent timing attacks.

### Q6: How does CSRF protection work?
**Answer:** Cross-Site Request Forgery (CSRF) is an attack where an unauthorized website tricks a user's browser into performing unwanted actions on a trusted site where the user is authenticated. We protect against this by generating a cryptographically secure random token (`secrets.token_hex(32)`) stored in the server session. Every state-changing HTTP request (`POST`, `PUT`, `DELETE`) must submit this token in form data or headers; requests with missing or mismatched tokens are rejected with HTTP 400.

### Q7: What is SQL Injection, and how does ResQ Pulse prevent it?
**Answer:** SQL Injection occurs when malicious user input is concatenated directly into SQL query strings, allowing an attacker to manipulate query logic. ResQ Pulse completely prevents SQL injection by using **parameterized queries** with placeholder markers (`?`) across all SQLite database executions (e.g., `db.execute("SELECT * FROM ambulances WHERE status = ?", (status,))`), ensuring user input is treated strictly as data, never as executable SQL.

### Q8: What is Spreadsheet / CSV Formula Injection (CWE-1236)?
**Answer:** CSV Injection occurs when untrusted user input exported into a spreadsheet file starts with formula trigger characters (`=`, `+`, `-`, `@`, `\t`, `\r`). When opened in spreadsheet software like Microsoft Excel or LibreOffice Calc, the cell is interpreted as an executable formula. ResQ Pulse neutralizes this by passing every cell through `sanitize_csv_cell()`, prepending a single quote (`'`) to force the spreadsheet to treat the content as literal text.

### Q9: What is the difference between session-based authentication and token-based (JWT) authentication?
**Answer:** In session-based authentication, the server generates a cryptographically signed session cookie stored in the client browser, while session data remains on the server. In JWT (token-based) authentication, the user claims and signature are stored directly inside a stateless token transmitted in HTTP headers. ResQ Pulse uses session-based authentication with `HttpOnly` and `SameSite=Lax` cookies to prevent Cross-Site Scripting (XSS) token theft.

### Q10: How does the Smart Dispatch Assist prevent double-booking of ambulances?
**Answer:** When a dispatcher assigns an ambulance, the operation runs inside an immediate SQLite database transaction (`BEGIN IMMEDIATE TRANSACTION;`). The engine verifies that the vehicle's status is still `Available`. If another dispatcher concurrently assigned the vehicle moments earlier, the transaction detects the conflict, rolls back, and returns a graceful conflict error without corrupting records.

### Q11: How is patient privacy maintained on public endpoints?
**Answer:** When citizens lodge an emergency request, they receive a unique public tracking reference code (e.g., `REQ-2026-0001`). The public tracking route (`/emergency/track/<request_code>`) performs a projection query that extracts only non-identifying operational fields (`request_code`, `status`, `category`, general area, and assigned vehicle). Caller names, phone numbers, and private medical notes are strictly omitted from the response.

### Q12: What are Leaflet.js and OpenStreetMap?
**Answer:** Leaflet.js is an open-source JavaScript library used to build interactive mobile-friendly web mapping applications. OpenStreetMap (OSM) is a collaborative, open-data project providing geographic tile maps. Leaflet manages map rendering, vector marker layers, popups, and zooming, while fetching map imagery tiles from OpenStreetMap servers.

### Q13: What is the purpose of rate-limiting on the login route?
**Answer:** Rate limiting prevents automated brute-force attacks and credential stuffing. ResQ Pulse tracks failed authentication attempts by client IP and username. If 5 consecutive failed attempts occur within 5 minutes, the account/IP is locked out for 5 minutes, returning HTTP 429.

### Q14: How does the application detect stale GPS telemetry?
**Answer:** Every ambulance record stores a `last_location_update` timestamp. In `app/utils.py`, `is_location_stale()` compares this timestamp against the current server time using a configurable threshold (default: 15 minutes). If the delta exceeds 15 minutes, the vehicle is flagged with a `Stale Telemetry` badge to alert dispatchers that coordinates may be outdated.

### Q15: How does the Fastest-Route navigation engine work?
**Answer:** The system uses an Adapter Design Pattern (`app/routing.py`) that abstracts the routing provider. By default, it queries the Open Source Routing Machine (OSRM) driving API to compute road network polylines and duration estimates. It requests alternative routes (`alternatives=true`), compares durations, caches results by coordinate grid to prevent rate-limit exhaustion, and returns both primary and secondary options for dispatcher evaluation.

### Q16: How does the application avoid fabricating traffic conditions?
**Answer:** In accordance with emergency operations engineering standards, ResQ Pulse never invents green/red congestion indicators or fabricates "zero traffic" claims. When using OSRM or offline providers without live traffic sensor feeds, it transparently tags the ETA as `Road Network Routing (OSRM)` and displays: *"Live traffic data unavailable. Travel times reflect speed on road network."* Traffic-aware ETAs are only activated when an authentic traffic-enabled provider (such as Mapbox Directions with traffic profile) is configured with a valid API key.

### Q17: How is citizen privacy enforced on the public live tracking link?
**Answer:** Citizens access the tracking page using a 43-character, cryptographically unguessable token (`secrets.token_urlsafe(32)`) stored as a SHA-256 hash in the database, preventing enumeration attacks that affect sequential database IDs. The public views (`/track/<token>` and `/api/v1/track/<token>/live`) strictly redact the caller's name, phone number, and driver phone numbers, rendering only vehicle position, incident priority, ETA, and route geometry. Furthermore, dispatchers have one-click controls to revoke access or regenerate tokens on demand.

### Q18: How does the telemetry API prevent denial-of-service and clock skew?
**Answer:** The `PUT /api/v1/ambulances/<id>/location` endpoint enforces a sliding-window rate limit (minimum 2 seconds between updates per vehicle), returning HTTP 429 if vehicles broadcast too frequently. It also validates coordinates within earthly boundaries (-90 to 90, -180 to 180) and checks timestamp skew, rejecting any coordinate stamped more than 60 seconds into the future with HTTP 422.

---

## 16. Git Instructions (When Ready to Commit)

*Note: Per project instructions, code has NOT been pushed to GitHub.*

When you are ready to push to your GitHub repository in the future:
```powershell
git init
git add .
git commit -m "Initial release of ResQ Pulse - Smart Ambulance Tracking System"
git branch -M main
git remote add origin https://github.com/<your-username>/<your-repo-name>.git
git push -u origin main
```
