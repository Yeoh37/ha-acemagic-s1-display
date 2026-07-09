#!/usr/bin/env bash
set -e

echo "ACEMAGIC S1 Status - demarrage"
echo "Peripheriques HID disponibles:"
ls -la /dev/hidraw* 2>/dev/null || true
python3 /app.py
