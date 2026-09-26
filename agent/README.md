# agent/

QuoteForge agent on TrueForge. Needs Node 22.14+ and [uv](https://docs.astral.sh/uv/).

```bash
cp .env.example .env          # repo root; fill OPENAI_API_KEY (and DAYTONA_API_KEY to enable the sandbox)
cd agent
uv run mocks/server.py        # terminal 1: mock tools MCP server on :8801
./start_trueforge.sh          # terminal 2: TrueForge on :8790
uv run setup.py               # register tools, model, sandbox and the "quoteforge" agent (re-runnable)
uv run run_demo.py            # scenario 1: stops at the send_quote approval gate
uv run run_demo.py --approve  # same, then approve (or --deny)
```

- Model provider is `MODEL_PROVIDER` in `.env` (`openai` or `truefoundry`). To switch to the TrueFoundry gateway, set it to `truefoundry`, fill `TFY_*`, and re-run `setup.py`.
- Tools come from the MCP server at `TOOLS_MCP_URL`. To use the real tools, point it at that server and re-run `setup.py`.
- `send_quote` and `create_po` always need approval (annotated destructive, and named in `require_approval_for_tools`).
- The sandbox is on only when `DAYTONA_API_KEY` is set. Without it the agent calls `check_stock` with `kg_needed: null`.
- `start_trueforge.sh` allows `127.0.0.1` through TrueForge's outbound URL guard so it can reach the local tools server.
