#!/usr/bin/env bash
# Installation en UNE commande : ./install.sh   (Linux x64, ~6 Go disque, 0 € : tout tourne en local sur le CPU)
set -euo pipefail
cd "$(dirname "$0")"
command -v ffmpeg >/dev/null || { echo "Installez ffmpeg (sudo apt install ffmpeg) puis relancez."; exit 1; }
command -v node >/dev/null || echo "Conseil : installez node (YouTube ne donne la vidéo qu'avec un runtime JS)."
python3 -m venv .venv && .venv/bin/pip install -q --upgrade pip && .venv/bin/pip install -q -r requirements.txt
mkdir -p llm models && cd llm
LLAMA=b12244
[ -x llama-$LLAMA/llama-server ] || { curl -sL -o llama.tgz "https://github.com/ggml-org/llama.cpp/releases/download/$LLAMA/llama-$LLAMA-bin-ubuntu-x64.tar.gz" && tar xzf llama.tgz && rm llama.tgz; }
MODEL_URL=${CLIP_MODEL_URL:-https://huggingface.co/bartowski/Qwen2.5-7B-Instruct-GGUF/resolve/main/Qwen2.5-7B-Instruct-Q4_K_M.gguf}
[ -f model.gguf ] || curl -L -o model.gguf "$MODEL_URL"
[ -f blaze_face_short_range.tflite ] || curl -sL -o blaze_face_short_range.tflite https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/latest/blaze_face_short_range.tflite
echo "OK. Lancez : ./clip <lien YouTube ou fichier>   ou   ./clip --ui"
echo "Optionnel, non installé ici : pip install whisperx && ./clip <lien> --align whisperx"
