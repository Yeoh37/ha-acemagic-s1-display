ARG BUILD_FROM
FROM $BUILD_FROM

RUN apk add --no-cache \
    bash \
    python3 \
    py3-pip \
    py3-pillow \
    py3-psutil \
    font-dejavu \
    jq \
    eudev-libs

COPY run.sh /
COPY app.py /
RUN chmod +x /run.sh

CMD ["/run.sh"]
