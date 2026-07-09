FROM ghcr.io/home-assistant/amd64-base:latest

RUN apk add --no-cache \
    bash \
    python3 \
    py3-pillow \
    py3-psutil \
    py3-pip \
    libusb \
    font-dejavu

RUN pip3 install --no-cache-dir --break-system-packages pyusb

COPY run.sh /
COPY app.py /
RUN chmod +x /run.sh

CMD ["/run.sh"]
