#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ASSET_DIR="$ROOT_DIR/app/src/main/assets"
MODEL_PATH="$ASSET_DIR/pose_landmarker_lite.task"
MODEL_URL="https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task"

mkdir -p "$ASSET_DIR"

if [[ -s "$MODEL_PATH" ]]; then
  echo "Pose model already exists: $MODEL_PATH"
  exit 0
fi

curl --fail --location --show-error "$MODEL_URL" --output "$MODEL_PATH"
echo "Downloaded Pose Landmarker model: $MODEL_PATH"
