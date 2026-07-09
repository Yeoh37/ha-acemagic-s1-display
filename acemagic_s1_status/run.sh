#!/usr/bin/env bash
set -e
echo "ACEMAGIC S1 Status - demarrage"
echo "HID disponibles:"
ls -l /dev/hidraw* 2>/dev/null || true
echo "USB bus disponibles:"
find /dev/bus/usb -type c -maxdepth 3 -exec ls -l {} \; 2>/dev/null || true
python3 /app.py
