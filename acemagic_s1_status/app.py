import json
import os
import struct
import subprocess
import time
from datetime import datetime

import psutil
from PIL import Image, ImageDraw, ImageFont

WIDTH = 320
HEIGHT = 170
FONT_BIG = "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"
FONT_MED = "/usr/share/fonts/dejavu/DejaVuSans.ttf"


def load_options():
    default = {
        "refresh_seconds": 10,
        "hidraw_device": "/dev/hidraw1",
        "orientation": "landscape",
        "packet_mode": "ht32_auto",
    }
    try:
        with open("/data/options.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            default.update(data)
    except Exception as exc:
        print(f"Options par defaut utilisees: {exc}", flush=True)
    return default


def list_hidraw():
    try:
        out = subprocess.check_output("ls -l /dev/hidraw* 2>/dev/null || true", shell=True, text=True)
        print("Peripheriques HID disponibles:", flush=True)
        print(out.strip() or "aucun", flush=True)
    except Exception as exc:
        print(f"Impossible de lister hidraw: {exc}", flush=True)


def make_image():
    cpu = psutil.cpu_percent(interval=0.2)
    mem = psutil.virtual_memory()
    used = mem.used / (1024 ** 3)
    total = mem.total / (1024 ** 3)

    img = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
    draw = ImageDraw.Draw(img)
    font_big = ImageFont.truetype(FONT_BIG, 28)
    font_mid = ImageFont.truetype(FONT_BIG, 22)
    font_small = ImageFont.truetype(FONT_MED, 18)

    draw.text((22, 16), "HOME ASSISTANT", fill=(0, 255, 80), font=font_big)
    draw.text((108, 55), "OK", fill=(0, 255, 80), font=font_big)
    draw.text((52, 84), "EN FONCTIONNEMENT", fill=(0, 255, 80), font=font_mid)
    draw.text((28, 122), f"CPU {cpu:.0f}%", fill=(230, 230, 230), font=font_small)
    draw.text((130, 122), f"RAM {used:.1f}/{total:.0f} Go", fill=(230, 230, 230), font=font_small)
    draw.text((238, 146), datetime.now().strftime("%H:%M"), fill=(120, 180, 255), font=font_small)
    return img


def rgb565(img, endian="le"):
    img = img.convert("RGB")
    out = bytearray()
    for r, g, b in img.getdata():
        value = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
        if endian == "le":
            out.append(value & 0xFF)
            out.append((value >> 8) & 0xFF)
        else:
            out.append((value >> 8) & 0xFF)
            out.append(value & 0xFF)
    return bytes(out)


def write_packet(fd, payload):
    os.write(fd, payload)


def send_ht32_a3(device, img, endian="le", with_report_id=False):
    data = rgb565(img, endian=endian)
    chunk_size = 4096
    total = (len(data) + chunk_size - 1) // chunk_size

    with open(device, "wb", buffering=0) as f:
        fd = f.fileno()
        for index in range(total):
            chunk = data[index * chunk_size:(index + 1) * chunk_size]
            header = bytes([
                0x55, 0xA3,
                index & 0xFF,
                total & 0xFF,
                len(chunk) & 0xFF,
                (len(chunk) >> 8) & 0xFF,
                0x00,
                0x00,
            ])
            payload = header + chunk
            payload = payload.ljust(4104, b"\x00")
            if with_report_id:
                payload = b"\x00" + payload
            write_packet(fd, payload)
            time.sleep(0.002)


def send_f1f2_a3(device, img):
    with open(device, "wb", buffering=0) as f:
        fd = f.fileno()
        for cmd in (bytes([0x55, 0xA1, 0xF1]), bytes([0x55, 0xA1, 0xF2])):
            write_packet(fd, cmd.ljust(64, b"\x00"))
            time.sleep(0.05)
    send_ht32_a3(device, img, endian="le", with_report_id=False)


def send_image(device, img, mode):
    print(f"Envoi image vers {device}, mode={mode}", flush=True)
    if mode == "ht32_a3":
        send_ht32_a3(device, img, endian="le", with_report_id=False)
    elif mode == "ht32_f1f2_a3":
        send_f1f2_a3(device, img)
    elif mode == "diagnostic":
        for endian in ("le", "be"):
            for report in (False, True):
                print(f"Diagnostic endian={endian} report_id={report}", flush=True)
                send_ht32_a3(device, img, endian=endian, with_report_id=report)
                time.sleep(1)
    else:
        # ht32_auto
        send_f1f2_a3(device, img)
        time.sleep(0.5)
        send_ht32_a3(device, img, endian="le", with_report_id=True)
    print("Cycle envoye", flush=True)


def main():
    opts = load_options()
    refresh = int(opts.get("refresh_seconds", 10))
    device = opts.get("hidraw_device", "/dev/hidraw1")
    mode = opts.get("packet_mode", "ht32_auto")

    print("ACEMAGIC S1 Status v1.0.9", flush=True)
    list_hidraw()
    print(f"Device={device}, refresh={refresh}, mode={mode}", flush=True)

    if not os.path.exists(device):
        raise SystemExit(f"Peripherique introuvable: {device}")

    while True:
        try:
            img = make_image()
            send_image(device, img, mode)
        except Exception as exc:
            print(f"Erreur LCD: {exc}", flush=True)
        time.sleep(refresh)


if __name__ == "__main__":
    main()
