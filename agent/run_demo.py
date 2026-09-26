"""Run a demo scenario through the saved QuoteForge agent and stop at the first approval gate.

Run: uv run run_demo.py [--scenario 1|3] [--approve | --deny]
Without a decision flag the run stops at the first gate and nothing is sent.
With one, every gate in the run gets that decision.
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

# Moves to demo/ once it lands there. Scenario 3 is scenario 1 with a target that puts margin at 8.14%.
SCENARIOS = {
    1: """From: Rakesh Sharma, Sharma Industries <purchase@sharma-industries.example>

Hi, please quote for 50 nos MS L brackets, 200 x 100 x 8 mm, 1 bend and 2 holes each, powder coated.
Delivery needed in 2 weeks.""",
    3: """From: Rakesh Sharma, Sharma Industries <purchase@sharma-industries.example>

Hi, please quote for 50 nos MS L brackets, 200 x 100 x 8 mm, 1 bend and 2 holes each, powder coated.
Our budget is Rs 8,700 for the full order, all inclusive of GST. Delivery needed in 2 weeks.""",
}
EXPECTED_FIRST_GATE = {1: "send_quote", 3: "request_margin_approval"}

# make_quote_pdf does not exist yet, so there is no real quote id; remove once it does.
QUOTE_ID_NOTE = '[Demo run: use quote_id "Q-DEMO-001".]'


def stream_turn(client: TrueForge, session_id: str, turn_input: list, events: dict) -> list:
    """Stream one turn, print tool activity and costing breakdowns, and return pending approval events."""
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
            breakdown = find_breakdown(event.content)
            if breakdown:
                print(f"\n-> {name}(...)")
                print_breakdown(breakdown)
            else:
                print(f"\n-> {name}({args})\n<- {str(event.content)[:800]}")
        elif event.type == "tool.approval_required":
            pending.append(event)
        elif event.type == "tool.response_required":
            for ref in event.tool_calls:
                print(f"\nAgent asked: {find_call(events, ref.id)[1]}")
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


def find_breakdown(content) -> dict | None:
    """Pull a costing.py breakdown out of a sandbox tool response, however the harness wraps stdout."""
    if isinstance(content, dict):
        if "line_items" in json.dumps(content) and "total" in content:
            return content
        return next((b for v in content.values() if (b := find_breakdown(v))), None)
    if isinstance(content, list):
        return next((b for v in content if (b := find_breakdown(v))), None)
    if isinstance(content, str) and "line_items" in content:
        decoder = json.JSONDecoder()
        for i, ch in enumerate(content):
            if ch == "{":
                try:
                    found = find_breakdown(decoder.raw_decode(content, i)[0])
                except ValueError:
                    continue
                if found:
                    return found
    return None


def print_breakdown(b: dict) -> None:
    rs = lambda x: f"{x:>12,.2f}"
    print("   === Costing breakdown (costing.py) ===")
    for item in b["items"]:
        dims = " x ".join(str(d) for d in item["dimensions_mm"])
        print(f"   {item['name']} x {item['qty']} ({item['material']} {dims} mm), {item['weight_kg_per_piece']} kg/pc, needs {item['kg_needed']} kg")
        for line in item["line_items"]:
            print(f"     {line['label']:<10} {line['detail']:<48} {rs(line['amount'])}")
    print(f"   {'Cost subtotal':<61} {rs(b['cost_subtotal'])}")
    print(f"   {'Overhead ' + str(b['overhead']['pct']) + '%':<61} {rs(b['overhead']['amount'])}")
    print(f"   {'Margin ' + str(b['margin']['pct']) + '%':<61} {rs(b['margin']['amount'])}")
    print(f"   {'Price before GST':<61} {rs(b['price_before_gst'])}")
    print(f"   {'GST ' + str(b['gst']['pct']) + '%':<61} {rs(b['gst']['amount'])}")
    print(f"   {'TOTAL':<61} {rs(b['total'])}")
    mc, sc = b["margin_check"], b["self_check"]
    print(f"   Margin check: effective {mc['effective_margin_pct']}% vs floor {mc['margin_floor_pct']}%, below floor: {mc['below_floor']}")
    print(f"   Self-check: {'passed' if sc['passed'] else 'FAILED ' + '; '.join(sc['errors'])}")


def gates(events: dict, pending: list) -> list[tuple]:
    return [(p.thread_id, ref.id, *find_call(events, ref.id)) for p in pending for ref in p.tool_calls]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", type=int, choices=sorted(SCENARIOS), default=1)
    decision = parser.add_mutually_exclusive_group()
    decision.add_argument("--approve", action="store_true", help="allow every gated call")
    decision.add_argument("--deny", action="store_true", help="deny every gated call")
    args = parser.parse_args()

    client = TrueForge(base_url=os.environ.get("TRUEFORGE_BASE_URL") or "http://localhost:8790", timeout=600)
    session = client.sessions.create(agent={"name": AGENT_NAME})
    enquiry = SCENARIOS[args.scenario]
    print(f"Session {session.data.id}\n\nScenario {args.scenario} enquiry:\n{enquiry}")

    events: dict = {}
    pending = stream_turn(client, session.data.id, [{"type": "user.message", "content": f"{enquiry}\n\n{QUOTE_ID_NOTE}"}], events)
    first = gates(events, pending)

    responses = [e for e in events.values() if e.type == "tool.response"]
    called = [find_call(events, e.tool_call_id)[0] for e in responses]
    stock_kg = [json.loads(find_call(events, e.tool_call_id)[1]).get("kg_needed") for e in responses if find_call(events, e.tool_call_id)[0] == "check_stock"]
    breakdowns = [b for e in responses if (b := find_breakdown(e.content))]

    print("\n=== Approval gate ===")
    if not first:
        print("No approval pending.")
    for _, _, name, call_args in first:
        print(f"PAUSED before {name}({call_args})")

    sandbox = bool(os.environ.get("DAYTONA_API_KEY"))
    checks = {
        "rate card fetched": "get_rate_card" in called,
        "stock checked": "check_stock" in called,
        "nothing sent": "send_quote" not in called,
    }
    if not sandbox:
        # Without costing there are no trusted numbers, so the agent keeps a draft and stops.
        checks["stops as draft without a gate (no sandbox)"] = not first
    else:
        checks[f"first gate is {EXPECTED_FIRST_GATE[args.scenario]}"] = bool(first) and first[0][2] == EXPECTED_FIRST_GATE[args.scenario]
        checks["check_stock got kg_needed 65.94"] = 65.94 in stock_kg
        checks["costing.py breakdown total 9654.44"] = any(b["total"] == 9654.44 and b["self_check"]["passed"] for b in breakdowns)
        if args.scenario == 3:
            checks["margin below floor (8.14%)"] = any(b["margin_check"]["effective_margin_pct"] == 8.14 for b in breakdowns)
    ok = all(checks.values())
    for label, passed in checks.items():
        print(f"  [{'x' if passed else ' '}] {label}")
    print(f"\nScenario {args.scenario}: {'PASS' if ok else 'FAIL'} (tools run: {called})")

    if args.approve or args.deny:
        approval = {"status": "allow"} if args.approve else {"status": "deny", "reason": "Owner rejected; keep as draft."}
        pending_gates = first
        while pending_gates:
            print(f"\nOwner decision on {', '.join(g[2] for g in pending_gates)}: {approval['status']}")
            pending = stream_turn(client, session.data.id, [
                {"type": "user.tool_approval", "thread_id": thread_id, "tool_call_id": call_id, "approval": approval}
                for thread_id, call_id, _, _ in pending_gates
            ], events)
            pending_gates = gates(events, pending)
            for _, _, name, call_args in pending_gates:
                print(f"\nPAUSED before {name}({call_args})")

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
