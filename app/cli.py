"""Management commands for EventGate users."""

import argparse
import getpass

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.database import SessionLocal
from app.models import User
from app.security import hash_password


def main():
    parser = argparse.ArgumentParser(description="EventGate management")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create-user", help="Create a user, prompting privately for the password")
    create.add_argument("username")
    reset = commands.add_parser("reset-password", help="Reset a user's password and invalidate their sessions")
    reset.add_argument("username")
    args = parser.parse_args()
    try:
        if not 1 <= len(args.username) <= 150:
            parser.error("Username must contain 1 to 150 characters")
        password = getpass.getpass("Password (at least 12 characters): ")
        if len(password) < 12 or password != getpass.getpass("Confirm password: "):
            parser.error("Passwords must match and contain at least 12 characters")
        with SessionLocal() as db:
            user = db.scalar(select(User).where(User.username == args.username))
            if args.command == "create-user":
                if user:
                    parser.error("Username already exists")
                user = User(username=args.username, password_hash=hash_password(password))
                db.add(user)
            else:
                if not user:
                    parser.error("User not found")
                user.password_hash = hash_password(password)
            db.commit()
        print("User saved.")
    except ValueError as exc:
        parser.error(str(exc))
    except SQLAlchemyError:
        # SQL exceptions can contain passwords/payloads in query parameters.
        parser.error("Database operation failed. Check connectivity and run alembic upgrade head.")


if __name__ == "__main__":
    main()
