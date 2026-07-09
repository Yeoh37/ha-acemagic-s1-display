import json
import os
import time
import glob
import math
import subprocess
from datetime import datetime

import psutil
from PIL import Image, ImageDraw, ImageFont

VID = 0x04D9
PID = 0xFD01
WIDTH = 320
HEIGHT = 170
IMG_BYTES = WIDTH * HEIGHT * 2
ENDPOINT_OUT = 0x02
INTERFACE = 1
CHUNK_PAYLOAD = 4096

FONT_BOLD = "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"
FONT_REG = "/usr/share/fonts/dejavu/DejaVuSans.ttf"


def load_options():
    defaults = {
        "refresh_seconds": 10,
        "backend": "auto",
        "hidraw_device": "/dev/hidraw1",
        "orientation": "landscape",
        "unbind_usbhid": True,
    }
    try:
        with open("/data/options.json", "r") as f:
            defaults.update(json.load(f))
    except Exception as e:
        print(f"Options par defaut utilisees: {e}", flush=True)
    return defaults


def make_image():
    cpu = psutil.cpu_percent(interval=0.2)
    mem = psutil.virtual_memory()
    used = mem.used / (1024 ** 3)
    total = mem.total / (1024 ** 3)

    img = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
    d = ImageDraw.Draw(img)
    fb = ImageFont.truetype(FONT_BOLD, 28)
    fm = ImageFont.truetype(FONT_BOLD, 22)
    fs = ImageFont.truetype(FONT_REG, 18)

    d.text((18, 16), "HOME ASSISTANT", fill=(0, 255, 80), font=fb)
    d.text((92, 54), "OK", fill=(0, 255, 80), font=fb)
    d.text((50, 83), "EN FONCTIONNEMENT", fill=(0, 255, 80), font=fm)
    d.text((30, 120), f"CPU {cpu:.0f}%", fill=(230, 230, 230), font=fs)
    d.text((145, 120), f"RAM {used:.1f}/{total:.0f} Go", fill=(230, 230, 230), font=fs)
    d.text((220, 145), datetime.now().strftime("%H:%M"), fill=(160, 190, 255), font=fs)
    return img


def rgb565_le(img):
    out = bytearray()
    for r, g, b in img.convert("RGB").getdata():
        v = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
        out.append(v & 0xFF)
        out.append((v >> 8) & 0xFF)
    return bytes(out)


def find_usb_sysfs():
    matches = []
    for devdir in glob.glob("/sys/bus/usb/devices/*"):
        try:
            with open(os.path.join(devdir, "idVendor")) as f:
                vid = f.read().strip().lower()
            with open(os.path.join(devdir, "idProduct")) as f:
                pid = f.read().strip().lower()
            if vid == "04d9" and pid == "fd01":
                matches.append(devdir)
        except Exception:
            pass
    return matches


def unbind_usbhid():
    print("Recherche sysfs USB 04d9:fd01", flush=True)
    devdirs = find_usb_sysfs()
    if not devdirs:
        print("Aucun peripherique sysfs 04d9:fd01 trouve", flush=True)
        return False

    ok = False
    for devdir in devdirs:
        base = os.path.basename(devdir)
        print(f"Peripherique USB trouve: {base}", flush=True)
        for iface in glob.glob(os.path.join(devdir, f"{base}:1.*")):
            iface_name = os.path.basename(iface)
            driver_link = os.path.join(iface, "driver")
            if os.path.islink(driver_link):
                driver = os.path.basename(os.readlink(driver_link))
            else:
                driver = "none"
            print(f"Interface {iface_name}, driver={driver}", flush=True)
            if iface_name.endswith(".1") or iface_name.endswith(":1.1") or iface_name.split(":")[-1].endswith(".1"):
                for drv in ("usbhid", "hid-generic"):
                    unbind_path = f"/sys/bus/usb/drivers/{drv}/unbind"
                    if os.path.exists(unbind_path):
                        try:
                            with open(unbind_path, "w") as f:
                                f.write(iface_name)
                            print(f"unbind OK: {iface_name} depuis {drv}", flush=True)
                            ok = True
                        except Exception as e:
                            print(f"unbind {drv} echoue pour {iface_name}: {e}", flush=True)
    return ok


class HidrawWriter:
    def __init__(self, path):
        self.path = path
        self.fd = os.open(path, os.O_RDWR | os.O_SYNC)
        print(f"HIDRAW ouvert: {path}", flush=True)

    def write_packet(self, p):
        os.write(self.fd, p)

    def send_image(self, img):
        data = rgb565_le(img)
        # Plusieurs variantes connues/possibles, en gardant la version stable.
        for endian in ("le",):
            total = math.ceil(len(data) / CHUNK_PAYLOAD)
            # init candidates
            for init in (bytes([0x55,0xA1,0x01,0x00,0x00,0x00,0x00,0x00]), bytes([0x55,0xA1,0xF1,0,0,0,0,0]), bytes([0x55,0xA1,0xF2,0,0,0,0,0])):
                try:
                    self.write_packet(init.ljust(64, b"\x00"))
                    time.sleep(0.02)
                except Exception as e:
                    print(f"Init hidraw ignoree: {e}", flush=True)
            for i in range(total):
                chunk = data[i*CHUNK_PAYLOAD:(i+1)*CHUNK_PAYLOAD]
                header = bytes([0x55, 0xA3, i & 0xFF, total & 0xFF, len(chunk) & 0xFF, (len(chunk)>>8)&0xFF, 0, 0])
                packet = header + chunk
                self.write_packet(packet)
        print("Image envoyee via hidraw", flush=True)


class LibusbWriter:
    def __init__(self):
        import usb.core, usb.util
        self.usb = usb
        self.dev = usb.core.find(idVendor=VID, idProduct=PID)
        if self.dev is None:
            raise RuntimeError("USB 04d9:fd01 introuvable")
        print("USB 04d9:fd01 trouve", flush=True)
        try:
            if self.dev.is_kernel_driver_active(INTERFACE):
                print("Kernel driver actif sur interface 1, detach...", flush=True)
                self.dev.detach_kernel_driver(INTERFACE)
        except Exception as e:
            print(f"detach_kernel_driver info: {e}", flush=True)
        try:
            self.dev.set_configuration()
            print("set_configuration OK", flush=True)
        except Exception as e:
            print(f"set_configuration info: {e}", flush=True)
        usb.util.claim_interface(self.dev, INTERFACE)
        print("Interface USB 1 claim OK", flush=True)

    def send_image(self, img):
        data = rgb565_le(img)
        total = math.ceil(len(data) / CHUNK_PAYLOAD)
        # sequence candidate
        for p in (bytes([0x55,0xA1,0xF1,0,0,0,0,0]), bytes([0x55,0xA1,0xF2,0,0,0,0,0])):
            self.dev.write(ENDPOINT_OUT, p.ljust(4104, b"\x00"), timeout=3000)
            time.sleep(0.02)
        for i in range(total):
            chunk = data[i*CHUNK_PAYLOAD:(i+1)*CHUNK_PAYLOAD]
            header = bytes([0x55, 0xA3, i & 0xFF, total & 0xFF, len(chunk) & 0xFF, (len(chunk)>>8)&0xFF, 0, 0])
            self.dev.write(ENDPOINT_OUT, header + chunk, timeout=3000)
        print("Image envoyee via libusb", flush=True)


def main():
    opt = load_options()
    print("ACEMAGIC S1 Status v1.1.0", flush=True)
    print(f"Options: {opt}", flush=True)

    if opt.get("unbind_usbhid", True):
        unbind_usbhid()
        time.sleep(0.5)

    backend = opt.get("backend", "auto")
    writer = None
    if backend in ("auto", "libusb"):
        try:
            writer = LibusbWriter()
        except Exception as e:
            print(f"libusb indisponible: {e}", flush=True)
            if backend == "libusb":
                raise
    if writer is None:
        writer = HidrawWriter(opt.get("hidraw_device", "/dev/hidraw1"))

    refresh = int(opt.get("refresh_seconds", 10))
    while True:
        try:
            writer.send_image(make_image())
        except Exception as e:
            print(f"Erreur envoi image: {e}", flush=True)
        time.sleep(refresh)


if __name__ == "__main__":
    main()
