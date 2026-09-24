# Offline Deployment (Isolated Network, No Internet)

Production for this platform runs in an isolated network with **no internet
access at runtime**. Every dependency that needs the internet must be
resolved on a build machine that DOES have internet, packaged, and carried
across the air gap. Nothing in the running stack may fetch from a public
host — no CDN assets, no font CDNs, no `pip`/`npm` installs, no telemetry to
a public endpoint.

This document is the full story: build outside, transfer, load, bring the
stack up, what to expect on first boot, and what stays disabled unless you
point it at an internal endpoint.

## 1. What used to reach the internet (and no longer does)

An audit of the codebase found exactly one runtime internet dependency: the
frontend imported its three type faces (Syne, Manrope, JetBrains Mono) from
`fonts.googleapis.com` (`frontend/src/styles/mcait/fonts.css`). That import
has been replaced with local `@font-face` rules pointing at woff2 files
vendored into `frontend/src/assets/fonts/`; Vite fingerprints and bundles
them into `dist/assets/` at build time like any other static asset. There is
now no `fonts.googleapis` (or `fonts.gstatic`, `cdn.`, `unpkg`, `jsdelivr`,
`cdnjs`) string anywhere in `frontend/src/**`, `frontend/index.html`, or a
production `dist/` build — a regression test
(`frontend/src/offlineAssets.test.ts`) pins this so it can't regress
silently.

None of these three faces have Arabic glyphs. Arabic text already falls
through to the system fallback stack (`ui-sans-serif, system-ui,
-apple-system, "Segoe UI", sans-serif` — see `--font-sans` /
`--sans` in `frontend/src/styles/mcait/typography.css` and
`frontend/src/index.css`), which is unchanged by this work and resolves to
whatever Arabic-capable font the host OS provides. No regression there.

Everything else that talks to a service (the LLM endpoint, the optional
embeddings backend, the optional OpenTelemetry collector) already points at
an internal host by configuration — see §5.

## 2. Build outside the isolated network

On a machine WITH internet (this is where `pip install`, `npm install`, and
base-image pulls happen):

```powershell
# from the repo root
docker compose build backend frontend
docker pull postgres:16-alpine
# (once Task O2 lands: docker pull valkey/valkey:8-alpine — no changes
#  needed here, the bundle script reads it from docker-compose.yml)

# package everything into offline_bundle/
powershell -File .\scripts\build_offline_bundle.ps1
```

`scripts/build_offline_bundle.ps1` (PowerShell 5.1 compatible):

1. Regex-reads every `image:` line out of `docker-compose.yml` (today:
   `postgres:16-alpine`; will automatically pick up `valkey/valkey:8-alpine`
   once O2 adds it — no script edit needed).
2. Runs `docker compose build backend frontend` (skippable with
   `-SkipBuild` if the images already exist locally).
3. `docker pull`s the image-only services, then `docker save`s every image
   (pulled + built) to `offline_bundle/<name>.tar`.
4. Writes `offline_bundle/MANIFEST.json`: image names, image IDs, digests
   (via `docker inspect`), the git commit the bundle was built from, and the
   build timestamp.
5. Prints the transfer/load instructions reproduced in §3 below.

Flags: `-DryRun` prints what would be built/saved without touching Docker
(fast structure check); `-SkipBuild` saves already-built local images
without rebuilding.

Sizes, two honest kinds -- the O1 bundle run MEASURED these docker-save tars
(pre-tier-5 backend): postgres 111.3 MB, backend 303.4 MB, frontend 152.1 MB.
Tier 5's ML deps (scikit-learn, statsforecast, and its numba/llvmlite chain,
baked in at build time per the air-gap constraint) grow the BACKEND tar to an
ESTIMATED ~600-900 MB -- re-run `scripts/build_offline_bundle.ps1` to measure
your actual bundle; the other images are untouched by tier 5:

| image                     | save tar size                          |
|---------------------------|----------------------------------------|
| `postgres:16-alpine`      | 111.3 MB (measured, O1 run)            |
| `valkey/valkey:8-alpine`  | ~60 MB (estimated)                     |
| `data_analytics-backend`  | ~600-900 MB (estimated post-tier-5)    |
| `data_analytics-frontend` | 152.1 MB (measured, O1 run)            |

The backend image is ~1.4-1.8 GB uncompressed (numba/llvmlite's LLVM payload
is most of the growth over pre-tier-5); `docker save`'s tar comes out at
roughly half that. These are approximate and will drift with base-image and
dependency updates -- `offline_bundle/MANIFEST.json` records the exact image
digests for whatever bundle you actually built, and that file (not this
table) is the source of truth to verify a transferred bundle against. (The
frontend image here runs the Vite dev server per `frontend/Dockerfile` — see
§4 for the alternative of shipping the built `dist/` instead.)

## 3. Transfer and load, inside the isolated network

1. Copy the entire `offline_bundle/` directory (all `*.tar` files +
   `MANIFEST.json`) plus a checkout of this repository across the air gap
   (USB drive, secure file transfer — whatever your environment's approved
   mechanism is).
2. On the target host, for each `*.tar`:
   ```powershell
   docker load -i offline_bundle\postgres_16-alpine.tar
   docker load -i offline_bundle\data_analytics-backend.tar
   docker load -i offline_bundle\data_analytics-frontend.tar
   ```
3. Confirm the loaded images match `MANIFEST.json` (`docker images`,
   compare digests).
4. Create a `.env` (see `docker-compose.yml` for the variables it reads —
   `POSTGRES_*`, `SECRET_KEY`, `ALLOWED_ORIGINS`, `VITE_API_URL`, etc.) with
   values appropriate to the isolated network (internal hostnames, not
   `localhost`, if the frontend/backend are reached from other machines).
5. Bring the stack up:
   ```powershell
   docker compose up -d
   ```
   Compose uses the already-loaded local images/tags; nothing is pulled.

## 4. Frontend serving: dev server vs production build

`frontend/Dockerfile` is multi-stage, and compose defines **two** frontend
services. Which one you run is the difference between a development box and
a deployment:

| Service | Stage | Command | Port | Use |
|---|---|---|---|---|
| `frontend` | `dev` | `npm run dev` (HMR, source bind-mounted) | 3001 | day-to-day development; started by a plain `docker compose up` |
| `web` | `prod` | nginx serving the built `dist/` | 8090 | real deployments; behind the `prod` profile |

```powershell
# production: build the bundle into an nginx image and run it
docker compose --profile prod up -d --build web
```

The `web` image serves the static bundle **and proxies `/api` to the
backend**, so the app and the API share one origin. That is why the built
bundle contains no API hostname: `services/api.ts` falls back to a relative
`/api/v1` in production, and the same image runs on localhost, on a
customer's hostname, or behind their TLS terminator with no rebuild. Only a
split deployment (API on a different host) needs
`--build-arg VITE_API_URL=https://api.example.com`, exposed in compose as
`VITE_API_URL_BUILD`.

Override the published port with `WEB_PORT` (8080 is left alone on purpose —
it collides with other stacks often enough to be a bad default).

For the air-gapped bundle: `web` is a **built** service like the others, so
add it to `$BuiltServices` in `scripts/build_offline_bundle.ps1` when you
want the deployment image carried across the gap. Its nginx base layer is
pulled from the internet-connected machine at build time, exactly like
`postgres` and `valkey`.

## 5. First-boot expectations

### Alembic adoption / stamp

`backend/app/main.py`'s `lifespan` runs `_run_alembic()` at startup, under a
Postgres advisory lock (safe with multiple Uvicorn workers). Three cases,
all handled automatically — no manual DBA step required on first boot:

- **Fresh database** (no tables at all): `alembic upgrade head` runs every
  migration from scratch.
- **Database already stamped by Alembic** (has `alembic_version`):
  `alembic upgrade head` — a no-op if already current.
- **Database that only ever ran `create_all`/`_migrate`** (app tables exist,
  no `alembic_version` table — i.e., any environment that predates Alembic
  being adopted, T1): the app detects this and runs `alembic stamp head`,
  which writes only the version marker and runs no DDL. The existing schema
  is adopted without being touched. See `backend/alembic/README.md` for
  detail.

If the alembic step itself fails for any reason, startup logs the exception
and continues — `create_all`/`_migrate` (the pre-Alembic path) still runs,
so a first boot never hard-fails on a migration problem; it degrades to the
old schema-sync behavior instead.

### Uploads / data volumes

`uploaded_files` and `postgres_data` are named Docker volumes — they start
empty on a fresh host and persist across `docker compose down`/`up`
(not across `docker compose down -v`).

## 6. What stays disabled offline (unless pointed at an internal endpoint)

Everything below defaults to **off** or **internal-only** by configuration
(`backend/app/core/config.py`) — nothing tries to reach the public internet,
and a deployment that changes nothing here runs fully offline with these
features simply inactive:

- **LLM endpoint** (`llm_base_url`, default
  `http://10.125.18.189:8000/v1`, `llm_enabled=True`): used only for
  Layer-1 column/table descriptions during a catalog sync — an improvement,
  never a requirement. `services/llm.py` returns `None` rather than raising
  when the box is unreachable, so a sync still completes with the model
  endpoint down. **This must point at an internal, self-hosted
  OpenAI-compatible endpoint (e.g. vLLM) inside the isolated network** — it
  is internal by design, never a public API.
- **Backend-B embeddings** (`embedding_base_url` / `embedding_model` /
  `embedding_dim`, all `None` by default): Tier-2 retrieval's lexical
  Backend A (pure numpy TF-IDF) is always available and is the default.
  Backend B (an OpenAI-compatible embeddings endpoint) only activates if all
  three settings are provided, pointing at an internal endpoint; any
  query-time failure (unreachable, wrong response shape, timeout) falls
  back to Backend A automatically — retrieval degrading, never breaking the
  agent.
- **OpenTelemetry** (`otel_enabled=False` by default, `otel_endpoint`
  unset): off by default, and the otel packages are never even imported
  unless explicitly enabled (`core/telemetry.py`), so a broken or absent
  otel install can never brick startup. If enabled, `otel_endpoint` must
  point at an **internal** collector — never a public SaaS telemetry
  endpoint.
- **SMTP** (`smtp_host=""` by default): outbound email for scheduled
  deliveries/alerts. An unset host means delivery is recorded as
  undeliverable rather than raising; a deployment without an internal SMTP
  relay still schedules deliveries, the status column just explains why
  nothing arrived. Point `smtp_host` at an internal mail relay to enable it.
- **Valkey shared cache** (Task O2, `valkey_url`, default `None`): the
  platform runs with today's in-process cache behavior byte-for-byte when
  unset. Only activates against an internal Valkey service added to
  `docker-compose.yml`.

None of the above require internet — only, optionally, an internal service
inside the isolated network. With all of them left at their defaults, the
platform is fully functional offline (query, report, dashboard, connector,
row-security, and scheduling features do not depend on any of the above).
