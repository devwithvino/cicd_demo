# syntax=docker/dockerfile:1.7

# Build stage runs on the builder's native platform and cross compiles,
# so multi-arch builds never need slow emulation.
FROM --platform=$BUILDPLATFORM golang:1.27-alpine@sha256:f92b6ef800e499660581efdabdf25d9d817a9d124eaf900924f0504e7e27e12d AS build
WORKDIR /src

COPY go.mod go.sum ./
RUN --mount=type=cache,target=/go/pkg/mod go mod download

COPY . .
ARG TARGETOS
ARG TARGETARCH
ARG VERSION=dev
ARG GIT_SHA=unknown
ARG BUILD_TIME=unknown
ARG BROKEN_RELEASE=false
RUN --mount=type=cache,target=/go/pkg/mod \
    --mount=type=cache,target=/root/.cache/go-build \
    CGO_ENABLED=0 GOOS=$TARGETOS GOARCH=$TARGETARCH \
    go build -trimpath \
      -ldflags "-s -w \
        -X github.com/devwithvino/cicd_demo/services/api/internal/buildinfo.Version=${VERSION} \
        -X github.com/devwithvino/cicd_demo/services/api/internal/buildinfo.Commit=${GIT_SHA} \
        -X github.com/devwithvino/cicd_demo/services/api/internal/buildinfo.BuildTime=${BUILD_TIME} \
        -X github.com/devwithvino/cicd_demo/services/api/internal/buildinfo.BrokenRelease=${BROKEN_RELEASE}" \
      -o /out/api ./cmd/api

# Runtime stage: no shell, no package manager, non-root user.
FROM gcr.io/distroless/static-debian12:nonroot@sha256:afa5c872c891853ca7fcf1f12c3edb23f7eeef36189728842dd51042ff57f7ab
ARG VERSION=dev
ARG GIT_SHA=unknown
ARG BUILD_TIME=unknown
LABEL org.opencontainers.image.title="shipyard-api" \
      org.opencontainers.image.description="Shipyard API service" \
      org.opencontainers.image.source="https://github.com/devwithvino/cicd_demo" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${GIT_SHA}" \
      org.opencontainers.image.created="${BUILD_TIME}"
COPY --from=build /out/api /api
ENV PORT=8080
EXPOSE 8080
USER nonroot:nonroot
ENTRYPOINT ["/api"]
