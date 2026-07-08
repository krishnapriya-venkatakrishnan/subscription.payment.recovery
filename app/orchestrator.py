from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.agent import classify_and_decide
from app.models import DecisionLog
from app.schemas import PaymentFailureEvent
from app.stripe_actions import execute_action


def process_payment_failure(
    db: Session, failure: PaymentFailureEvent
) -> Optional[DecisionLog]:
    """Process one failed-payment event end-to-end.

    Returns None if this event was already processed (idempotent no-op —
    a re-delivered Stripe webhook must not double-execute the action).

    Raises AgentDecisionError (from classify_and_decide) if the Anthropic
    call fails — the caller should surface this as a 5xx so Stripe retries
    the webhook later. No row is written in that case, since nothing was
    decided or executed yet.
    """

    existing = (
        db.query(DecisionLog)
        .filter(DecisionLog.stripe_event_id == failure.stripe_event_id)
        .first()
    )
    if existing is not None:
        return None

    decision = classify_and_decide(failure)
    result = execute_action(decision, failure)

    log = DecisionLog(
        stripe_event_id=failure.stripe_event_id,
        invoice_id=failure.invoice_id,
        customer_id=failure.customer_id,
        decline_code=failure.decline_code,
        failure_reason=failure.failure_reason,
        classification=decision.classification,
        action=decision.action,
        reasoning=decision.reasoning,
        action_result=result.status,
        action_error=None if result.status == "success" else result.detail,
    )

    db.add(log)
    try:
        db.commit()
    except IntegrityError:
        # Lost a race with a concurrent delivery of the same event — the
        # other request's row is the durable record; treat this as a no-op.
        db.rollback()
        return None

    db.refresh(log)
    return log
