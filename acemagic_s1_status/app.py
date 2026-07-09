import json
import os
import time
from datetime import datetime
from pathlib import Path

import psutil
from PIL import Image, ImageDraw, ImageFont

WIDTH = 320
HEIGHT = 170
PACKET_SIZE = 4104
PAYLOAD_SIZE = 4096

FONT_BOLD = "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"
FONT_REG = "/usr/share/fonts/dejavu/DejaVuSans.ttf"


def load_options():
    defaults = {
        "refresh_seconds": 10,
        "hidraw_device": "auto",
        "orientation": "landscape",
    }
    try:
        with open("/data/options.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        defaults.update(data)
    except Exception as exc:
        print(f"Options par defaut utilisees: {exc}", flush=True)
    return defaults


def detect_hidraw(preferred):
    if preferred and preferred != "auto":
        if Path(preferred).exists():
            print(f"Peripherique HID configure: {preferred}", flush=True)
            return preferred
        print(f"Peripherique configure absent: {preferred}", flush=True)

    # Sur le S1, l'interface vendor-defined est generalement hidraw1.
    for dev in ["/dev/hidraw1", "/dev/hidraw0"]:
        if Path(dev).exists():
            print(f"Peripherique HID selectionne: {dev}", flush=True)
            return dev
    raise FileNotFoundError("Aucun /dev/hidraw0 ou /dev/hidraw1 trouve")


def packet(header, payload=b""):
    data = bytes(header) + bytes(payload)
    if len(data) > PACKET_SIZE:
        raise ValueError("Paquet HID trop grand")
    return data + bytes(PACKET_SIZE - len(data))


def write_packet(device_path, data):
    with open(device_path, "wb", buffering=0) as dev:
        dev.write(data)


def send_orientation(device_path, orientation):
    # 0x01 = landscape, 0x02 = portrait d'apres la doc reverse-engineered.
    value = 0x01 if orientation == "landscape" else 0x02
    write_packet(device_path, packet([0x55, 0xA1, 0xF1, value, 0x00, 0x00, 0x00, 0x00]))
    print(f"Orientation envoyee: {orientation}", flush=True)


def send_heartbeat(device_path):
    now = datetime.now()
    write_packet(device_path, packet([0x55, 0xA1, 0xF2, now.hour, now.minute, now.second, 0x00, 0x00]))


def rgb565_swapped(image):
    # Le LCD attend RGB565 avec endian swap.
    image = image.convert("RGB")
    out = bytearray(WIDTH * HEIGHT * 2)
    pos = 0
    for r, g, b in image.getdata():
        value = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
        # endian swap: octet bas puis octet haut
        out[pos] = value & 0xFF
        out[pos + 1] = (value >> 8) & 0xFF
        pos += 2
    return bytes(out)


def make_image():
    cpu = psutil.cpu_percent(interval=0.4)
    vm = psutil.virtual_memory()
    used_gb = vm.used / (1024 ** 3)
    total_gb = vm.total / (1024 ** 3)

    img = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
    draw = ImageDraw.Draw(img)

    big = ImageFont.truetype(FONT_BOLD, 28)
    mid = ImageFont.truetype(FONT_BOLD, 22)
    small = ImageFont.truetype(FONT_REG, 18)
    tiny = ImageFont.truetype(FONT_REG, 14)

    green = (0, 255, 80)
    white = (235, 235, 235)
    blue = (110, 180, 255)
    gray = (150, 150, 150)

    draw.rectangle((0, 0, WIDTH - 1, HEIGHT - 1), outline=(0, 80, 30))
    draw.text((18, 16), "HOME ASSISTANT", fill=green, font=big)
    draw.text((116, 55), "OK", fill=green, font=mid)
    draw.text((45, 82), "EN FONCTIONNEMENT", fill=white, font=small)

    draw.text((28, 116), f"CPU {cpu:>3.0f} %", fill=white, font=small)
    draw.text((28, 140), f"RAM {used_gb:.1f}/{total_gb:.0f} Go", fill=white, font=small)
    draw.text((224, 140), datetime.now().strftime("%H:%M"), fill=blue, font=small)
    draw.text((230, 116), "S1 LCD", fill=gray, font=tiny)

    return img


def redraw(device_path, image):
    data = rgb565_swapped(image)
    total = len(data)
    seq = 1
    offset = 0

    while offset < total:
        chunk = data[offset:offset + PAYLOAD_SIZE]
        if offset == 0:
            subcmd = 0xF0
        elif offset + PAYLOAD_SIZE >= total:
            subcmd = 0xF2
        else:
            subcmd = 0xF1

        off16 = offset & 0xFFFF
        length_words = len(chunk) // 256  # doc: 0x10 pour 4096, 0x09 pour 2304
        if len(chunk) % 256:
            length_words += 1

        header = [
            0x55, 0xA3, subcmd, seq & 0xFF,
            off16 & 0xFF, (off16 >> 8) & 0xFF,
            length_words & 0xFF, (length_words >> 8) & 0xFF,
        ]
        write_packet(device_path, packet(header, chunk))
        offset += len(chunk)
        seq += 1
        time.sleep(0.01)


def main():
    opts = load_options()
    refresh = max(2, int(opts.get("refresh_seconds", 10)))
    orientation = opts.get("orientation", "landscape")
    if orientation == "auto":
        orientation = "landscape"

    device = detect_hidraw(opts.get("hidraw_device", "auto"))
    print(f"Rafraichissement: {refresh} s", flush=True)

    try:
        send_orientation(device, orientation)
        time.sleep(0.2)
    except Exception as exc:
        print(f"Orientation non envoyee: {exc}", flush=True)

    while True:
        try:
            send_heartbeat(device)
            img = make_image()
            redraw(device, img)
            send_heartbeat(device)
            print("Image envoyee au LCD", flush=True)
        except Exception as exc:
            print(f"Erreur LCD: {exc}", flush=True)
        time.sleep(refresh)


if __name__ == "__main__":
    main()
