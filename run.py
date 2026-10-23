import os
from app import create_app

# Instantiate the Flask application
app = create_app(os.getenv("FLASK_ENV", "development"))

if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_ENV", "development").lower() == "development"

    print("=" * 60)
    print("  RESQ PULSE — Smart Ambulance Tracking System")
    print("  Tagline: Every Second Matters.")
    print("=" * 60)
    print(f"  * Operations Console: http://{host}:{port}/auth/login")
    print(f"  * Public Landing Page: http://{host}:{port}/")
    print(f"  * Emergency Booking:  http://{host}:{port}/emergency/register")
    print("=" * 60)

    app.run(host=host, port=port, debug=debug)
