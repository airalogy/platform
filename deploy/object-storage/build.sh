#!/bin/sh
set -eu
cd /build
. ./sources.env

fetch_source() {
  name="$1" commit="$2" checksum="$3"
  mkdir -p "/src/$name" /sources
  printf 'Fetching official %s source at %s\n' "$name" "$commit"
  wget -T 60 -q -O "/sources/$name-upstream.tar.gz" "https://codeload.github.com/minio/$name/tar.gz/$commit"
  printf '%s  %s\n' "$checksum" "/sources/$name-upstream.tar.gz" | sha256sum -c -
  tar -xzf "/sources/$name-upstream.tar.gz" --strip-components=1 -C "/src/$name"
}

prepare() {
  name="$1"
  cd "/src/$name"
  printf 'Preparing checksum-verified %s build dependencies\n' "$name"
  # Vendor only the build/test dependency closure rather than downloading every
  # transitive module's unrelated packages. Downloads still verify go.sum/sumdb.
  timeout 1200 go mod vendor
  go mod verify
  # Include corresponding source, dependency licenses and vendored modules.
  tar -czf "/sources/$name-vendored.tar.gz" -C /src "$name"
  cd /build
}

compile() {
  name="$1" commit="$2" version="$3" release="$4"
  cd "/src/$name"
  printf 'Compiling %s for %s/%s\n' "$name" "$GOOS" "$GOARCH"
  timeout 1200 go build -mod=vendor -trimpath -buildvcs=false -ldflags \
    "-s -w -X github.com/minio/$name/cmd.Version=$version -X github.com/minio/$name/cmd.ReleaseTag=$release -X github.com/minio/$name/cmd.CommitID=$commit -X github.com/minio/$name/cmd.ShortCommitID=$(printf '%s' "$commit" | cut -c1-12) -X github.com/minio/$name/cmd.CopyrightYear=2025" \
    -o "/out/$name" .
  cd /build
}

case "${1:-}" in
  fetch)
    fetch_source minio "$MINIO_COMMIT" "$MINIO_SOURCE_SHA256"
    fetch_source mc "$MC_COMMIT" "$MC_SOURCE_SHA256"
    ;;
  prepare)
    prepare minio
    prepare mc
    cp sources.env build.sh Dockerfile /sources/
    ;;
  compile)
    mkdir -p /out
    compile minio "$MINIO_COMMIT" "$MINIO_VERSION" "$MINIO_RELEASE"
    compile mc "$MC_COMMIT" "$MC_VERSION" "$MC_RELEASE"
    ;;
  *) echo 'Expected fetch, prepare or compile' >&2; exit 2 ;;
esac
