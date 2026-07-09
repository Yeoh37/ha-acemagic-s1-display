import json
import os
import time
from datetime import datetime
from pathlib import Path

import psutil
import usb1
from PIL import Image, ImageDraw, ImageFont

WIDTH = 320
HEIGHT = 170
PACKET_SIZE = 4104
PAYLOAD_SIZE = 4096
VID = 0x04D9
PID = 0xFD01
INTERFACE = 1
ENDPOINT_OUT = 0x02

FONT_BOLD = "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"
FONT_REG = "/usr/share/fonts/dejavu/DejaVuSans.ttf"


def load_options():
    defaults = {
        "refresh_seconds": 2,
        "hidraw_device": "/dev/hidraw1",
        "orientation": "landscape",
        "backend": "libusb1",
    }
    try:
        with open("/data/options.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        defaults.update(data)
    except Exception as exc:
        print(f"Options par defaut utilisees: {exc}", flush=True)
    return defaults


def packet(header, payload=b""):
    data = bytes(header) + bytes(payload)
    if len(data) > PACKET_SIZE:
        raise ValueError(f"Paquet trop grand: {len(data)}")
    return data + bytes(PACKET_SIZE - len(data))


def rgb565_be(image):
    image = image.convert("RGB")
    out = bytearray(WIDTH * HEIGHT * 2)
    pos = 0
    for r, g, b in image.getdata():
        value = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
        # Documentation communautaire: RGB565 big-endian.
        out[pos] = (value >> 8) & 0xFF
        out[pos + 1] = value & 0xFF
        pos += 2
    return bytes(out)


def rgb565_le(image):
    image = image.convert("RGB")
    out = bytearray(WIDTH * HEIGHT * 2)
    pos = 0
    for r, g, b in image.getdata():
        value = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
        out[pos] = value & 0xFF
        out[pos + 1] = (value >> 8) & 0xFF
        pos += 2
    return bytes(out)


def make_image():
    cpu = psutil.cpu_percent(interval=0.25)
    vm = psutil.virtual_memory()
    used_gb = vm.used / (1024 ** 3)
    total_gb = vm.total / (1024 ** 3)

    img = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
    draw = ImageDraw.Draw(img)

    big = ImageFont.truetype(FONT_BOLD, 28)
    mid = ImageFont.truetype(FONT_BOLD, 24)
    small = ImageFont.truetype(FONT_REG, 18)
    tiny = ImageFont.truetype(FONT_REG, 14)

    green = (0, 255, 80)
    white = (235, 235, 235)
    blue = (110, 180, 255)
    gray = (150, 150, 150)

    draw.rectangle((0, 0, WIDTH - 1, HEIGHT - 1), outline=(0, 80, 30))
    draw.text((18, 16), "HOME ASSISTANT", fill=green, font=big)
    draw.text((128, 54), "OK", fill=green, font=mid)
    draw.text((45, 84), "EN FONCTIONNEMENT", fill=white, font=small)
    draw.text((28, 118), f"CPU {cpu:>3.0f} %", fill=white, font=small)
    draw.text((28, 142), f"RAM {used_gb:.1f}/{total_gb:.0f} Go", fill=white, font=small)
    draw.text((224, 142), datetime.now().strftime("%H:%M"), fill=blue, font=small)
    draw.text((230, 118), "S1 LCD", fill=gray, font=tiny)
    return img


class LibUsb1Writer:
    def __init__(self):
        self.ctx = usb1.USBContext()
        print("Recherche USB 04D9:FD01", flush=True)
        self.handle = self.ctx.openByVendorIDAndProductID(VID, PID)
        if self.handle is None:
            raise RuntimeError("USB 04D9:FD01 introuvable")
        try:
            self.handle.detachKernelDriver(INTERFACE)
            print("Kernel driver detache de l'interface 1", flush=True)
        except Exception as exc:
            print(f"Info detach interface 1: {exc}", flush=True)
        self.handle.claimInterface(INTERFACE)
        print("Interface USB 1 revendiquee, endpoint OUT 0x02", flush=True)

    def write(self, data):
        # Custom HID: pas de report ID, paquet fixe 4104 octets.
        self.handle.interruptWrite(ENDPOINT_OUT, bytes(data), timeout=3000)

    def close(self):
        try:
            self.handle.releaseInterface(INTERFACE)
        except Exception:
            pass
        try:
            self.handle.close()
        except Exception:
            pass
        try:
            self.ctx.close()
        except Exception:
            pass


class HidrawWriter:
    def __init__(self, device):
        self.device = device
        if not Path(device).exists():
            raise FileNotFoundError(device)
        print(f"HIDRAW utilise: {device}", flush=True)

    def write(self, data):
        with open(self.device, "wb", buffering=0) as f:
            f.write(data)

    def close(self):
        pass


def send_orientation(writer, orientation):
    if orientation == "auto":
        orientation = "landscape"
    value = 0x01 if orientation == "landscape" else 0x02
    writer.write(packet([0x55, 0xA1, 0xF1, value]))
    print(f"Orientation envoyee: {orientation}", flush=True)


def send_heartbeat(writer):
    now = datetime.now()
    writer.write(packet([0x55, 0xA1, 0xF2, now.hour, now.minute, now.second]))


def send_image(writer, image, endian="be"):
    data = rgb565_be(image) if endian == "be" else rgb565_le(image)
    total_chunks = (len(data) + PAYLOAD_SIZE - 1) // PAYLOAD_SIZE
    offset = 0
    seq = 0
    while offset < len(data):
        chunk = data[offset:offset + PAYLOAD_SIZE]
        # Format simple documente par les projets communautaires: 55 A3 + index + total + longueur + padding.
        header = [
            0x55, 0xA3,
            seq & 0xFF,
            total_chunks & 0xFF,
            len(chunk) & 0xFF,
            (len(chunk) >> 8) & 0xFF,
            0x00,
            0x00,
        ]
        writer.write(packet(header, chunk))
        offset += len(chunk)
        seq += 1
        time.sleep(0.003)


def send_image_alt(writer, image, endian="be"):
    data = rgb565_be(image) if endian == "be" else rgb565_le(image)
    offset = 0
    seq = 1
    while offset < len(data):
        chunk = data[offset:offset + PAYLOAD_SIZE]
        subcmd = 0xF0 if offset == 0 else (0xF2 if offset + PAYLOAD_SIZE >= len(data) else 0xF1)
        off16 = offset & 0xFFFF
        blocks = (len(chunk) + 255) // 256
        header = [0x55, 0xA3, subcmd, seq & 0xFF, off16 & 0xFF, (off16 >> 8) & 0xFF, blocks & 0xFF, (blocks >> 8) & 0xFF]
        writer.write(packet(header, chunk))
        offset += len(chunk)
        seq += 1
        time.sleep(0.003)


def main():
    print("ACEMAGIC S1 Status - demarrage v1.0.5", flush=True)
    print("Peripheriques HID disponibles:", flush=True)
    os.system("ls -l /dev/hidraw* 2>/dev/null || true")

    opts = load_options()
    refresh = max(1, int(opts.get("refresh_seconds", 2)))
    orientation = opts.get("orientation", "landscape")
    backend = opts.get("backend", "libusb1")
    print(f"Backend: {backend}", flush=True)
    print(f"Rafraichissement: {refresh} s", flush=True)

    if backend == "hidraw":
        writer = HidrawWriter(opts.get("hidraw_device", "/dev/hidraw1"))
    else:
        writer = LibUsb1Writer()

    try:
        send_orientation(writer, orientation)
        time.sleep(0.2)
        while True:
            try:
                img = make_image()
                send_heartbeat(writer)
                # Les firmwares S1 ne reagissent pas tous au meme header: on envoie les deux variantes.
                send_image(writer, img, endian="be")
                time.sleep(0.1)
                send_image_alt(writer, img, endian="be")
                send_heartbeat(writer)
                print("Image envoyee au LCD", flush=True)
            except Exception as exc:
                print(f"Erreur LCD: {type(exc).__name__}: {exc}", flush=True)
            time.sleep(refresh)
    finally:
        writer.close()


if __name__ == "__main__":
    main()
