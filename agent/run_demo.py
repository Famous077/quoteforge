"""Run demo scenario 1 through the saved QuoteForge agent and stop at the send_quote approval gate.

Run: uv run run_demo.py [--approve | --deny]
Without a flag the run stops at the gate and nothing is sent.
"""

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from trueforge_sdk import TrueForge
from trueforge_sdk.events import is_event_delta, merge_event_delta

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

AGENT_NAME = "quoteforge"

# Scenario 1 (clean enquiry). Moves to demo/ once it lands there.
ENQUIRY = """From: Rakesh Sharma, Sharma Industries <purchase@sharma-industries.example>

Hi, please quote for 50 nos MS L brackets, 200 x 100 x 8 mm, 1 bend and 2 holes each, powder coated.
Delivery needed in 2 weeks."""

# Costing and PDF are not built yet; remove this once run_code and make_quote_pdf exist.
SKELETON_NOTE = """[Skeleton run: costing is not available yet. After get_rate_card and check_stock,
call send_quote with quote_id "Q-DEMO-001" and the customer's email so the owner can review.]"""


def stream_turn(client: TrueForge, session_id: str, turn_input: list, events: dict) -> list:
    """Stream one turn, print tool activity, and return pending approval events."""
    pending = []
    for event in client.sessions.create_turn_stream(session_id=session_id, input=turn_input):
        if is_event_delta(event):
            base = events.get(event.id)
            if base is not None:
                merge_event_delta(base, event)
            continue
        events[event.id] = event

        if event.type == "tool.response":
            name, args = find_call(events, event.tool_call_id)
            print(f"\n-> {name}({args})\n<- {event.content}")
        elif event.type == "tool.approval_required":
            pending.append(event)
        elif event.type == "turn.done":
            state = event.state
            if state.status != "done":
                sys.exit(f"Turn ended with status {state.status}: {getattr(state, 'message', None) or getattr(state, 'reason', None)}")
            if state.output is not None and state.output.content:
                print(f"\nAgent:\n{state.output.content}")
    return pending


def find_call(events: dict, tool_call_id: str) -> tuple[str, str]:
    for e in events.values():
        if e.type == "model.message":
            for tc in e.tool_calls or []:
                if tc.id == tool_call_id:
                    return tc.function.name, tc.function.arguments
    return "?", "?"


def main() -> None:
    parser = argparse.ArgumentParser()
    decision = parser.add_mutually_exclusive_group()
    decision.add_argument("--approve", action="store_true", help="allow send_quote after the gate")
    decision.add_argument("--deny", action="store_true", help="deny send_quote after the gate")
    args = parser.parse_args()

    client = TrueForge(base_url=os.environ.get("TRUEFORGE_BASE_URL") or "http://localhost:8790", timeout=600)
    session = client.sessions.create(agent={"name": AGENT_NAME})
    print(f"Session {session.data.id}\n\nEnquiry:\n{ENQUIRY}")

    events: dict = {}
    pending = stream_turn(client, session.data.id, [{"type": "user.message", "content": f"{ENQUIRY}\n\n{SKELETON_NOTE}"}], events)

    called = [find_call(events, e.tool_call_id)[0] for e in events.values() if e.type == "tool.response"]
    gated = [(p.thread_id, ref.id, *find_call(events, ref.id)) for p in pending for ref in p.tool_calls]

    print("\n=== Approval gate ===")
    if not gated:
        print("No approval pending.")
    for _, _, name, call_args in gated:
        print(f"PAUSED before {name}({call_args})")

    ok = "get_rate_card" in called and "check_stock" in called and any(g[2] == "send_quote" for g in gated) and "send_quote" not in called
    print(f"\nScenario 1 skeleton: {'PASS' if ok else 'FAIL'} (tools run: {called})")

    if gated and (args.approve or args.deny):
        approval = {"status": "allow"} if args.approve else {"status": "deny", "reason": "Owner rejected; keep as draft."}
        print(f"\nOwner decision: {approval['status']}")
        stream_turn(client, session.data.id, [
            {"type": "user.tool_approval", "thread_id": thread_id, "tool_call_id": call_id, "approval": approval}
            for thread_id, call_id, _, _ in gated
        ], events)

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
