#!/usr/bin/env bash
# Consistent backup of ALL THREE stores: PostgreSQL (pg_dump) + Qdrant
# (snapshots) + MinIO (object mirror). Run during low write activity for a clean
# point-in-time set; restore.sh stops the app tier so the restored state is
# mutually consistent.
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

echo ">> MinIO object mirror (figures + pages buckets) -> $DIR/minio.tar"
# `mc` runs inside the minio container against the local server; the figure
# crops + page renders are re-imported by restore.sh. Losing the object store
# breaks citation thumbnails and the visual answer path.
$COMPOSE exec -T minio sh -c '
  mc alias set local http://localhost:9000 "${MINIO_ROOT_USER:-minioadmin}" "${MINIO_ROOT_PASSWORD:-minioadmin-dev-only}" >/dev/null 2>&1
  rm -rf /tmp/minio_backup && mkdir -p /tmp/minio_backup
  for b in figures pages; do
    mc mirror --quiet --overwrite "local/$b" "/tmp/minio_backup/$b" >/dev/null 2>&1 || true
  done
  tar -C /tmp/minio_backup -cf - . 2>/dev/null
' > "$DIR/minio.tar" || echo "   (minio empty or unavailable — skipped)"

echo ">> Backup complete: $DIR  (postgres.sql, qdrant_*.snapshot, minio.tar)"
