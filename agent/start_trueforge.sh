#!/usr/bin/env bash
# Local TrueForge server. Its outbound URL guard blocks private hosts, so allow only
# the local tools MCP server.
set -euo pipefail
OUTBOUND_URL_ALLOWED_HOSTS='["127.0.0.1"]' exec npx -y @truefoundry/trueforge@0.2.1 "$@"
