ARG API_IMAGE_TAG=v3.0.0-api.40
FROM ghcr.io/hsos6miyabi/rustdesk-api:${API_IMAGE_TAG}

ARG S6_OVERLAY_VERSION=3.2.0.0
ARG S6_ARCH=x86_64

ADD https://github.com/just-containers/s6-overlay/releases/download/v${S6_OVERLAY_VERSION}/s6-overlay-noarch.tar.xz /tmp/
ADD https://github.com/just-containers/s6-overlay/releases/download/v${S6_OVERLAY_VERSION}/s6-overlay-${S6_ARCH}.tar.xz /tmp/
RUN apt-get update \
 && apt-get install -y --no-install-recommends xz-utils \
 && rm -rf /var/lib/apt/lists/* \
 && tar -C / -Jxpf /tmp/s6-overlay-noarch.tar.xz \
 && tar -C / -Jxpf /tmp/s6-overlay-${S6_ARCH}.tar.xz \
 && rm /tmp/s6-overlay*.tar.xz \
 && ln -sf /run /var/run

COPY rootfs /
RUN chmod 755 /usr/bin/hbbs /usr/bin/hbbr /usr/bin/rustdesk-utils /usr/bin/healthcheck.sh

ENV RELAY=relay.example.com ENCRYPTED_ONLY=0 MUST_LOGIN=N
EXPOSE 21114 21115 21116 21116/udp 21117 21118 21119
HEALTHCHECK --interval=30s --timeout=5s CMD /usr/bin/healthcheck.sh
WORKDIR /app
VOLUME /app/data /data
ENTRYPOINT ["/init"]
