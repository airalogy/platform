FROM --platform=$BUILDPLATFORM golang:1.26.9-alpine3.23@sha256:96123126ac58e910f4dd3619a8901e2fb6d1ad84b59b1232cac7c9ea65a8f888 AS source
ENV CGO_ENABLED=0 GOTOOLCHAIN=local GOMAXPROCS=2
WORKDIR /build
COPY sources.env build.sh Dockerfile ./
RUN sh build.sh fetch
RUN --mount=type=cache,target=/go/pkg/mod sh build.sh prepare

FROM source AS build
ARG TARGETARCH
ENV GOOS=linux GOARCH=$TARGETARCH
RUN --mount=type=cache,target=/root/.cache/go-build sh build.sh compile

FROM alpine:3.23@sha256:85fe1e81d6758c208f3e1eed4338a1997e19d4be002d4dd32d3100c9a8c010a0
ARG PLATFORM_VERSION=development
ARG GIT_COMMIT=unknown
LABEL org.opencontainers.image.title="Airalogy Platform object storage (upstream MinIO and mc)" \
      org.opencontainers.image.source="https://github.com/airalogy/platform" \
      org.opencontainers.image.version="$PLATFORM_VERSION" \
      org.opencontainers.image.revision="$GIT_COMMIT" \
      org.opencontainers.image.licenses="AGPL-3.0-or-later" \
      io.airalogy.minio.commit="9e49d5e7a648f00e26f2246f4dc28e6b07f8c84a" \
      io.airalogy.mc.commit="7394ce0dd2a80935aded936b09fa12cbb3cb8096"
COPY --from=build /out/minio /out/mc /usr/bin/
COPY --from=source /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/
COPY --from=source /sources /usr/share/airalogy-object-storage/source
COPY --from=source /src/minio/LICENSE /licenses/minio/LICENSE
COPY --from=source /src/mc/LICENSE /licenses/mc/LICENSE
COPY --from=source /usr/local/go/LICENSE /licenses/go/LICENSE
ENV MINIO_UPDATE=off
EXPOSE 9200 9201
ENTRYPOINT ["minio"]
CMD ["server", "/data", "--address", ":9200", "--console-address", ":9201"]
