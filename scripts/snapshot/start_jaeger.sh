#!/usr/bin/env bash
set -e
# Idempotent: skip if container exists
if docker ps -a --format '{{.Names}}' | grep -q '^v10-jaeger$'; then
  docker start v10-jaeger >/dev/null
  echo "v10-jaeger already exists; started."
else
  docker run -d --name v10-jaeger --restart unless-stopped \
    -p 16686:16686 -p 4317:4317 -p 4318:4318 \
    jaegertracing/all-in-one:latest
fi
echo "Jaeger UI: http://localhost:16686"
echo "OTLP HTTP endpoint: http://localhost:4318/v1/traces"
