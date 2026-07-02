#!/usr/bin/env bash
# Consistent backup of BOTH stores: PostgreSQL (pg_dump) + Qdrant (snapshots).
# Run during low write activity for a clean point-in-time pair; restore.sh stops
# the app tier so the restored Postgres+Qdrant state is mutually consistent.
#
#   bash scripts/backup.sh [backup_dir]
set -euo pipefail

DIR="${1:-./backups/$(date +%Y%m%d_%H%M%S)}"
COMPOSE="${COMPOSE:-docker compose -f docker-compose.dev.yml}"
QDRANT="${QDRANT_URL:-http://localhost:6333}"
mkdir -p "$DIR"

echo ">> PostgreSQL dump -> $DIR/postgres.sql"
$COMPOSE exec -T postgres pg_dump -U rag --clean --if-exists rag > "$DIR/postgres.sql"

echo ">> Qdrant snapshots"
COLLS=$(curl -s "$QDRANT/collections" | python -c "import json,sys;print(' '.join(c['name'] for c in json.load(sys.stdin)['result']['collections']))")
for c in $COLLS; do
  name=$(curl -s -X POST "$QDRANT/collections/$c/snapshots" | python -c "import json,sys;print(json.load(sys.stdin)['result']['name'])")
  curl -s "$QDRANT/collections/$c/snapshots/$name" -o "$DIR/qdrant_$c.snapshot"
  echo "   $c -> qdrant_$c.snapshot"
done

echo ">> Backup complete: $DIR"
