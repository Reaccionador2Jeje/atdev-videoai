#!/bin/sh
set -eu

: "${PORT:=8080}"
: "${ATDEV_PUBLIC_BASE_URL:=}"
: "${ATDEV_OAUTH_USERNAME:=}"
: "${ATDEV_OAUTH_PASSWORD:=}"
: "${ATDEV_DOWNLOAD_SECRET:=}"

export ATDEV_PORT=8765
export ATDEV_MCP_PORT=8766
export ATDEV_MCP_HOST=127.0.0.1
export ATDEV_OAUTH_DB=/var/lib/atdev-videoai/oauth.sqlite3

# Persistent data path; the Railway volume should be mounted at /var/lib/atdev-videoai.
mkdir -p /var/lib/atdev-videoai/projects /var/lib/atdev-videoai/renders /var/lib/atdev-videoai/assets
mkdir -p /app/projects /app/engine/renders /app/engine/assets
ln -sfn /var/lib/atdev-videoai/projects /app/projects
ln -sfn /var/lib/atdev-videoai/renders /app/engine/renders
ln -sfn /var/lib/atdev-videoai/assets /app/engine/assets

cat >/etc/nginx/conf.d/default.conf <<'NGINX'
server {
  listen 0.0.0.0:__PORT__;
  server_name _;
  client_max_body_size 40m;
  root /app;
  index index.html;

  location = /health {
    access_log off;
    return 200 "ok\\n";
    add_header Content-Type text/plain;
  }

  location ~ ^/(mcp|oauth/|actions/|\\.well-known/) {
    proxy_pass http://127.0.0.1:8766;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_buffering off;
    proxy_read_timeout 3600s;
  }

  location /api/ {
    proxy_pass http://127.0.0.1:8765;
    proxy_set_header Host $host;
    proxy_read_timeout 3600s;
  }

  location /download/ {
    proxy_pass http://127.0.0.1:8765;
    proxy_set_header Host $host;
  }

  location / {
    try_files $uri $uri/ /index.html;
  }
}
NGINX
sed -i "s/__PORT__/$PORT/g" /etc/nginx/conf.d/default.conf

python /app/engine/server.py &
ENGINE_PID=$!
python /app/mcp_http_server.py &
MCP_PID=$!
nginx -g 'daemon off;' &
NGINX_PID=$!

term() {
  kill "$ENGINE_PID" "$MCP_PID" "$NGINX_PID" 2>/dev/null || true
}
trap term TERM INT

wait "$NGINX_PID"
