import argparse
import getpass
import os
import sys
from app import create_app
from app.db import get_db, init_db, seed_demo_data
from werkzeug.security import generate_password_hash


def main():
    parser = argparse.ArgumentParser(description="ResQ Pulse System Administration CLI")
    subparsers = parser.add_subparsers(dest="command", help="Management commands")

    # init-db
    subparsers.add_parser("init-db", help="Initialize database tables")

    # seed-db
    subparsers.add_parser("seed-db", help="Seed demonstration data")

    # create-admin
    admin_parser = subparsers.add_parser("create-admin", help="Create an administrator account")
    admin_parser.add_argument("--username", help="Admin username")
    admin_parser.add_argument("--name", help="Admin full name")
    admin_parser.add_argument("--password", help="Admin password (leave blank for secure prompt)")

    args = parser.parse_args()
    app = create_app(os.getenv("FLASK_ENV", "development"))

    if args.command == "init-db":
        with app.app_context():
            init_db()
            print("[OK] Database initialized successfully.")

    elif args.command == "seed-db":
        with app.app_context():
            seed_demo_data()
            print("[OK] Demonstration data seeded successfully.")

    elif args.command == "create-admin":
        username = args.username or input("Enter administrator username: ").strip().lower()
        name = args.name or input("Enter full name: ").strip()

        if args.password:
            password = args.password
        else:
            password = getpass.getpass("Enter secure password: ")
            confirm = getpass.getpass("Confirm secure password: ")
            if password != confirm:
                print("Error: Passwords do not match.", file=sys.stderr)
                sys.exit(1)

        if not username or not password or not name:
            print("Error: All fields are required.", file=sys.stderr)
            sys.exit(1)

        with app.app_context():
            db = get_db()
            cur = db.execute("SELECT id FROM administrators WHERE username = ?", (username,))
            if cur.fetchone():
                print(f"Error: Administrator '{username}' already exists.", file=sys.stderr)
                sys.exit(1)

            pw_hash = generate_password_hash(password)
            db.execute(
                """
                INSERT INTO administrators (username, password_hash, full_name, role)
                VALUES (?, ?, ?, 'Administrator')
                """,
                (username, pw_hash, name),
            )
            db.commit()
            print(f"[OK] Administrator '{username}' created successfully.")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
