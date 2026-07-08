from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from app.db import Base


class DecisionLog(Base):
    """One row per processed invoice.payment_failed event.

    stripe_event_id is unique — this is the idempotency key. A row only
    exists here once the full pipeline (agent decision + action attempt)
    has completed, so a redelivered event is detected by its presence and
    skipped rather than re-executed.
    """

    __tablename__ = "decision_logs"

    id = Column(Integer, primary_key=True)
    stripe_event_id = Column(String, unique=True, nullable=False, index=True)

    invoice_id = Column(String, nullable=False)
    customer_id = Column(String, nullable=False)
    decline_code = Column(String, nullable=True)
    failure_reason = Column(String, nullable=True)

    classification = Column(String, nullable=False)
    action = Column(String, nullable=False)
    reasoning = Column(Text, nullable=False)

    action_result = Column(String, nullable=False)
    action_error = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
