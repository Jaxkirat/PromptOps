FROM python:3.12-slim

RUN pip install --no-cache-dir pytest==9.2.0 \
    && useradd --create-home --uid 10001 sandbox

USER sandbox
WORKDIR /work
