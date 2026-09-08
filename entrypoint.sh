#!/bin/sh
set -e

# Graceful cleanup background processes on exit
trap 'kill $(jobs -p) 2>/dev/null' EXIT INT TERM

echo "🚀 Starting API & Dashboard Server on port 8765..."
python dashboard.py --serve --port 8765 &

echo "🤖 Starting Main Trading Bot..."
exec python main.py --yes
