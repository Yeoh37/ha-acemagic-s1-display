#!/usr/bin/env bash
set -e

echo "ACEMAGIC S1 Status - demarrage"
echo "Peripheriques HID disponibles:"
ls -l /dev/hidraw* 2>/dev/null || true
echo "USB devices:"
lsusb || true
python3 /app.py
