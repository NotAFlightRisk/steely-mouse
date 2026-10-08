FROM python:3.15-slim AS build

# hidapi only ships wheels for some pythons, so keep what it needs to build from source
RUN apt-get update \
 && apt-get install -y --no-install-recommends gcc libc6-dev pkg-config libudev-dev libusb-1.0-0-dev \
 && rm -rf /var/lib/apt/lists/*

ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PATH="/venv/bin:$PATH"
RUN python -m venv /venv

ARG VERSION=0.0.0
WORKDIR /src
COPY pyproject.toml LICENSE ./
COPY .github/README.md ./.github/
COPY rivalcfg_gui ./rivalcfg_gui
RUN SETUPTOOLS_SCM_PRETEND_VERSION="${VERSION}" pip install . \
 && mkdir /udev \
 && rivalcfg --print-udev > /udev/99-steelseries-rival.rules


FROM python:3.15-slim

ARG VERSION=0.0.0
ARG REVISION=unknown
ARG CREATED=unknown

LABEL org.opencontainers.image.title="steely-mouse" \
      org.opencontainers.image.description="A web GUI for configuring SteelSeries mice" \
      org.opencontainers.image.source="https://github.com/NotAFlightRisk/steely-mouse" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${REVISION}" \
      org.opencontainers.image.created="${CREATED}"

RUN apt-get update \
 && apt-get install -y --no-install-recommends libudev1 libusb-1.0-0 \
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
