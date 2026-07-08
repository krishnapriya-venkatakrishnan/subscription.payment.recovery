from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request, Response
from sqlalchemy.orm import Session

from app.agent import AgentDecisionError
from app.db import get_db, init_db
from app.orchestrator import process_payment_failure
from app.webhook import (
    WebhookVerificationError,
    extract_payment_failure,
    verify_and_parse_event,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Subscription Payment Recovery Agent", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/webhooks/stripe")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = verify_and_parse_event(payload, sig_header)
    except WebhookVerificationError as e:
        return Response(content=f"Webhook signature verification failed: {e}", status_code=400)

    if event["type"] != "invoice.payment_failed":
        return {"status": "ignored", "type": event["type"]}

    failure = extract_payment_failure(event)

    try:
        log = process_payment_failure(db, failure)
    except AgentDecisionError as e:
        # 5xx so Stripe retries the webhook later — nothing was durably
        # recorded, so a later delivery can still succeed.
        return Response(content=str(e), status_code=500)

    if log is None:
        return {"status": "already_processed", "stripe_event_id": failure.stripe_event_id}

    return {
        "status": "processed",
        "stripe_event_id": log.stripe_event_id,
        "classification": log.classification,
        "action": log.action,
        "reasoning": log.reasoning,
        "action_result": log.action_result,
    }
