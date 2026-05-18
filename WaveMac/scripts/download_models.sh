#!/usr/bin/env bash
# download_models.sh — Baixa os modelos ONNX do MediaPipe para o WaveMac
# Os modelos são convertidos da versão TFLite oficial do Google MediaPipe.
# Fonte: https://github.com/PINTO0309/PINTO_model_zoo

set -euo pipefail

MODELS_DIR="$(dirname "$0")/../assets/models"
mkdir -p "$MODELS_DIR"

echo "📦 Baixando modelos ONNX do MediaPipe..."

# Palm Detection Lite (192x192, ~2.9 MB)
PALM_URL="https://huggingface.co/PINTO0309/palm_detection_mediapipe/resolve/main/palm_detection_lite.onnx"
PALM_PATH="$MODELS_DIR/palm_detection_lite.onnx"

if [ -f "$PALM_PATH" ]; then
    echo "   ✅ palm_detection_lite.onnx já existe, pulando."
else
    echo "   ⬇️  Baixando palm_detection_lite.onnx..."
    curl -L --progress-bar "$PALM_URL" -o "$PALM_PATH"
    echo "   ✅ palm_detection_lite.onnx baixado."
fi

# Hand Landmark Lite (256x256, ~7.4 MB)
LANDMARK_URL="https://huggingface.co/PINTO0309/hand_landmark_mediapipe/resolve/main/hand_landmark_lite.onnx"
LANDMARK_PATH="$MODELS_DIR/hand_landmark_lite.onnx"

if [ -f "$LANDMARK_PATH" ]; then
    echo "   ✅ hand_landmark_lite.onnx já existe, pulando."
else
    echo "   ⬇️  Baixando hand_landmark_lite.onnx..."
    curl -L --progress-bar "$LANDMARK_URL" -o "$LANDMARK_PATH"
    echo "   ✅ hand_landmark_lite.onnx baixado."
fi

echo ""
echo "✅ Modelos prontos em assets/models/"
echo "   Agora compile com: cargo build --release"
