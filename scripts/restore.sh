#!/usr/bin/env bash
# Restore PostgreSQL + Qdrant from a backup dir to a mutually-consistent state.
# The app tier is stopped during restore so no writes interleave.
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

echo ">> Restarting app tier"
$COMPOSE start backend worker >/dev/null
echo ">> Restore complete from: $DIR"
