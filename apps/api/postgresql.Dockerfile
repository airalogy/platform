ARG PG_MAJOR=16
ARG POSTGRES_IMAGE_VERSION=16.14
ARG POSTGRES_SERVER_DEV_VERSION=16.14-1.pgdg12+1
FROM postgres:${POSTGRES_IMAGE_VERSION}-bookworm AS builder
ARG PG_MAJOR
ARG POSTGRES_SERVER_DEV_VERSION
ARG APT_DEBIAN_MIRROR=http://deb.debian.org/debian
ARG APT_DEBIAN_SECURITY_MIRROR=http://deb.debian.org/debian-security
ARG APT_POSTGRES_MIRROR=http://apt.postgresql.org/pub/repos/apt

# zhparser Dockerfile: https://github.com/amutu/zhparser/blob/master/docker/bookworm/16/Dockerfile
# pgvector Dockerfile: https://github.com/pgvector/pgvector/blob/master/Dockerfile

# Set the environment variable to handle non-interactive installations
ARG DEBIAN_FRONTEND=noninteractive

# Install dependencies for building zhparser. pgvector is installed from PGDG packages.
# postgresql-server-dev is downloaded and unpacked for headers only, avoiding its heavy LLVM dependency chain.
RUN set -eux; \
    find /etc/apt -type f \( -name '*.list' -o -name '*.sources' \) -exec sed -i \
        -e "s|http://deb.debian.org/debian-security|${APT_DEBIAN_SECURITY_MIRROR}|g" \
        -e "s|http://deb.debian.org/debian|${APT_DEBIAN_MIRROR}|g" \
        -e "s|http://apt.postgresql.org/pub/repos/apt|${APT_POSTGRES_MIRROR}|g" \
        {} +; \
    printf 'Acquire::Retries "5";\nAcquire::http::Timeout "30";\nAcquire::https::Timeout "30";\n' > /etc/apt/apt.conf.d/80-retries \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        git \
        postgresql-${PG_MAJOR}-pgvector \
        pkg-config \
        binutils \
        automake \
        libtool \
        ca-certificates \
    && apt-get download postgresql-server-dev-${PG_MAJOR}=${POSTGRES_SERVER_DEV_VERSION} \
    && dpkg-deb -x postgresql-server-dev-${PG_MAJOR}_${POSTGRES_SERVER_DEV_VERSION}_*.deb / \
    && rm postgresql-server-dev-${PG_MAJOR}_${POSTGRES_SERVER_DEV_VERSION}_*.deb \
    && rm -rf /var/lib/apt/lists/*

# Build and install scws for zhparser
RUN git clone --branch 1.2.3 --single-branch --depth 1 https://github.com/hightman/scws.git && \
    cd scws && \
    touch README && aclocal && autoconf && autoheader && libtoolize && automake --add-missing && \
    ./configure && \
    make install

# Build and install zhparser
RUN git clone --branch master --single-branch --depth 1 https://github.com/amutu/zhparser.git && \
    cd zhparser && \
    make install with_llvm=no

# Final stage for the PostgreSQL image
FROM postgres:${POSTGRES_IMAGE_VERSION}-bookworm
ARG PG_MAJOR


# Copy files from the builder stage
COPY --from=builder /usr/local/lib/libscws.* /usr/local/lib/
COPY --from=builder /usr/lib/postgresql/${PG_MAJOR}/lib/* /usr/lib/postgresql/${PG_MAJOR}/lib/
COPY --from=builder /usr/share/postgresql/${PG_MAJOR}/extension/* /usr/share/postgresql/${PG_MAJOR}/extension/
COPY --from=builder /usr/share/postgresql/${PG_MAJOR}/tsearch_data/*.utf8.* /usr/share/postgresql/${PG_MAJOR}/tsearch_data/
