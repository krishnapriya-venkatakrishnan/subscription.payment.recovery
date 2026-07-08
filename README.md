# Subscription Payment Recovery Agent — Stage 1

A demo AI agent that reacts to failed Stripe subscription payments: it classifies
the failure, decides on a recovery action, executes that action against Stripe
(test mode), and logs its full reasoning to Postgres.

**Stage 1 scope:** one webhook → one agent call → one Stripe action → one log
row. Everything else (email/dunning, approval dashboard, segmentation,
multi-agent split, evals) is deliberately out of scope for now — see
`app/orchestrator.py` for the seam where those will plug in.

## Architecture

```
Stripe (invoice.payment_failed)
        │
        ▼
app/webhook.py        verify signature, extract decline_code/failure_reason
        │
        ▼
app/orchestrator.py   idempotency check (by stripe_event_id) → glue
        │
        ├──▶ app/agent.py            classify + decide (Anthropic, structured JSON)
        │
        ├──▶ app/stripe_actions.py   execute the decided action (Stripe API)
        │
        └──▶ app/models.py           write DecisionLog row (Postgres)
```

Each module only knows about its own concern — `agent.py` has no Stripe or DB
imports, `stripe_actions.py` has no Anthropic imports. This is intentional: a
later stage splits `agent.py` into triage / strategy / action agents without
touching webhook handling or Stripe execution.

## Setup

### 1. Prerequisites

- Python 3.11+
- Local Postgres running (`createdb dunning`, or point `DATABASE_URL` at any
  Postgres instance)
- [Stripe CLI](https://docs.stripe.com/stripe-cli) installed and logged in
  (`stripe login`) — used both to forward webhooks locally and to simulate a
  failed payment
- A Stripe account in **test mode** and an Anthropic API key

### 2. Install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
```

Fill in `.env`:

- `STRIPE_SECRET_KEY` — your **test mode** secret key (starts `sk_test_`)
- `ANTHROPIC_API_KEY` — your Anthropic API key
- `DATABASE_URL` — defaults to `postgresql+psycopg2://postgres:postgres@localhost:5432/dunning`
- `STRIPE_WEBHOOK_SECRET` — leave as-is for now, you'll get the real value in the next step

### 4. Run the server

```bash
uvicorn app.main:app --reload
```

This also creates the `decision_logs` table on startup if it doesn't exist.

### 5. Forward Stripe webhooks to your local server

In a separate terminal:

```bash
stripe listen --forward-to localhost:8000/webhooks/stripe
```

This prints a webhook signing secret (`whsec_...`) — copy it into `.env` as
`STRIPE_WEBHOOK_SECRET` and restart `uvicorn`.

### 6. Simulate a failed payment

With `stripe listen` still running, in a third terminal:

```bash
stripe trigger invoice.payment_failed
```

This creates a real (test-mode) customer, invoice, and failed charge in your
Stripe account and fires the webhook at your local server. Watch the
`uvicorn` terminal — you should see the request come in, then a JSON response
like:

```json
{
  "status": "processed",
  "stripe_event_id": "evt_...",
  "classification": "other",
  "action": "schedule_smart_retry",
  "reasoning": "...",
  "action_result": "success"
}
```

Re-run `stripe trigger invoice.payment_failed` with the *same* event (e.g. by
using the Stripe CLI's replay, or by having `stripe listen` redeliver) and
you should instead see `"status": "already_processed"` — confirming the
idempotency guard works.

### 7. Inspect the decision log

```bash
psql dunning -c 'select stripe_event_id, classification, action, action_result, reasoning from decision_logs order by created_at desc limit 5;'
```

## Notes on the decline reason `stripe trigger` produces

`stripe trigger invoice.payment_failed` generates a generic test decline —
the exact `decline_code`/`failure_reason` values depend on Stripe's fixture
and often won't specifically be "insufficient funds." To reliably exercise
the `insufficient_funds` classification path, create a real test-mode
subscription using Stripe's dedicated test card `4000 0000 0000 9995`
(always declines as insufficient funds) via the Stripe Dashboard or API, then
let its first invoice fail naturally.

## Design notes

- **Idempotency**: `decision_logs.stripe_event_id` has a unique constraint.
  The orchestrator checks for an existing row before calling the agent; if
  Stripe redelivers the same event, processing is skipped and `null`/no-op is
  returned. A `DecisionLog` row is only ever written once the full pipeline
  (agent decision + action attempt) has completed — if the Anthropic call
  itself fails, nothing is written and the webhook returns 5xx so Stripe
  retries later.
- **Structured output**: the agent uses `output_config.format` (via the
  Anthropic SDK's `messages.parse()` helper) to constrain the model's
  response to a JSON schema — no prompt-engineered JSON, no fragile parsing.
  The schema lives in `app/schemas.py::AgentDecision` and is intentionally
  small for Stage 1; it's designed to grow (more actions, more fields)
  without breaking existing callers.
- **Stripe action**: `stripe.Invoice.pay(invoice_id)` reattempts the charge
  against the invoice's default payment method — the real "smart retry"
  action, not a simulation.
