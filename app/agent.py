from anthropic import Anthropic

from app.config import settings
from app.schemas import AgentDecision, PaymentFailureEvent

_client = Anthropic(api_key=settings.anthropic_api_key)

_SYSTEM_PROMPT = (
    "You are a payment recovery (dunning) decisioning agent for a subscription "
    "business. You are given the details of a Stripe invoice payment that just "
    "failed. Classify the failure and decide on a recovery action.\n\n"
    "Classification:\n"
    "- 'insufficient_funds': the decline code or failure reason indicates the "
    "customer's account lacked funds at the time of the charge (a transient, "
    "soft decline worth retrying).\n"
    "- 'other': any other decline reason (e.g. expired card, stolen card, "
    "issuer decline, unknown).\n\n"
    "Action: the only recovery action currently available is "
    "'schedule_smart_retry' — reattempting the charge. Always choose it "
    "regardless of classification; your classification and reasoning inform "
    "how future stages will differentiate the action.\n\n"
    "Always give concrete reasoning that references the specific decline code "
    "or failure reason you were given — do not give a generic explanation."
)


class AgentDecisionError(Exception):
    """Raised when the Anthropic API call fails or returns something we can't use."""


def classify_and_decide(failure: PaymentFailureEvent) -> AgentDecision:
    user_content = (
        f"Invoice ID: {failure.invoice_id}\n"
        f"Customer ID: {failure.customer_id}\n"
        f"Amount due: {failure.amount_due} {failure.currency}\n"
        f"Decline code: {failure.decline_code or 'unknown'}\n"
        f"Failure reason: {failure.failure_reason or 'unknown'}\n"
    )

    try:
        response = _client.messages.parse(
            model=settings.anthropic_model,
            max_tokens=1024,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
            output_format=AgentDecision,
        )
    except Exception as e:
        raise AgentDecisionError(f"Anthropic API call failed: {e}") from e

    if response.parsed_output is None:
        raise AgentDecisionError(
            "Anthropic response could not be parsed into an AgentDecision "
            f"(stop_reason={response.stop_reason!r})"
        )

    return response.parsed_output
