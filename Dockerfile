FROM python:3.11-slim AS builder

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    mpg123 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /root/.local /root/.local

ENV PATH=/root/.local/bin:$PATH

COPY src/ ./src/
COPY pyproject.toml ./

RUN pip install --no-cache-dir -e ".[sse]"

ENV MCP_MUSIC_DIR=/music
ENV MCP_ENABLED_PLATFORMS=netease,qqmusic,kugou,local
ENV MCP_TRANSPORT=stdio
ENV MCP_HOST=0.0.0.0
ENV MCP_PORT=8090

RUN mkdir -p /music

EXPOSE 8090

VOLUME ["/music"]

ENTRYPOINT ["python", "-m", "mcp_music_server.server"]
