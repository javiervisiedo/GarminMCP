FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    GARMIN_MCP_TRANSPORT=streamable-http \
    GARMIN_TOKEN_DIR=/home/garmincoach/.garminconnect \
    GARMIN_CACHE_DIR=/home/garmincoach/.cache/garmin-coach-mcp \
    PORT=8080

RUN groupadd --gid 10001 garmincoach \
    && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin garmincoach

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src/ ./src/

RUN pip install --no-cache-dir . \
    && mkdir -p /home/garmincoach/.garminconnect /home/garmincoach/.cache/garmin-coach-mcp \
    && chmod 700 /home/garmincoach/.garminconnect /home/garmincoach/.cache/garmin-coach-mcp \
    && chown -R garmincoach:garmincoach /home/garmincoach /app

USER garmincoach

EXPOSE 8080

ENTRYPOINT ["garmin-coach-mcp", "--transport", "streamable-http"]
