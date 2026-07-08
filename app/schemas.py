from typing import Literal, Optional

from pydantic import BaseModel


class PaymentFailureEvent(BaseModel):
    """Extracted from a Stripe invoice.payment_failed event — the input to the agent."""

    stripe_event_id: str
    invoice_id: str
    customer_id: str
    decline_code: Optional[str] = None
    failure_reason: Optional[str] = None
    amount_due: int
    currency: str


class AgentDecision(BaseModel):
    """Structured output of the decisioning agent.

    Kept minimal for Stage 1 (single action). The schema is deliberately
    forward-compatible: later stages will widen `action`'s allowed values
    and this shape stays the same.
    """

    classification: Literal["insufficient_funds", "other"]
    action: Literal["schedule_smart_retry"]
    reasoning: str


class ActionResult(BaseModel):
    status: Literal["success", "failed", "skipped"]
    detail: str
