#!/bin/sh
set -e

echo "🚀 Starting API & Dashboard Server on port 8765..."
python dashboard.py --serve --port 8765 &

echo "🤖 Starting Main Trading Bot..."
exec python main.py --live --yes
