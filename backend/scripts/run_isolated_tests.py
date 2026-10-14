"""Run backend tests against a dedicated PostgreSQL database, never the app DB."""

from __future__ import annotations

import os
import subprocess
import sys

import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url

from app.core.config import settings

TEST_DATABASE = "kira_voice_test"


def main() -> int:
    app_url = make_url(str(settings.DATABASE_URL))
    if app_url.database == TEST_DATABASE:
        raise RuntimeError("Application and test database must be distinct")
    test_url = app_url.set(database=TEST_DATABASE)
    postgres_url = app_url.set(drivername="postgresql", database="postgres")
    try:
        with psycopg.connect(
            postgres_url.render_as_string(hide_password=False), autocommit=True
        ) as connection:
            exists = connection.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DATABASE,)
            ).fetchone()
            if not exists:
                connection.execute(
                    sql.SQL("CREATE DATABASE {}").format(sql.Identifier(TEST_DATABASE))
                )
    except psycopg.Error as exc:
        raise RuntimeError(
            f"Could not prepare isolated test database ({type(exc).__name__})"
        ) from None

    environment = os.environ.copy()
    environment["DATABASE_URL"] = test_url.render_as_string(hide_password=False)
    sys.stdout.write(f"Isolated pytest database: {TEST_DATABASE}\n")
    migrated = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        env=environment,
        check=False,
    )
    if migrated.returncode:
        return migrated.returncode
    tested = subprocess.run(
        [sys.executable, "-m", "pytest", *sys.argv[1:]],
        env=environment,
        check=False,
    )
    return tested.returncode


if __name__ == "__main__":
    raise SystemExit(main())
