FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends bash git ripgrep \
    && rm -rf /var/lib/apt/lists/*

# Tool runtime dependencies, pinned to the versions in uv.lock.
RUN pip install --no-cache-dir tzdata pydantic==2.14.2 docstring-parser==0.18.0

COPY tools /opt/harness/tools
# Lets `python -P -m tools.runner` find the tool package from any working directory.
ENV PYTHONPATH=/opt/harness

WORKDIR /workspace
