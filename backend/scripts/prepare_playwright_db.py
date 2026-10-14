"""Reset the dedicated Playwright database and emit its URL for the runner.

Run only from ``scripts/run_isolated_playwright.ps1``, which captures stdout
without printing the URL. Never log the returned URL or provider credentials.
"""

from __future__ import annotations

import sys

import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url

from app.core.config import settings

TEST_DATABASE = "kira_playwright_test"


def main() -> None:
    app_url = make_url(str(settings.DATABASE_URL))
    if app_url.database == TEST_DATABASE:
        raise RuntimeError("App and Playwright databases must differ")
    admin_url = app_url.set(drivername="postgresql", database="postgres")
    try:
        with psycopg.connect(
            admin_url.render_as_string(hide_password=False), autocommit=True
        ) as connection:
            exists = connection.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DATABASE,)
            ).fetchone()
            if exists:
                # Only this hard-coded test database is replaced. Refuse to
                # force-disconnect any other process using it.
                connection.execute(
                    sql.SQL("DROP DATABASE {}").format(sql.Identifier(TEST_DATABASE))
                )
            connection.execute(
                sql.SQL("CREATE DATABASE {}").format(sql.Identifier(TEST_DATABASE))
            )
    except psycopg.Error as exc:
        raise RuntimeError(
            f"Could not prepare Playwright database ({type(exc).__name__})"
        ) from None
    sys.stdout.write(
        app_url.set(database=TEST_DATABASE).render_as_string(hide_password=False)
        + "\n"
    )


if __name__ == "__main__":
    main()
