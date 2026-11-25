# LOOP UI test image: real GTK 3 on a virtual X display (Xvfb), for window screenshots in seconds.
# Debian 13 (trixie), the same release as Raspberry Pi OS on the displays.
FROM debian:trixie-slim
ENV DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8
RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 python3-gi gir1.2-gtk-3.0 gir1.2-gdkpixbuf-2.0 librsvg2-common \
      xvfb xauth dbus-x11 fonts-dejavu-core fonts-inter adwaita-icon-theme \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /loop
CMD ["sh", "sim/docker/run.sh"]
