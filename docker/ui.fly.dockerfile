# syntax=docker/dockerfile:1

FROM oven/bun:1 AS builder

WORKDIR /app/ui

COPY ui/package.json ui/bun.lock ./
RUN bun install --frozen-lockfile

COPY ui/ .

ARG VITE_API_ORIGIN=""
ENV VITE_API_ORIGIN=${VITE_API_ORIGIN}

RUN bun run build


FROM caddy:2-alpine AS runtime

WORKDIR /srv

COPY docker/Caddyfile /etc/caddy/Caddyfile
COPY --from=builder /app/ui/dist /srv

EXPOSE 8080
