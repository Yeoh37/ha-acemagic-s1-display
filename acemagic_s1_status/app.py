import os, time, json, struct, glob
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import psutil

WIDTH, HEIGHT = 320, 170
FONT_BOLD = "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"
FONT = "/usr/share/fonts/dejavu/DejaVuSans.ttf"


def options():
    try:
        with open('/data/options.json','r') as f:
            return json.load(f)
    except Exception:
        return {}


def rgb565_le(img):
    img = img.convert('RGB')
    out = bytearray()
    for r, g, b in img.getdata():
        v = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
        out.append(v & 0xFF)
        out.append((v >> 8) & 0xFF)
    return bytes(out)


def rgb565_be(img):
    img = img.convert('RGB')
    out = bytearray()
    for r, g, b in img.getdata():
        v = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
        out.append((v >> 8) & 0xFF)
        out.append(v & 0xFF)
    return bytes(out)


def make_img():
    cpu = psutil.cpu_percent(interval=0.2)
    mem = psutil.virtual_memory()
    used = mem.used / 1024**3
    total = mem.total / 1024**3
    img = Image.new('RGB', (WIDTH, HEIGHT), (0,0,0))
    d = ImageDraw.Draw(img)
    f1 = ImageFont.truetype(FONT_BOLD, 28)
    f2 = ImageFont.truetype(FONT_BOLD, 23)
    f3 = ImageFont.truetype(FONT, 18)
    d.text((16, 16), 'HOME ASSISTANT', fill=(0,255,80), font=f1)
    d.text((102, 58), 'OK', fill=(0,255,80), font=f2)
    d.text((45, 88), 'EN FONCTIONNEMENT', fill=(230,230,230), font=f3)
    d.text((30, 118), f'CPU {cpu:.0f} %', fill=(210,210,210), font=f3)
    d.text((160, 118), f'RAM {used:.1f}/{total:.0f} Go', fill=(210,210,210), font=f3)
    d.text((119, 145), datetime.now().strftime('%H:%M:%S'), fill=(120,180,255), font=f3)
    return img


def write_all(fd, data):
    os.write(fd, data)
    time.sleep(0.002)


def pad(data, size):
    if len(data) >= size:
        return data[:size]
    return data + bytes(size-len(data))


def send_ht32(fd, payload, report_prefix=False, endian='le'):
    # ACEMAGIC/HT32 style: 4104 byte HID writes, 8 byte header + 4096 data.
    # Several firmwares require the report id byte at the beginning, others do not.
    chunk_size = 4096
    total = (len(payload) + chunk_size - 1) // chunk_size
    for idx in range(total):
        chunk = payload[idx*chunk_size:(idx+1)*chunk_size]
        # Try the most common header variants used by S1 reverse engineered projects.
        header = bytes([0x55, 0xA3, idx & 0xff, (idx >> 8) & 0xff, total & 0xff, 0x00, len(chunk) & 0xff, (len(chunk)>>8)&0xff])
        pkt = header + pad(chunk, chunk_size)
        if report_prefix:
            pkt = b'\x00' + pkt
        write_all(fd, pkt)


def send_init(fd, mode):
    sequences = []
    # Basic wake/orientation sequences seen on HT32 panels.
    sequences.append([b'\x55\xA1\x01\x00\x00\x00\x00\x00', b'\x55\xA1\x02\x00\x00\x00\x00\x00'])
    sequences.append([b'\x55\xF1\x01\x00\x00\x00\x00\x00', b'\x55\xF2\x01\x00\x00\x00\x00\x00'])
    sequences.append([b'\x00\x55\xA1\x01\x00\x00\x00\x00\x00', b'\x00\x55\xA1\x02\x00\x00\x00\x00\x00'])
    for seq in sequences:
        for cmd in seq:
            try:
                write_all(fd, pad(cmd, 64))
            except Exception as e:
                print('Init warning:', e, flush=True)


def main():
    opt = options()
    dev = opt.get('hidraw_device', '/dev/hidraw1')
    refresh = int(opt.get('refresh_seconds', 10))
    mode = opt.get('packet_mode', 'ht32_auto')
    print('ACEMAGIC S1 Status v1.0.7', flush=True)
    print('HID disponibles:', ', '.join(glob.glob('/dev/hidraw*')), flush=True)
    print(f'Device={dev}, refresh={refresh}, mode={mode}', flush=True)
    while True:
        try:
            fd = os.open(dev, os.O_RDWR | os.O_SYNC)
            img = make_img()
            payloads = [('le', rgb565_le(img)), ('be', rgb565_be(img))]
            send_init(fd, mode)
            for name, payload in payloads:
                if mode in ('ht32_auto','ht32_a3','ht32_f1f2_a3'):
                    print(f'Envoi HT32 endian={name} sans report id', flush=True)
                    send_ht32(fd, payload, report_prefix=False, endian=name)
                    time.sleep(0.25)
                    print(f'Envoi HT32 endian={name} avec report id', flush=True)
                    send_ht32(fd, payload, report_prefix=True, endian=name)
            os.close(fd)
            print('Cycle envoye', flush=True)
        except Exception as e:
            print('Erreur:', repr(e), flush=True)
        time.sleep(refresh)

if __name__ == '__main__':
    main()
