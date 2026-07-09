import os, time, json, glob, math, subprocess
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import psutil

VID = 0x04D9
PID = 0xFD01
WIDTH, HEIGHT = 320, 170
FONT_BOLD = "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"
FONT = "/usr/share/fonts/dejavu/DejaVuSans.ttf"


def read_options():
    try:
        with open('/data/options.json','r') as f:
            return json.load(f)
    except Exception:
        return {}


def log(msg):
    print(msg, flush=True)


def make_img():
    cpu = psutil.cpu_percent(interval=0.2)
    mem = psutil.virtual_memory()
    used = mem.used / 1024**3
    total = mem.total / 1024**3
    img = Image.new('RGB', (WIDTH, HEIGHT), (0,0,0))
    d = ImageDraw.Draw(img)
    f1 = ImageFont.truetype(FONT_BOLD, 28)
    f2 = ImageFont.truetype(FONT_BOLD, 24)
    f3 = ImageFont.truetype(FONT, 18)
    d.text((16, 16), 'HOME ASSISTANT', fill=(0,255,80), font=f1)
    d.text((103, 58), 'OK', fill=(0,255,80), font=f2)
    d.text((45, 88), 'EN FONCTIONNEMENT', fill=(230,230,230), font=f3)
    d.text((30, 118), f'CPU {cpu:.0f} %', fill=(220,220,220), font=f3)
    d.text((160, 118), f'RAM {used:.1f}/{total:.0f} Go', fill=(220,220,220), font=f3)
    d.text((119, 145), datetime.now().strftime('%H:%M:%S'), fill=(120,180,255), font=f3)
    return img


def rgb565(img, endian='le'):
    img = img.convert('RGB')
    out = bytearray()
    for r,g,b in img.getdata():
        v = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
        if endian == 'le':
            out.append(v & 0xFF); out.append((v >> 8) & 0xFF)
        else:
            out.append((v >> 8) & 0xFF); out.append(v & 0xFF)
    return bytes(out)


def pad(data, size):
    return data[:size] if len(data) >= size else data + bytes(size-len(data))


def packets(payload, with_report_id=False):
    chunk_size = 4096
    total = math.ceil(len(payload) / chunk_size)
    for idx in range(total):
        chunk = payload[idx*chunk_size:(idx+1)*chunk_size]
        header = bytes([0x55, 0xA3, idx & 0xff, (idx >> 8) & 0xff, total & 0xff, 0x00, len(chunk) & 0xff, (len(chunk)>>8)&0xff])
        pkt = header + pad(chunk, chunk_size)
        if with_report_id:
            pkt = b'\x00' + pkt
        yield pkt


def init_packets(with_report_id=False):
    cmds = [
        b'\x55\xA1\x01\x00\x00\x00\x00\x00',
        b'\x55\xA1\x02\x00\x00\x00\x00\x00',
        b'\x55\xF1\x01\x00\x00\x00\x00\x00',
        b'\x55\xF2\x01\x00\x00\x00\x00\x00',
    ]
    for c in cmds:
        p = pad(c, 64)
        if with_report_id:
            p = b'\x00' + p
        yield p


class HidrawWriter:
    def __init__(self, dev):
        self.dev = dev
        self.fd = os.open(dev, os.O_RDWR | os.O_SYNC)
        log(f'HIDRAW ouvert: {dev}')
    def write(self, data):
        os.write(self.fd, data)
        time.sleep(0.002)
    def close(self):
        os.close(self.fd)


class PyUsbWriter:
    def __init__(self):
        import usb.core, usb.util
        self.usb = usb
        self.dev = usb.core.find(idVendor=VID, idProduct=PID)
        if self.dev is None:
            raise RuntimeError('USB 04D9:FD01 introuvable')
        log('PyUSB: device trouve')
        try:
            self.dev.set_configuration()
            log('PyUSB: configuration OK')
        except Exception as e:
            log(f'PyUSB set_configuration ignore: {e!r}')
        for iface in (0,1):
            try:
                if self.dev.is_kernel_driver_active(iface):
                    self.dev.detach_kernel_driver(iface)
                    log(f'PyUSB: kernel driver detache interface {iface}')
            except Exception as e:
                log(f'PyUSB detach interface {iface} ignore: {e!r}')
        self.endpoint = 0x02
    def write(self, data):
        self.dev.write(self.endpoint, data, timeout=3000)
        time.sleep(0.002)
    def close(self):
        try:
            self.usb.util.dispose_resources(self.dev)
        except Exception:
            pass


class Libusb1Writer:
    def __init__(self):
        import usb1
        self.usb1 = usb1
        self.ctx = usb1.USBContext()
        log('libusb1: recherche 04D9:FD01')
        self.handle = self.ctx.openByVendorIDAndProductID(VID, PID, skip_on_error=True)
        if self.handle is None:
            raise RuntimeError('libusb1: impossible ouvrir 04D9:FD01')
        try:
            self.handle.setConfiguration(1)
            log('libusb1: configuration 1 OK')
        except Exception as e:
            log(f'libusb1 setConfiguration ignore: {e!r}')
        for iface in (0,1):
            try:
                self.handle.detachKernelDriver(iface)
                log(f'libusb1: kernel driver detache interface {iface}')
            except Exception as e:
                log(f'libusb1 detach interface {iface} ignore: {e!r}')
        self.handle.claimInterface(1)
        log('libusb1: interface 1 claim OK')
    def write(self, data):
        self.handle.bulkWrite(0x02, data, timeout=3000)
        time.sleep(0.002)
    def close(self):
        try:
            self.handle.releaseInterface(1)
            self.handle.close()
        except Exception:
            pass
        self.ctx.close()


def send_cycle(writer, img, mode):
    payloads = [('le', rgb565(img, 'le')), ('be', rgb565(img, 'be'))]
    for report in (False, True):
        for p in init_packets(report):
            try:
                writer.write(p)
            except Exception as e:
                log(f'Init warning report={report}: {e!r}')
    for endian, payload in payloads:
        for report in (False, True):
            log(f'Envoi image endian={endian}, report_id={report}')
            count = 0
            for p in packets(payload, report):
                writer.write(p)
                count += 1
            log(f'{count} paquets envoyes')
            time.sleep(0.2)


def diagnostic():
    log('--- diagnostic ---')
    for cmd in [['lsusb'], ['lsusb','-d','04d9:fd01','-v']]:
        try:
            out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True, timeout=5)
            log('$ ' + ' '.join(cmd) + '\n' + out[:4000])
        except Exception as e:
            log(f'Erreur diagnostic {cmd}: {e!r}')
    log('hidraw: ' + ', '.join(glob.glob('/dev/hidraw*')))
    log('usb bus: ' + ', '.join(glob.glob('/dev/bus/usb/*/*')))


def build_writer(backend, hidraw_dev):
    errors = []
    order = []
    if backend == 'auto':
        order = ['libusb', 'pyusb', 'hidraw']
    else:
        order = [backend]
    for b in order:
        try:
            log(f'Tentative backend: {b}')
            if b == 'libusb':
                return Libusb1Writer(), b
            if b == 'pyusb':
                return PyUsbWriter(), b
            if b == 'hidraw':
                return HidrawWriter(hidraw_dev), b
        except Exception as e:
            msg = f'{b}: {e!r}'
            errors.append(msg)
            log('Echec ' + msg)
    raise RuntimeError('Aucun backend utilisable: ' + ' | '.join(errors))


def main():
    opt = read_options()
    refresh = int(opt.get('refresh_seconds', 10))
    backend = opt.get('backend', 'auto')
    hidraw_dev = opt.get('hidraw_device', '/dev/hidraw1')
    packet_mode = opt.get('packet_mode', 'ht32_auto')
    log('ACEMAGIC S1 Status v1.0.8')
    log(f'backend={backend}, hidraw={hidraw_dev}, refresh={refresh}, packet_mode={packet_mode}')
    diagnostic()
    if backend == 'diagnostic':
        while True:
            time.sleep(3600)
    while True:
        writer = None
        try:
            img = make_img()
            writer, used_backend = build_writer(backend, hidraw_dev)
            log(f'Backend actif: {used_backend}')
            send_cycle(writer, img, packet_mode)
            log('Cycle envoye')
        except Exception as e:
            log(f'Erreur cycle: {e!r}')
        finally:
            try:
                if writer:
                    writer.close()
            except Exception:
                pass
        time.sleep(refresh)


if __name__ == '__main__':
    main()
