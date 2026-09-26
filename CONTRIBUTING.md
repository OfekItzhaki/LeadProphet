# Contributing

Keep changes small enough to review and verify independently. A useful commit sequence is:

1. Schema and migration changes.
2. Service and API behavior with tests.
3. UI wiring and documentation.

Run these checks from `backend` before opening a pull request:

```bash
python -m alembic upgrade head
python -m alembic check
python -m pytest -q
```

Never commit `.env`, local databases, access tokens, or provider credentials.
