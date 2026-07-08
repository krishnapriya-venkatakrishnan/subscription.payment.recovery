"""
Debug helper: call the agent directly with synthetic failure data — no
Stripe, no webhook, no running server needed. This is the fastest way to
see how classify_and_decide() behaves, and the tool to reach for while
iterating on the system prompt or schema in app/agent.py.

Usage:
    python scripts/debug_agent.py
    python scripts/debug_agent.py --reason insufficient_funds
    python scripts/debug_agent.py --reason unknown
"""
import argparse
import sys
from pathlib import Path

# Allow running as `python scripts/debug_agent.py` from the project root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agent import AgentDecisionError, classify_and_decide  # noqa: E402
from app.schemas import PaymentFailureEvent  # noqa: E402

# (decline_code, failure_reason) — mirrors what a real Stripe Charge would carry
SCENARIOS = {
    "insufficient_funds": ("insufficient_funds", "Your card has insufficient funds."),
    "generic_decline": ("card_declined", "Your card was declined."),
    "expired_card": ("expired_card", "Your card has expired."),
    "stolen_card": ("stolen_card", "Your card was reported lost or stolen."),
    "unknown": (None, None),  # simulates a failed charge lookup
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reason", choices=SCENARIOS.keys(), default="insufficient_funds")
    args = parser.parse_args()

    decline_code, failure_reason = SCENARIOS[args.reason]

    failure = PaymentFailureEvent(
        stripe_event_id="evt_debug_local",
        invoice_id="in_debug_local",
        customer_id="cus_debug_local",
        decline_code=decline_code,
        failure_reason=failure_reason,
        amount_due=2000,
        currency="usd",
    )

    print(f"Input:  decline_code={decline_code!r} failure_reason={failure_reason!r}\n")

    try:
        decision = classify_and_decide(failure)
    except AgentDecisionError as e:
        print(f"AgentDecisionError: {e}")
        return

    print(f"classification: {decision.classification}")
    print(f"action:         {decision.action}")
    print(f"reasoning:      {decision.reasoning}")


if __name__ == "__main__":
    main()
