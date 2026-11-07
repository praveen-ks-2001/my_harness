FROM python:3.12-slim

RUN pip install --no-cache-dir tzdata

COPY tools.py /opt/harness/tools.py

WORKDIR /workspace
