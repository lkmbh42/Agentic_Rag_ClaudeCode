#!/usr/bin/env bash
# One-time Docling model staging (setup-time network access only — distinct
# from the air-gapped-at-RUNTIME guarantee, Rule 2). Downloads the pinned
# layout + TableFormer artifacts into MODELS_DIR/docling, which prod mounts
# read-only and points DOCLING_ARTIFACTS_PATH at. After this step, Docling
# never touches the network.
#
# Usage (on the provisioning host with network access):
#   MODELS_DIR=./models bash scripts/stage-docling-models.sh
#
# Pin: docs/PINS.md §4 records the exact revision. CI fails on unpinned refs.
set -euo pipefail

MODELS_DIR="${MODELS_DIR:-./models}"
TARGET="${MODELS_DIR}/docling"
# ds4sd/docling-models revision — operator fills the pinned hash at provisioning
# (placeholder scheme identical to the CLAUDE.md model manifest).
REVISION="${DOCLING_MODELS_REVISION:-<HF_REVISION_HASH>}"

if [[ "${REVISION}" == "<HF_REVISION_HASH>" ]]; then
  echo "WARNING: no pinned revision set (DOCLING_MODELS_REVISION)." >&2
  echo "         Dev staging proceeds with the docling default; PROD MUST PIN." >&2
  python -c "
from docling.utils.model_downloader import download_models
from pathlib import Path
download_models(output_dir=Path('${TARGET}'), progress=True)
"
else
  python -c "
from huggingface_hub import snapshot_download
snapshot_download('ds4sd/docling-models', revision='${REVISION}',
                  local_dir='${TARGET}')
"
fi

echo ">> Docling artifacts staged in ${TARGET}"
echo ">> Set DOCLING_ARTIFACTS_PATH=/models/docling in prod .env"
