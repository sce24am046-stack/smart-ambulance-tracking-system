import os
from datetime import datetime
import click
from flask import Flask, g, render_template, request, session
from werkzeug.security import generate_password_hash

from app.db import close_db, get_db, init_db, seed_demo_data
from app.security import generate_csrf_token, validate_csrf
from config import config_by_name


def create_app(config_name=None):
    """Application factory for ResQ Pulse Smart Ambulance Tracking System."""
    if config_name is None:
        config_name = os.getenv("FLASK_ENV", "development").lower()

    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_by_name.get(config_name, config_by_name["development"]))

    # Ensure the instance directory exists
    try:
        os.makedirs(app.instance_path, exist_ok=True)
    except OSError:
        pass

    # Database connection teardown
    app.teardown_appcontext(close_db)

    # CSRF Protection Hook
    @app.before_request
    def handle_csrf():
        # Skip CSRF check for static files and safe methods
        if request.path.startswith("/static/"):
            return
        validate_csrf()

    # Template Context Processors
    @app.context_processor
    def inject_global_template_vars():
        return {
            "csrf_token": generate_csrf_token,
            "current_year": datetime.now().year,
            "current_user": {
                "id": session.get("user_id"),
                "username": session.get("username"),
                "full_name": session.get("full_name"),
                "role": session.get("role"),
            } if session.get("user_id") else None,
            "APP_NAME": "RESQ PULSE",
            "APP_SUBTITLE": "Smart Ambulance Tracking System",
            "APP_TAGLINE": "Every Second Matters.",
        }

    # Register Blueprints
    from app.auth.routes import auth_bp
    from app.dashboard.routes import dashboard_bp
    from app.ambulances.routes import ambulances_bp
    from app.emergencies.routes import emergencies_bp
    from app.hospitals.routes import hospitals_bp
    from app.tracking.routes import tracking_bp
    from app.reports.routes import reports_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(ambulances_bp)
    app.register_blueprint(emergencies_bp)
    app.register_blueprint(hospitals_bp)
    app.register_blueprint(tracking_bp)
    app.register_blueprint(reports_bp)

    # Public Landing Page Route
    @app.route("/")
    def landing():
        """Public demonstration landing page."""
        db = get_db()
        cur = db.execute(
            """
            SELECT 
                COUNT(*) as total_amb,
                SUM(CASE WHEN status = 'Available' THEN 1 ELSE 0 END) as avail_amb
            FROM ambulances
            """
        )
        stats = cur.fetchone()
        cur_h = db.execute("SELECT COUNT(*) FROM hospitals")
        hosp_count = cur_h.fetchone()[0]

        return render_template(
            "landing.html",
            total_amb=stats["total_amb"] or 0,
            avail_amb=stats["avail_amb"] or 0,
            hosp_count=hosp_count or 0,
        )

    # Custom Error Handlers
    @app.errorhandler(400)
    def bad_request(error):
        return render_template("errors/400.html", error=error), 400

    @app.errorhandler(403)
    def forbidden(error):
        return render_template("errors/403.html", error=error), 403

    @app.errorhandler(404)
    def not_found(error):
        return render_template("errors/404.html", error=error), 404

    @app.errorhandler(429)
    def rate_limited(error):
        return render_template("errors/429.html", error=error), 429

    @app.errorhandler(500)
    def internal_error(error):
        app.logger.error(f"Internal server error: {error}")
        return render_template("errors/500.html"), 500

    # Register CLI Commands
    _register_cli_commands(app)

    return app


def _register_cli_commands(app: Flask):
    """Register custom management CLI commands with Click."""

    @app.cli.command("init-db")
    def init_db_command():
        """Initialize SQLite database tables and indexes."""
        init_db(app)
        click.echo("[OK] Database schema initialized successfully.")

    @app.cli.command("seed-db")
    def seed_db_command():
        """Populate database with demonstration data for Bengaluru area."""
        seed_demo_data(app)
        click.echo("[OK] Demonstration ambulances, hospitals, and sample calls seeded.")

    @app.cli.command("create-admin")
    @click.option("--username", prompt="Enter administrator username", help="Administrator username")
    @click.option("--name", prompt="Enter full name", help="Administrator full display name")
    @click.password_option(prompt="Enter secure password", confirmation_prompt=True, help="Administrator password")
    def create_admin_command(username, name, password):
        """Securely create a new administrator account with Werkzeug password hashing."""
        username = username.strip().lower()
        name = name.strip()
        if not username or not password or not name:
            click.echo("Error: Username, full name, and password are required.", err=True)
            return

        with app.app_context():
            db = get_db()
            cur = db.execute("SELECT id FROM administrators WHERE username = ?", (username,))
            if cur.fetchone():
                click.echo(f"Error: An administrator with username '{username}' already exists.", err=True)
                return

            pw_hash = generate_password_hash(password)
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            db.execute(
                """
                INSERT INTO administrators (username, password_hash, full_name, role, created_at)
                VALUES (?, ?, ?, 'Administrator', ?)
                """,
                (username, pw_hash, name, now_str),
            )
            db.commit()
            click.echo(f"[OK] Administrator '{username}' created successfully.")
