"""
Debug helper: post a synthetic invoice.payment_failed event straight to the
local webhook endpoint, signed the same way Stripe signs real deliveries.
No real Stripe subscription or charge is created — this exercises the
FastAPI route itself: signature verification, event-type routing, and
idempotency. Requires `uvicorn app.main:app` to be running separately.

Since app/webhook.py fetches decline info from a real Stripe Charge (by the
charge id embedded in the event), a synthetic event's charge id won't exist
in Stripe — decline_code/failure_reason will come back "unknown" here. For
real classification testing (insufficient_funds vs. other), use a real
Stripe test-mode subscription (see README.md), or scripts/debug_agent.py to
test the agent's classification logic directly.

Usage:
    python scripts/send_test_webhook.py
        # first delivery of a fresh event

    python scripts/send_test_webhook.py --event-id evt_test_123
    python scripts/send_test_webhook.py --event-id evt_test_123
        # run twice with the same --event-id to test idempotency —
        # second call should return "already_processed"

    python scripts/send_test_webhook.py --bad-signature
        # should be rejected with 400 (signature verification)

    python scripts/send_test_webhook.py --event-type customer.created
        # should return {"status": "ignored", ...} — event type we don't handle
"""
import argparse
import hashlib
import hmac
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402

WEBHOOK_URL = "http://localhost:8000/webhooks/stripe"


def sign(payload: bytes, secret: str, timestamp: int) -> str:
    """Reimplements Stripe's webhook signing scheme: HMAC-SHA256 over
    "{timestamp}.{payload}", formatted as the Stripe-Signature header."""
    signed_payload = f"{timestamp}.{payload.decode()}".encode()
    signature = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={signature}"


def build_event(event_id: str, event_type: str) -> dict:
    return {
        "id": event_id,
        "object": "event",
        "type": event_type,
        "data": {
            "object": {
                "id": f"in_test_{uuid.uuid4().hex[:16]}",
                "object": "invoice",
                "customer": f"cus_test_{uuid.uuid4().hex[:16]}",
                "charge": f"ch_test_{uuid.uuid4().hex[:16]}",
                "amount_due": 2000,
                "currency": "usd",
            }
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-id", default=None, help="Reuse to test idempotency")
    parser.add_argument("--event-type", default="invoice.payment_failed")
    parser.add_argument("--bad-signature", action="store_true", help="Sign with the wrong secret")
    args = parser.parse_args()

    event_id = args.event_id or f"evt_test_{uuid.uuid4().hex[:16]}"
    event = build_event(event_id, args.event_type)
    payload = json.dumps(event).encode()

    secret = "whsec_wrong_secret" if args.bad_signature else settings.stripe_webhook_secret
    signature = sign(payload, secret, timestamp=int(time.time()))

    req = urllib.request.Request(
        WEBHOOK_URL,
        data=payload,
        headers={"Content-Type": "application/json", "Stripe-Signature": signature},
        method="POST",
    )

    print(f"event_id: {event_id}")
    try:
        with urllib.request.urlopen(req) as resp:
            print(f"status:   {resp.status}")
            print(f"body:     {resp.read().decode()}")
    except urllib.error.HTTPError as e:
        print(f"status:   {e.code}")
        print(f"body:     {e.read().decode()}")


if __name__ == "__main__":
    main()
