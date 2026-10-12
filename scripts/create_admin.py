"""CLI script to create the first (or any) admin user.

Usage:
    cd /path/to/section23-jobs
    python scripts/create_admin.py <username> <password>

The script creates an admin user in the database. Run it once after a fresh
deployment before anyone can log in to the webapp.
"""

from __future__ import annotations

import asyncio
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


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python scripts/create_admin.py <username> <password>")
        sys.exit(1)
    asyncio.run(create_admin(sys.argv[1], sys.argv[2]))
