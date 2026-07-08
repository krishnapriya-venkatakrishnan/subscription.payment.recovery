import stripe

from app.config import settings
from app.schemas import ActionResult, AgentDecision, PaymentFailureEvent

stripe.api_key = settings.stripe_secret_key


def execute_action(decision: AgentDecision, failure: PaymentFailureEvent) -> ActionResult:
    """Execute the agent's chosen recovery action against Stripe test mode."""

    if decision.action != "schedule_smart_retry":
        # Forward-compatible guard: future stages will add more actions here.
        return ActionResult(status="skipped", detail=f"Unrecognized action: {decision.action}")

    try:
        stripe.Invoice.pay(failure.invoice_id)
        return ActionResult(
            status="success", detail="Invoice payment reattempted via Stripe API."
        )
    except stripe.error.StripeError as e:
        return ActionResult(status="failed", detail=str(e))
