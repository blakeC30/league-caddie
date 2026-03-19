# Multi-stage production Dockerfile
#
# Stage 1 (builder): installs all deps and runs `npm run build` to produce /app/dist
# Stage 2 (runtime): Nginx alpine serves the static files — no Node in prod
#
# The API proxy is NOT configured here. In production, Traefik ingress
# handles routing: /api/* → backend service, /* → this Nginx service.
# This keeps the frontend image fully stateless and ignorant of backend URLs.

# ─────────────────────────────────────────────────────────────────────────────
# Stage 1: Build the React + Vite application
# ─────────────────────────────────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

# Install all dependencies first (including devDependencies — Vite, TypeScript,
# Tailwind are dev deps needed for the build step).
# Copy lockfile + package.json before source so a code-only change doesn't
# bust the expensive npm ci layer.
COPY package*.json ./
RUN npm ci

# Copy source and produce the optimised static build.
COPY . .
RUN npm run build

# ─────────────────────────────────────────────────────────────────────────────
# Stage 2: Nginx — serve the static build, nothing else
# ─────────────────────────────────────────────────────────────────────────────
FROM nginx:alpine AS runtime

# Patch OS-level vulnerabilities in the base image before adding anything else.
RUN apk update && apk upgrade --no-cache && rm -rf /var/cache/apk/*

# Replace the default nginx config with our own (React Router + gzip + caching).
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy only the compiled output — no node_modules, no source, no secrets.
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

# Nginx alpine includes wget; use it for the liveness probe.
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -qO- http://localhost/health || exit 1

# nginx:alpine already sets CMD ["nginx", "-g", "daemon off;"] — no override needed.
