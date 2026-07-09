FROM ghcr.io/home-assistant/amd64-base:latest

RUN apk add --no-cache \
    bash \
    python3 \
    py3-pip \
    py3-pillow \
    py3-psutil \
    py3-setuptools \
    font-dejavu \
    libusb \
    usbutils \
    jq \
 && pip3 install --break-system-packages pyusb libusb1

COPY run.sh /
COPY app.py /
RUN chmod +x /run.sh
CMD ["/run.sh"]
