"""CLI script to create the first (or any) admin user.

Usage:
    cd /path/to/section23-jobs
    python scripts/create_admin.py <username>

The password is read from the terminal without echo (asked twice). Passing it
as a second argument still works but leaves it in your shell history.

The script creates an admin user in the database. Run it once after a fresh
deployment before anyone can log in to the webapp.
"""

from __future__ import annotations

import asyncio
import getpass
import sys
from pathlib import Path

# Ensure project src is on the path when run directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


async def create_admin(username: str, password: str) -> None:
    from sqlalchemy import select

    from job_aggregator.db.engine import async_session, init_db
    from job_aggregator.db.models import User
    from job_aggregator.webapp.auth import hash_password

    if len(password) < 6:
        print("✗  Password must be at least 6 characters.")
        sys.exit(1)

    await init_db()

    async with async_session() as session:
        existing = await session.execute(select(User).where(User.username == username))
        if existing.scalar_one_or_none():
            print(f"✗  User '{username}' already exists.")
            sys.exit(1)

        user = User(
            username=username,
            hashed_password=hash_password(password),
            is_admin=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

    print(f"✓  Admin user '{username}' created (id: {user.id})")
    print("   You can now log in at http://localhost:8080/login")


def main(argv: list[str]) -> None:
    if len(argv) not in (2, 3):
        print("Usage: python scripts/create_admin.py <username> [password]")
        sys.exit(1)

    username = argv[1]
    if len(argv) == 3:
        print(
            "Warning: a password given on the command line ends up in your shell "
            "history. Omit it to be prompted instead.",
            file=sys.stderr,
        )
        password = argv[2]
    else:
        password = getpass.getpass("Password: ")
        if getpass.getpass("Confirm password: ") != password:
            print("✗  Passwords do not match.")
            sys.exit(1)

    asyncio.run(create_admin(username, password))


if __name__ == "__main__":
    main(sys.argv)
