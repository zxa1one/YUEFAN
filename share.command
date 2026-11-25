#!/bin/bash
cd "$(dirname "$0")" || exit 1
CF="$(command -v cloudflared || true)"
if [ -z "$CF" ] && [ -x "$HOME/.local/bin/cloudflared" ]; then CF="$HOME/.local/bin/cloudflared"; fi
if [ -z "$CF" ]; then echo '请先安装 Cloudflared：https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/downloads/'; exit 1; fi
exec "$CF" tunnel --protocol http2 --url "http://127.0.0.1:${PORT:-8000}"
