#!/usr/bin/env bash
set -euo pipefail

: "${ADO_ORG_URL:?Set ADO_ORG_URL}"
: "${ADO_PAT:?Set ADO_PAT}"

OUT_DIR="${1:-out}"
mkdir -p "$OUT_DIR"

python -m src.ado_lang_inspector --out "$OUT_DIR"
