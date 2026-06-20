#!/usr/bin/env bash
# DIAGNOSTIC pass for the UE5.8 + Epic MCP wiring. Output -> /workspace/web/driver.out
# (HTTPS: https://<pod>-6080.proxy.runpod.net/driver.out). Read-only/safe.
echo "===== DRIVER DIAG $(date -u) whoami=$(whoami) uid=$(id -u) ====="

echo "----- setup.log (did socat/sshd install run? as which user?) -----"
tail -25 /workspace/setup.log 2>/dev/null

echo "----- socat present / running? -----"
which socat || echo "socat NOT installed"
pgrep -af socat || echo "socat NOT running"

echo "----- listening ports (8000/8009/8011) -----"
(ss -tlnp 2>/dev/null || netstat -tlnp 2>/dev/null) | grep -E ':(8000|8009|8011)\b' || echo "none of 8000/8009/8011 listening"

echo "----- is the editor running, and with the MCP flags? -----"
pgrep -af UnrealEditor | head -c 1000; echo

echo "----- MCP plugin actually present in the engine image? -----"
find /home/ue4/UnrealEngine/Engine/Plugins -maxdepth 5 -type d \
  \( -iname '*ContextProtocol*' -o -iname '*ToolsetRegistry*' -o -iname '*MCP*' \) 2>/dev/null | head
echo "(if empty: experimental MCP plugin is NOT in dev-slim)"

echo "----- probe local MCP on 8009 -----"
curl -s -m 6 -o /dev/null -w '127.0.0.1:8009/mcp -> %{http_code}\n' -X POST http://127.0.0.1:8009/mcp \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"p","version":"1"}}}' || echo "8009 no answer"

echo "----- ue.log: MCP / ContextProtocol / Unknown-command lines -----"
grep -iE 'ContextProtocol|ToolsetRegistry|MCP server|Model Context|Unknown command .*Protocol' /workspace/ue.log 2>/dev/null | tail -12 \
  || echo "no MCP-related log lines"

echo "----- fresh 5.8 init reached? -----"
grep -E '2026.06.20.*Engine is initialized' /workspace/ue.log 2>/dev/null | tail -1 || echo "no 2026-06-20 init line yet"

echo "===== DRIVER DIAG END ====="
