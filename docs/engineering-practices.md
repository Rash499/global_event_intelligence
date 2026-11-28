# Engineering workflow

Backend lint is Ruff (`backend/pyproject.toml`, deliberately limited to core correctness/style checks). Frontend lint is Biome with a minimal, low-noise ruleset. From the repository root:

```bash
cd backend && python -m ruff check app tests scripts
cd frontend && npm run lint && npx tsc -b && npx vitest run && npm run build
```

FastAPI OpenAPI component and path types are generated into `frontend/src/services/generatedApi.ts` with `npm run types:api`. The API service references the generated request types. Regenerate after changing API schemas/routes and commit the output.

The pre-push hook runs backend lint/tests and frontend lint/typecheck/unit tests. Install it once with `./scripts/install-git-hooks.sh` (this sets `core.hooksPath` for the clone). Playwright smoke tests use local demo data and axe checks; run with `cd frontend && npm run test:e2e`. CI runs these in a separate E2E job.
