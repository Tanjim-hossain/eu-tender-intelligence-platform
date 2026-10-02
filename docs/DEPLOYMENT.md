# Deployment and publication readiness

## Decision

Keep the native Mac application as the primary live demo: PostgreSQL in Docker,
FastAPI and Ollama on the host. Publish the repository, benchmark evidence and a
short screen recording first. This demonstrates the complete workflow without
operating an unauthenticated public inference endpoint.

If a public interactive demo is later required, the simplest architecture to
assess is one small Linux host running the API and PostgreSQL/pgvector with
persistent storage, protected by a TLS reverse proxy and authentication/rate
limits. Start with evidence mode. Local Qwen adds memory/compute requirements
and needs measured capacity before sizing a machine. No paid provider or cloud deployment is required for the current local setup.

## Optional local API container

`Dockerfile` uses a locked uv installation in a build stage and a non-root runtime
with one worker. Browser assets are installed from the package. The runtime image
excludes development tools/dbt; ingestion and dbt remain in the host checkout.
The allowlisted Docker context excludes `.env`, Git, datasets and audit artifacts.

```bash
# Keep the existing .env and PostgreSQL project/volume.
make app-build
make app-up
curl -fsS http://127.0.0.1:8000/health
make app-stop
```

Stop the native API first if it already uses port 8000, or use
`API_PORT=8001 make app-up`. These targets compose `infra/compose.yml` with
`infra/compose.app.yml`; they do not start a separate database project.

The overlay intentionally uses evidence mode. `127.0.0.1` inside the container
refers to the container; the existing loopback-only Ollama URL validation is kept.
Use the native app for local Ollama rather than weakening that boundary or exposing
the Mac daemon. The container stores model downloads in its own named cache volume,
mounts refresh audits read-only, and binds HTTP to host loopback. Ensure
`data/refresh` and its audits are readable by the container's UID 10001.

The first API start needs model download access and can exceed the initial health
check grace period. Download/cache before an offline demo. A failed health check
does not by itself restart a running Docker container. Inspect startup logs.

The current Linux dependency lock includes large PyTorch/CUDA wheels even when
inference uses CPU; budget several GB for download/image storage. The project currently preserves the tested dependency resolution. A CPU-specific lock/image is a future
optimization requiring separate cross-platform verification. Python base-image
tags and model names are not immutable digests/revisions, so this is dependency-
locked reproducibility, not a bit-for-bit hermetic build.

The API image has been built successfully both locally and through GitHub Actions.
CI also verifies that the packaged application can import and serve its static
assets without requiring a database or language model at test time. Full live
database and Ollama behavior should still be verified locally before a demo.

## Before public hosting

- Add authentication, rate limits, request/concurrency limits and TLS.
- Restrict PostgreSQL networking: the existing database Compose port binds broadly
  by default. Do not publish port 5433 to the internet; bind loopback or use only
  a private network on the deployment host.
- Separate application read access from refresh/migration database privileges.
- Persist/backup the database, audit artifacts and model cache; test restoration.
- Serialize scheduled refreshes, monitor stale/failed/running audits and budget
  model timeouts/memory under concurrent requests.
- Review raw exception logs and source excerpts before sharing; keep credentials
  in runtime secrets, never in the image or repository.
- Verify image build/start, real search/ask, backup recovery, and protected ingress.


## GitHub repository

The project is published as a public GitHub repository and uses GitHub Actions for
continuous integration.

The CI workflow checks code quality, typing, tests, answer-contract behavior,
Python packaging and the API Docker image on pushes and pull requests.

Before creating a release, I would re-run the local database and retrieval smoke
tests together with the hosted CI workflow.

No software license is currently declared. A license should be selected explicitly
before granting reuse rights to the code.

Implementation references: [uv Docker integration](https://docs.astral.sh/uv/guides/integration/docker/),
[GitHub checkout](https://github.com/actions/checkout),
[setup-uv](https://github.com/astral-sh/setup-uv). No hosted deployment was attempted.
