#!/bin/sh
# 若挂载了证书则启用 HTTPS 配置，否则仅 HTTP
set -eu

CERT_DIR="${NGINX_CERT_DIR:-/etc/nginx/certs}"
FULLCHAIN="${CERT_DIR}/fullchain.pem"
PRIVKEY="${CERT_DIR}/privkey.pem"

if [ -f "$FULLCHAIN" ] && [ -f "$PRIVKEY" ]; then
  echo "[nginx] TLS certs found → using nginx.prod.ssl.conf"
  cp /etc/nginx/nginx.prod.ssl.conf /etc/nginx/nginx.conf
else
  echo "[nginx] no TLS certs at ${CERT_DIR} → using nginx.prod.conf (HTTP only)"
  cp /etc/nginx/nginx.prod.conf /etc/nginx/nginx.conf
fi

exec nginx -g "daemon off;"
