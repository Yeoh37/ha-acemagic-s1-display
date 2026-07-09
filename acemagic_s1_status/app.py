import glob
import json
import os
import struct
import time
from datetime import datetime

import psutil
from PIL import Image, ImageDraw, ImageFont

WIDTH = 320
HEIGHT = 170
VID_HEX = "04d9"
PID_HEX = "fd01"

FONT_BOLD = "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"
FONT_REG = "/usr/share/fonts/dejavu/DejaVuSans.ttf"


def load_options():
    options = {"refresh_seconds": 10, "device_path": "auto", "rotate": "0"}
    try:
        with open("/data/options.json", "r", encoding="utf-8") as f:
            options.update(json.load(f))
    except Exception as e:
        print(f"Options par defaut utilisees: {e}")
    return options


def find_hidraw_devices():
    found = []
    for path in sorted(glob.glob("/dev/hidraw*")):
        name = os.path.basename(path)
        sys_nodes = glob.glob(f"/sys/class/hidraw/{name}/device")
        for node in sys_nodes:
            uevent_path = os.path.join(node, "uevent")
            try:
                with open(uevent_path, "r", encoding="utf-8", errors="ignore") as f:
                    data = f.read().lower()
                if VID_HEX in data and PID_HEX in data:
                    found.append(path)
            except Exception:
                pass
    return found


def make_status_image(rotate=0):
    cpu = psutil.cpu_percent(interval=0.3)
    vm = psutil.virtual_memory()
    used_gb = vm.used / (1024 ** 3)
    total_gb = vm.total / (1024 ** 3)

    img = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
    draw = ImageDraw.Draw(img)
    big = ImageFont.truetype(FONT_BOLD, 28)
    med = ImageFont.truetype(FONT_BOLD, 22)
    small = ImageFont.truetype(FONT_REG, 18)
    tiny = ImageFont.truetype(FONT_REG, 15)

    draw.rounded_rectangle((6, 6, WIDTH - 6, HEIGHT - 6), radius=12, outline=(0, 130, 60), width=2)
    draw.text((25, 20), "HOME ASSISTANT", fill=(0, 255, 90), font=big)
    draw.text((118, 58), "OK", fill=(0, 255, 90), font=med)
    draw.text((60, 84), "EN FONCTIONNEMENT", fill=(210, 255, 220), font=tiny)
    draw.text((34, 112), f"CPU  {cpu:4.0f} %", fill=(235, 235, 235), font=small)
    draw.text((34, 138), f"RAM  {used_gb:.1f} / {total_gb:.0f} Go", fill=(235, 235, 235), font=small)
    draw.text((225, 138), datetime.now().strftime("%H:%M"), fill=(150, 200, 255), font=small)

    if rotate:
        img = img.rotate(int(rotate), expand=True)
        img = img.resize((WIDTH, HEIGHT))
    return img


def rgb565_le(img):
    img = img.convert("RGB")
    out = bytearray()
    for r, g, b in img.getdata():
        value = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
        out.append(value & 0xFF)
        out.append((value >> 8) & 0xFF)
    return bytes(out)


def rgb565_be(img):
    img = img.convert("RGB")
    out = bytearray()
    for r, g, b in img.getdata():
        value = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
        out.append((value >> 8) & 0xFF)
        out.append(value & 0xFF)
    return bytes(out)


def write_packets(path, payload, mode):
    # Plusieurs firmwares du S1 existent. Ces modes permettent de tester sans modifier l'add-on.
    # Le plus courant pour les ecrans HID est un envoi en report de 64 octets.
    with open(path, "wb", buffering=0) as dev:
        if mode == "raw64":
            for i in range(0, len(payload), 63):
                chunk = payload[i:i+63]
                dev.write(bytes([0x00]) + chunk + bytes(63 - len(chunk)))
        elif mode == "magic55_64":
            total = (len(payload) + 55) // 56
            for idx in range(total):
                chunk = payload[idx*56:(idx+1)*56]
                header = bytes([0x00, 0x55, 0xA3, idx & 0xFF, (idx >> 8) & 0xFF, total & 0xFF, (total >> 8) & 0xFF, len(chunk)])
                dev.write(header + chunk + bytes(64 - len(header) - len(chunk)))
        elif mode == "magic55_4096":
            total = (len(payload) + 4095) // 4096
            for idx in range(total):
                chunk = payload[idx*4096:(idx+1)*4096]
                header = bytes([0x00, 0x55, 0xA3, idx & 0xFF, total & 0xFF, len(chunk) & 0xFF, (len(chunk) >> 8) & 0xFF, 0x00])
                dev.write(header + chunk)
        else:
            raise ValueError(f"Mode inconnu: {mode}")


def send_image(path, img):
    candidates = [
        ("rgb565_le", rgb565_le(img)),
        ("rgb565_be", rgb565_be(img)),
    ]
    packet_modes = ["magic55_64", "raw64", "magic55_4096"]

    last_error = None
    for fmt, payload in candidates:
        for mode in packet_modes:
            try:
                print(f"Tentative envoi: device={path} format={fmt} mode={mode} taille={len(payload)}")
                write_packets(path, payload, mode)
                print("Envoi termine sans erreur d'ecriture")
                return True
            except Exception as e:
                last_error = e
                print(f"Echec {fmt}/{mode}: {e}")
    print(f"Aucun mode d'envoi n'a fonctionne. Derniere erreur: {last_error}")
    return False


def main():
    options = load_options()
    refresh = max(2, int(options.get("refresh_seconds", 10)))
    configured_path = str(options.get("device_path", "auto"))
    rotate = int(options.get("rotate", 0))

    print(f"Rafraichissement: {refresh} secondes")
    print(f"Chemin configure: {configured_path}")

    while True:
        if configured_path != "auto":
            devices = [configured_path]
        else:
            devices = find_hidraw_devices()
            if not devices:
                devices = sorted(glob.glob("/dev/hidraw*"))

        print(f"Peripheriques candidats: {devices}")
        img = make_status_image(rotate=rotate)

        ok = False
        for dev in devices:
            ok = send_image(dev, img)
            if ok:
                break

        if ok:
            print("Mise a jour ecran demandee")
        else:
            print("Ecran non mis a jour. Voir les erreurs ci-dessus.")

        time.sleep(refresh)


if __name__ == "__main__":
    main()
