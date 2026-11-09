FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends bash git ripgrep \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir tzdata

COPY tools.py /opt/harness/tools.py

WORKDIR /workspace
