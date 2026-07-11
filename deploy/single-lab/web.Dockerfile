FROM node:22-bookworm-slim AS builder

ENV PNPM_HOME=/pnpm
ENV PATH=$PNPM_HOME:$PATH
ENV CI=true
ENV HUSKY=0

WORKDIR /workspace
RUN corepack enable

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY patches ./patches
COPY apps/web/package.json ./apps/web/package.json
COPY packages/components/package.json ./packages/components/package.json
COPY packages/composables/package.json ./packages/composables/package.json
COPY packages/shared/package.json ./packages/shared/package.json
RUN --mount=type=cache,id=airalogy-pnpm-store,target=/pnpm/store \
    corepack pnpm install --frozen-lockfile --store-dir=/pnpm/store

COPY tsconfig.base.json uno.config.ts ./
COPY packages/shared ./packages/shared
COPY packages/composables ./packages/composables
COPY packages/components ./packages/components

ARG VITE_APP_TITLE="Airalogy Lab"
ARG VITE_APP_DESC="Private laboratory protocols, records, and research workflows."
ARG VITE_SITE_ORIGIN="http://localhost:8080"
ARG VITE_DOCS_URL="https://github.com/airalogy/platform/tree/main/docs"
ARG NODE_COMPONENT_BUILD_MEMORY_MB=3072
ARG NODE_BUILD_MEMORY_MB=4096

ENV VITE_APP_TITLE=$VITE_APP_TITLE
ENV VITE_APP_DESC=$VITE_APP_DESC
ENV VITE_SITE_ORIGIN=$VITE_SITE_ORIGIN
ENV VITE_DOCS_URL=$VITE_DOCS_URL
ENV VITE_DEPLOYMENT_MODE=single_lab
ENV VITE_SERVICE_ENV=prod
ENV VITE_HTTP_PROXY=N
ENV VITE_API_BASE_URL=/api
ENV VITE_MINIO_BASE_URL=/minio
ENV VITE_BASE_URL=/
ENV VITE_ROUTER_HISTORY_MODE=history
ENV VITE_AUTH_ROUTE_MODE=static
ENV VITE_ROUTE_HOME=home
ENV VITE_ICON_PREFIX=icon
ENV VITE_ICON_LOCAL_PREFIX=icon-local
ENV VITE_ICON_SHARED_PREFIX=icon-shared
ENV VITE_MENU_ICON=mdi:menu
ENV VITE_OSS_BASE=/minio
ENV VITE_SOURCE_MAP=N
ENV VITE_APP_ARMS_ENABLE=N
ENV VITE_CHINA_COMPLIANCE_FOOTER=N
ENV VITE_RECORD_DELETE_GRACE_DAYS=7
ENV VITE_MKCERT=N
ENV VITE_WATCH_WORKSPACE=N
ENV VITE_DEVTOOLS=N
ENV VITE_GA_ID=
RUN NODE_OPTIONS="--max-old-space-size=${NODE_COMPONENT_BUILD_MEMORY_MB}" \
    corepack pnpm run build:prepare
COPY apps/web ./apps/web
RUN NODE_OPTIONS="--max-old-space-size=${NODE_BUILD_MEMORY_MB}" \
    corepack pnpm --filter @airalogy/web build:no-check

FROM caddy:2.10.2-alpine

COPY deploy/single-lab/Caddyfile /etc/caddy/Caddyfile
COPY --from=builder /workspace/apps/web/dist /srv

EXPOSE 80 443 443/udp
