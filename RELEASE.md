# LeadProphet 1.0.1 Release

The application, API, and release version are `1.0.1`. Update `VERSION`, `Settings.app_version`, FastAPI metadata, and this document together for future releases.

## Checklist

- Run `python -m pytest -q` from `backend`, then `npm run test:e2e` from the repository root.
- Run `npm run test:e2e:flaky` for repeated Chromium coverage when changing shared test state.
- Run `npm run test:e2e:production`.
- Run `python -m alembic upgrade head` and `python -m alembic check` from `backend`.
- Run dependency and static security checks documented in `TESTING.md`.
- Verify production environment values and back up the target database.
- Build the container with `docker compose build` and run the production smoke test.
- Tag the verified commit as `v1.0.1`.

## Rollback

Database migrations are forward-first. Before deployment, create a PostgreSQL dump. If application rollback is required, deploy the previous image and restore that dump into a clean database. Do not run destructive Alembic downgrades against production data without a reviewed migration-specific plan. Static application rollback is performed by redeploying the prior immutable image tag.
