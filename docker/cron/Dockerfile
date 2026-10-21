# curl and tzdata are baked in at build time: the target server has no network,
# so nothing may be installed when the container starts.
FROM alpine:3.20

RUN apk add --no-cache curl tzdata

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
