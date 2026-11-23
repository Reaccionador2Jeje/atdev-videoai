FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg nginx ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && mkdir -p /var/lib/atdev-videoai /run/nginx

WORKDIR /app
COPY . .
COPY deploy/start.sh /usr/local/bin/atdev-start
RUN chmod +x /usr/local/bin/atdev-start \
 && mkdir -p /app/projects /app/engine/renders /app/engine/assets

EXPOSE 8080
CMD ["/usr/local/bin/atdev-start"]
