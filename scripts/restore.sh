#!/usr/bin/env bash
# Restore PostgreSQL + Qdrant + MinIO from a backup dir to a mutually-consistent
# state. The app tier is stopped during restore so no writes interleave.
#
#   bash scripts/restore.sh <backup_dir>
set -euo pipefail

DIR="${1:?usage: restore.sh <backup_dir>}"
COMPOSE="${COMPOSE:-docker compose -f docker-compose.dev.yml}"
QDRANT="${QDRANT_URL:-http://localhost:6333}"

echo ">> Stopping app tier (consistent restore window)"
$COMPOSE stop backend worker >/dev/null

echo ">> Restoring PostgreSQL"
$COMPOSE exec -T postgres psql -U rag -d rag -q < "$DIR/postgres.sql" >/dev/null 2>&1 || true

echo ">> Restoring Qdrant collections"
for f in "$DIR"/qdrant_*.snapshot; do
  [ -e "$f" ] || continue
  c=$(basename "$f" .snapshot); c=${c#qdrant_}
  curl -s -X POST "$QDRANT/collections/$c/snapshots/upload?priority=snapshot" \
    -F "snapshot=@$f" >/dev/null
  echo "   recovered $c"
done

if [ -f "$DIR/minio.tar" ]; then
  echo ">> Restoring MinIO objects (figures + pages)"
  $COMPOSE exec -T minio sh -c '
    mc alias set local http://localhost:9000 "${MINIO_ROOT_USER:-minioadmin}" "${MINIO_ROOT_PASSWORD:-minioadmin-dev-only}" >/dev/null 2>&1
    rm -rf /tmp/minio_restore && mkdir -p /tmp/minio_restore
    tar -C /tmp/minio_restore -xf -
    for b in figures pages; do
      mc mb --ignore-existing "local/$b" >/dev/null 2>&1 || true
      [ -d "/tmp/minio_restore/$b" ] && mc mirror --quiet --overwrite "/tmp/minio_restore/$b" "local/$b" >/dev/null 2>&1 || true
    done
  ' < "$DIR/minio.tar" && echo "   recovered figures + pages"
fi

echo ">> Restarting app tier"
$COMPOSE start backend worker >/dev/null
echo ">> Restore complete from: $DIR"
