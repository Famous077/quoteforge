"""Register QuoteForge with a running TrueForge server. Safe to re-run (every call is an upsert).

Run: uv run setup.py
"""

import os
import re
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

AGENT_NAME = "quoteforge"
TOOLS_SERVER = "quoteforge-tools"
PROMPT = (Path(__file__).parent / "prompts" / "system.md").read_text()


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, "").strip() or default


def model_name(model_id: str) -> str:
    # TrueForge resource names are lowercase slugs; the gateway id is sent upstream unchanged.
    return re.sub(r"[^a-z0-9]+", "-", model_id.lower()).strip("-")[:64]


def build_spec(model_fqn: str, sandbox: bool) -> dict:
    return {
        "model": {"name": model_fqn, "params": {"temperature": 0}},
        "instructions": PROMPT,
        "mcp_servers": [
            {
                "name": TOOLS_SERVER,
                "enable_tools": ["@all"],
                # Named explicitly so the gate holds even if a server drops its annotations.
                "require_approval_for_tools": ["@destructive", "send_quote", "create_po"],
                "preload": True,
            }
        ],
        "config": {
            "sandbox": {"enabled": sandbox},
            "dynamic_sub_agents": {"enabled": False},
            "ask_user_questions": {"enabled": True},
            "iteration_limit": 30,
        },
    }


def put(client: httpx.Client, path: str, body: dict) -> dict:
    r = client.put(path, json=body)
    if r.is_error:
        sys.exit(f"PUT {path} failed ({r.status_code}): {r.text}")
    return r.json()


def main() -> None:
    client = httpx.Client(base_url=env("TRUEFORGE_BASE_URL", "http://localhost:8790") + "/api/v1", timeout=120)

    tools_url = env("TOOLS_MCP_URL", "http://127.0.0.1:8801/mcp")
    put(client, "/settings/mcp-servers", {"manifest": {
        "type": "remote",
        "name": TOOLS_SERVER,
        "url": tools_url,
        "description": "Shop rate card, stock check and quote sending.",
    }})
    print(f"MCP server '{TOOLS_SERVER}' -> {tools_url}")

    daytona_key = env("DAYTONA_API_KEY")
    if daytona_key:
        put(client, "/settings/sandbox-providers", {"manifest": {
            "type": "daytona",
            "auth": {"api_key": daytona_key},
            "exec_timeout_ms": 60000,
            "auto_stop_interval_in_minutes": 5,
            "auto_archive_interval_in_minutes": 60,
            "auto_delete_interval_in_minutes": 7200,
        }})
    print(f"Sandbox: {'on (Daytona)' if daytona_key else 'off (no DAYTONA_API_KEY)'}")

    missing = [v for v in ("TFY_GATEWAY_BASE_URL", "TFY_API_KEY", "TFY_MODEL_ID") if not env(v)]
    if missing:
        sys.exit(f"Skipping model provider and agent: set {', '.join(missing)} in .env")

    model_id = env("TFY_MODEL_ID")
    put(client, "/settings/model-providers", {"manifest": {
        "type": "truefoundry",
        "base_url": env("TFY_GATEWAY_BASE_URL"),
        "auth": {"api_key": env("TFY_API_KEY")},
        "models": [{"model_id": model_id, "name": model_name(model_id), "properties": {}}],
    }})
    model_fqn = f"truefoundry/{model_name(model_id)}"
    print(f"Model provider: truefoundry, model {model_fqn}")

    spec = build_spec(model_fqn, sandbox=bool(daytona_key))
    existing = next((a for a in client.get("/agents").json()["data"] if a["name"] == AGENT_NAME), None)
    if existing:
        put(client, f"/agents/{existing['id']}", {"manifest": spec})
    else:
        r = client.post("/agents", json={
            "name": AGENT_NAME,
            "description": "Turns fabrication enquiries into verified, owner-approved quotes.",
            "manifest": spec,
        })
        if r.is_error:
            sys.exit(f"POST /agents failed ({r.status_code}): {r.text}")
    print(f"Agent '{AGENT_NAME}' saved")


if __name__ == "__main__":
    main()
