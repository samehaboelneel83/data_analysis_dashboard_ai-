# Three stages, two of them shipped.
#
#   dev   — the Vite dev server with HMR. What `docker compose up` runs, and
#           what the source bind-mounts in docker-compose.yml expect.
#   build — produces the static bundle. Never run on its own.
#   prod  — nginx serving that bundle. What a real deployment runs.
#
# Until now compose ran the DEV SERVER in production: no minification, no
# cache headers, source maps and the HMR websocket exposed, and a rebuild of
# every module on each page load. docs/OFFLINE_DEPLOYMENT.md described the
# static path as the thing still to do; this file is it.
#
# `target:` is therefore REQUIRED on both compose services — a multi-stage
# Dockerfile with no target builds the LAST stage, which would silently turn
# the dev service into an nginx container with no HMR.

FROM node:20-alpine AS dev
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
EXPOSE 3000
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "3000"]


FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
# No VITE_API_URL is passed on purpose: an unset value makes the bundle call
# its OWN origin (see services/api.ts), so the same image works on any
# hostname. Pass --build-arg VITE_API_URL=https://api.example.com only when
# the API is served from a different origin than the app.
ARG VITE_API_URL=""
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build


FROM nginx:1.27-alpine AS prod
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
