# syntax=docker/dockerfile:1.7

# Build stage: install all dependencies, compile TypeScript, then drop dev dependencies.
FROM node:24-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci --no-audit --no-fund
COPY . .
RUN npm run build && npm prune --omit=dev

# Runtime stage: compiled output and production dependencies only, non-root user.
FROM node:24-alpine
ARG VERSION=dev
ARG GIT_SHA=unknown
ARG BUILD_TIME=unknown
LABEL org.opencontainers.image.title="shipyard-web" \
      org.opencontainers.image.description="Shipyard web dashboard" \
      org.opencontainers.image.source="https://github.com/devwithvino/cicd_demo" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${GIT_SHA}" \
      org.opencontainers.image.created="${BUILD_TIME}"
WORKDIR /app
ENV NODE_ENV=production \
    APP_VERSION=${VERSION} \
    GIT_SHA=${GIT_SHA} \
    BUILD_TIME=${BUILD_TIME} \
    PORT=8082
COPY --from=build --chown=node:node /app/package.json ./
COPY --from=build --chown=node:node /app/node_modules ./node_modules
COPY --from=build --chown=node:node /app/dist ./dist
EXPOSE 8082
USER node
CMD ["node", "dist/server/main.js"]
