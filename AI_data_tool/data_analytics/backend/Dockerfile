# Two stages, both shipped.
#
#   dev  — what `docker compose up` runs: the source is BIND-MOUNTED over /app
#          by docker-compose.yml and uvicorn --reload watches it. The image
#          itself carries only the dependencies.
#   prod — a self-contained image: the source is COPIED in, it runs as an
#          unprivileged user, and uvicorn runs without --reload. What
#          docker-compose.prod.yml builds for a real deployment.
#
# Until now the only image was the dev one, so production depended on a
# source mount, ran as root, and ran the auto-reloader (release blocker, gap
# analysis section 6). `target:` is set on the compose service for the same
# reason as frontend/Dockerfile: with no target a multi-stage build takes the
# LAST stage.

FROM python:3.12-slim AS base
WORKDIR /app
# mdbtools reads Microsoft Access (.mdb/.accdb). Microsoft's own ACE/Jet
# provider is Windows-only, so on this image it is the only way to read Access
# at all. Debian bookworm ships 1.0.0, the release that added .accdb support.
# Needed at BUILD time only -- the running container makes no network calls.
RUN apt-get update && apt-get install -y --no-install-recommends freetds-dev mdbtools && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir --timeout 300 --retries 5 -r requirements.txt
EXPOSE 8000


FROM base AS prod
# A fixed uid so a host-side volume can be chowned to it before first start
# (see docs/BACKUP_AND_RECOVERY.md: a volume first written by the old
# root-run image is owned by root and this user cannot write to it).
RUN groupadd --system --gid 10001 datalytics \
 && useradd --system --uid 10001 --gid datalytics --home-dir /app --shell /usr/sbin/nologin datalytics
COPY --chown=datalytics:datalytics . .
RUN mkdir -p /app/uploads && chown datalytics:datalytics /app/uploads
USER datalytics
# UVICORN_WORKERS processes, no reloader. Startup is advisory-lock serialized
# (app.main lifespan) and the scheduler is advisory-locked per item, so
# several workers are safe by construction.
ENV UVICORN_WORKERS=2
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers \"${UVICORN_WORKERS}\""]


FROM base AS dev
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
