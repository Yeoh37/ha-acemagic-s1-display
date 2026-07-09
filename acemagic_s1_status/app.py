import json, os, time, struct, glob, traceback
import psutil
from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 320, 170
FONT_BOLD = "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"
FONT_REG = "/usr/share/fonts/dejavu/DejaVuSans.ttf"


def opts():
    try:
        with open('/data/options.json') as f:
            return json.load(f)
    except Exception:
        return {}


def img_rgb565(img):
    img = img.convert('RGB')
    out = bytearray()
    for r,g,b in img.getdata():
        v = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
        out += bytes([(v >> 8) & 255, v & 255])
    return bytes(out)


def make_image(orientation='landscape'):
    cpu = psutil.cpu_percent(interval=0.2)
    mem = psutil.virtual_memory()
    img = Image.new('RGB', (WIDTH, HEIGHT), (0,0,0))
    d = ImageDraw.Draw(img)
    f1 = ImageFont.truetype(FONT_BOLD, 28)
    f2 = ImageFont.truetype(FONT_BOLD, 22)
    f3 = ImageFont.truetype(FONT_REG, 18)
    d.text((20, 16), 'HOME ASSISTANT', fill=(0,255,80), font=f1)
    d.text((112, 54), 'OK', fill=(0,255,80), font=f1)
    d.text((42, 88), 'EN FONCTIONNEMENT', fill=(0,200,255), font=f2)
    d.text((32, 124), f'CPU {cpu:.0f} %', fill=(230,230,230), font=f3)
    d.text((160, 124), f'RAM {mem.used/1024**3:.1f}/{mem.total/1024**3:.0f} Go', fill=(230,230,230), font=f3)
    if orientation == 'portrait':
        img = img.rotate(90, expand=True).resize((WIDTH, HEIGHT))
    return img


def write_packet(path, packet):
    with open(path, 'wb', buffering=0) as f:
        return f.write(packet)


def send_hid(path, image, mode='auto'):
    raw = img_rgb565(image)
    print(f'HIDRAW: {path}, mode={mode}, image={len(raw)} bytes', flush=True)

    # Variantes: certains pilotes attendent un report ID 0x00, d'autres non.
    modes = ['raw4104','report4105','short64'] if mode == 'auto' else [mode]

    for m in modes:
        try:
            print(f'Test mode {m}', flush=True)
            # init/orientation candidates
            init_packets = [
                bytes([0x55,0xA1,0xF1,0x01]) + bytes(4100),
                bytes([0x55,0xA1,0xF2,0x01]) + bytes(4100),
                bytes([0x00,0x55,0xA1,0xF1,0x01]) + bytes(4100),
                bytes([0x00,0x55,0xA1,0xF2,0x01]) + bytes(4100),
            ]
            for p in init_packets:
                try: write_packet(path, p)
                except Exception as e: print(f'Init ignore: {e}', flush=True)

            chunks = [raw[i:i+4096] for i in range(0, len(raw), 4096)]
            for i,ch in enumerate(chunks):
                header = bytes([0x55,0xA3, i & 255, len(chunks) & 255, len(ch)&255, (len(ch)>>8)&255, 0, 0])
                pkt = header + ch
                if m == 'raw4104':
                    pkt = pkt.ljust(4104, b'\x00')
                elif m == 'report4105':
                    pkt = (b'\x00' + pkt).ljust(4105, b'\x00')
                elif m == 'short64':
                    # split en rapports de 64 bytes precedes par report ID 0
                    pkt = pkt
                    for j in range(0, len(pkt), 63):
                        write_packet(path, (b'\x00' + pkt[j:j+63]).ljust(64, b'\x00'))
                    continue
                write_packet(path, pkt)
            print(f'Mode {m}: envoi termine', flush=True)
            time.sleep(0.3)
        except Exception as e:
            print(f'Mode {m}: erreur {e}', flush=True)
            traceback.print_exc()


def main():
    o = opts()
    refresh = int(o.get('refresh_seconds',10))
    dev = o.get('hidraw_device','/dev/hidraw1')
    orientation = o.get('orientation','landscape')
    mode = o.get('packet_mode','auto')
    print('ACEMAGIC S1 Status v1.0.6', flush=True)
    print(f'Device={dev}, refresh={refresh}, orientation={orientation}, packet_mode={mode}', flush=True)
    print('HID disponibles: ' + ', '.join(glob.glob('/dev/hidraw*')), flush=True)
    while True:
        try:
            send_hid(dev, make_image(orientation), mode)
        except Exception as e:
            print(f'Erreur generale: {e}', flush=True)
            traceback.print_exc()
        time.sleep(refresh)

if __name__ == '__main__':
    main()
