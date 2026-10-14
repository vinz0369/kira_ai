---
name: repo-bootstrap
description: Reuse FastAPI Full Stack Template and adapt its existing React/Vite auth, database, Docker and CI without rebuilding boilerplate.
---
# Reuse the app scaffold

Read `AGENTS.md`, `docs/14_TEMPLATE_MIGRATION_ADR.md`, `docs/00_BUILD_ORDER.md`, then inspect upstream source and current git status.

## Procedure

1. Confirm `frontend/`, `backend/`, existing migrations, auth, CI, compose file. If missing, bootstrap from https://github.com/fastapi/full-stack-fastapi-template; pin upstream commit and retain license. Do not scaffold a separate Next.js app.
2. Run existing upstream startup/lint/tests unchanged first; note failures and upstream versions. Avoid deleting template routes/tests until substitutes pass.
3. Add AI Character tables and API routes to existing SQLModel/Alembic/backend router; extend React routes with Dashboard/Studio/Overlay.
4. Add Redis service to existing Docker config with health readiness; don't recreate its database or authentication.
5. Derive API type/client updates using mechanisms already provided by template; avoid hand-maintaining two incompatible DTOs.
6. Produce `IMPLEMENTATION_STATUS.md` with exact commands and screenshots only when tested.

## Done when

Upstream scaffold still starts; all initial tests pass; app-specific empty routes compile; docs validator passes; all new config has placeholders, no secrets.
