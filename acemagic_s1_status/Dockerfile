FROM ghcr.io/home-assistant/amd64-base:latest

RUN apk add --no-cache \
    bash \
    python3 \
    py3-pillow \
    py3-psutil \
    font-dejavu \
    jq \
    eudev-libs

COPY run.sh /
COPY app.py /
RUN chmod +x /run.sh

CMD ["/run.sh"]
