FROM alpine:3.20
ARG NGINX_VERSION=1.25.5
ARG NGINX_RTMP_VERSION=1.2.2

# Faster mirrors (Timeweb RU)
RUN sed -i 's|https://dl-cdn.alpinelinux.org/alpine|https://mirror.yandex.ru/mirrors/alpine|g' /etc/apk/repositories || true

RUN set -eux; apk add --no-cache ca-certificates pcre2 zlib openssl

RUN set -eux; apk add --no-cache --virtual .build-deps build-base pcre2-dev zlib-dev openssl-dev linux-headers curl tar

RUN set -eux; mkdir -p /tmp/src; cd /tmp/src; \
  curl -fsSL "http://nginx.org/download/nginx-${NGINX_VERSION}.tar.gz" -o nginx.tar.gz; \
  curl -fsSL "https://github.com/arut/nginx-rtmp-module/archive/refs/tags/v${NGINX_RTMP_VERSION}.tar.gz" -o rtmp.tar.gz; \
  tar -xzf nginx.tar.gz; tar -xzf rtmp.tar.gz

RUN set -eux; cd /tmp/src/nginx-${NGINX_VERSION}; \
  ./configure --prefix=/usr/local/nginx \
    --conf-path=/etc/nginx/nginx.conf \
    --with-http_ssl_module \
    --with-http_stub_status_module \
    --with-threads \
    --with-file-aio \
    --add-module="/tmp/src/nginx-rtmp-module-${NGINX_RTMP_VERSION}"; \
  make -j"$(nproc)"; \
  make install; \
  ln -sf /usr/local/nginx/sbin/nginx /usr/sbin/nginx

RUN set -eux; rm -rf /tmp/src; apk del .build-deps

COPY nginx.conf /etc/nginx/nginx.conf
EXPOSE 1935 8080

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
CMD ["nginx","-g","daemon off;"]
