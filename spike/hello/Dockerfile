# Throwaway image for the Phase 0 platform spike. Removed once the real services exist.
FROM busybox:1.36
ARG VERSION=dev
ARG GIT_SHA=unknown
RUN mkdir -p /www && \
    printf '{"service":"hello","version":"%s","sha":"%s"}\n' "$VERSION" "$GIT_SHA" > /www/version && \
    echo ok > /www/healthz
USER 65534
ENV PORT=10000
EXPOSE 10000
CMD ["sh", "-c", "httpd -f -v -p ${PORT} -h /www"]
