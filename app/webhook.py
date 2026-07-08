import stripe

from app.config import settings
from app.schemas import PaymentFailureEvent

stripe.api_key = settings.stripe_secret_key


class WebhookVerificationError(Exception):
    """Raised when a webhook payload fails Stripe signature verification."""


def verify_and_parse_event(payload: bytes, sig_header: str) -> stripe.Event:
    try:
        return stripe.Webhook.construct_event(
            payload, sig_header, settings.stripe_webhook_secret
        )
    except (ValueError, stripe.error.SignatureVerificationError) as e:
        raise WebhookVerificationError(str(e)) from e


def extract_payment_failure(event: stripe.Event) -> PaymentFailureEvent:
    """Pull the failure reason / decline code out of the event's invoice + charge.

    The invoice object on invoice.payment_failed carries a `charge` id pointing
    at the failed charge, which is where Stripe puts `failure_code` /
    `failure_message`. Charge lookup is best-effort — if it fails we still
    return the event with unknown reason fields rather than blocking the
    webhook.
    """

    invoice = event["data"]["object"]

    decline_code = None
    failure_reason = None

    charge_id = getattr(invoice, "charge", None)
    if charge_id:
        try:
            charge = stripe.Charge.retrieve(charge_id)
            decline_code = getattr(charge, "failure_code", None)
            failure_reason = getattr(charge, "failure_message", None)
        except stripe.error.StripeError:
            pass

    return PaymentFailureEvent(
        stripe_event_id=event["id"],
        invoice_id=invoice["id"],
        customer_id=invoice["customer"],
        decline_code=decline_code,
        failure_reason=failure_reason,
        amount_due=getattr(invoice, "amount_due", 0),
        currency=getattr(invoice, "currency", "usd"),
    )
