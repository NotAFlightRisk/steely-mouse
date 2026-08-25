FROM python:3.13-slim AS build

# wheels cover the common arches, the toolchain is there for the ones they don't
RUN apt-get update \
 && apt-get install -y --no-install-recommends gcc libhidapi-dev libudev-dev \
 && rm -rf /var/lib/apt/lists/*

ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PATH="/venv/bin:$PATH"
RUN python -m venv /venv

WORKDIR /src
COPY pyproject.toml README.md LICENSE ./
COPY rivalcfg_gui ./rivalcfg_gui
RUN pip install . \
 && mkdir /udev \
 && rivalcfg --print-udev > /udev/99-steelseries-rival.rules


FROM python:3.13-slim

ARG VERSION=dev
ARG REVISION=unknown
ARG CREATED=unknown

LABEL org.opencontainers.image.title="rivalcfg-gui" \
      org.opencontainers.image.description="A web GUI for configuring SteelSeries mice" \
      org.opencontainers.image.source="https://github.com/Lissy93/rivalcfg-gui" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${REVISION}" \
      org.opencontainers.image.created="${CREATED}"

# hidapi reaches the mouse through hidraw, so its shared libs have to be here
RUN apt-get update \
 && apt-get install -y --no-install-recommends libhidapi-hidraw0 libhidapi-libusb0 \
 && rm -rf /var/lib/apt/lists/*

COPY --from=build /venv /venv
COPY --from=build /udev /udev

ENV PATH="/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    RIVALCFG_GUI_HOST=0.0.0.0 \
    RIVALCFG_GUI_PORT=8777
EXPOSE 8777

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import os, urllib.request as r; r.urlopen('http://127.0.0.1:%s/' % os.environ['RIVALCFG_GUI_PORT'])"

ENTRYPOINT ["rivalcfg-gui", "--no-browser"]
