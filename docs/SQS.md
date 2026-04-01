# SQS Event System

Event-driven message processing for playoff automation and pick reminders. The scraper publishes events to SQS; the worker consumes them.

---

## Architecture

| Container | Role | SQS interaction |
|-----------|------|-----------------|
| Scraper | APScheduler time-driven jobs | **Publisher** — publishes events at status transitions and on schedule |
| Worker | SQS consumer loop | **Consumer** — processes events, runs finalization logic, sends emails |

Time-triggered jobs (schedule sync, field sync, live scores) stay on APScheduler. Only event-triggered operations use SQS.

---

## Message Contract

All messages are JSON with a `type` field that routes to the correct handler.

### `TOURNAMENT_IN_PROGRESS`

Published by `sync_tournament()` while a tournament is `in_progress` and any linked playoff draft rounds are unresolved.

```json
{ "type": "TOURNAMENT_IN_PROGRESS", "tournament_id": "uuid" }
```

**Consumer:** `resolve_draft()` for any "drafting" playoff rounds once `any_r1_teed_off()` returns True. Idempotent via `draft_resolved_at` guard.

### `TOURNAMENT_COMPLETED`

Published by `sync_schedule()` on status transition to `completed`.

```json
{ "type": "TOURNAMENT_COMPLETED", "tournament_id": "uuid" }
```

**Consumer:** Full finalization pipeline in order:
1. `score_picks(db, tournament)` — score all regular Pick records
2. `score_round()` — score all PlayoffPick records for linked "locked" playoff rounds
3. `advance_bracket()` — advance the bracket if all members are scored

Each step is idempotent.

### `PICK_REMINDER_SEND`

Published by `_run_pick_reminder_send()` APScheduler job (Wednesday 18:00 UTC). Trigger-only, no payload.

```json
{ "type": "PICK_REMINDER_SEND" }
```

**Consumer:** `send_pick_reminders(db)` — queries all unsent `PickReminder` rows, aggregates by user across leagues/tournaments, sends one consolidated email per user via Resend. Marks reminders as sent.

---

## Guarantees

- **At-least-once delivery** — SQS Standard Queues. All handlers are idempotent.
- **Visibility timeout: 120s** — prevents concurrent processing. If handler crashes, message reappears after timeout.
- **DLQ after 3 failures** — dead-letter queue retains messages for 14 days.
- **No distributed lock needed** — visibility timeout provides single-consumer semantics.

---

## Queue Configuration

### Main Queue

| Setting | Value |
|---------|-------|
| Type | Standard (not FIFO) |
| Visibility timeout | 120 seconds |
| Message retention | 4 days |
| Receive wait time | 20 seconds (long polling) |

### Dead-Letter Queue

| Setting | Value |
|---------|-------|
| Max receive count | 3 |
| Message retention | 14 days |

### Naming

```
Production:   league-caddie-events-prod / league-caddie-events-prod-dlq
Development:  league-caddie-events-dev / league-caddie-events-dev-dlq
```

---

## Local Development (LocalStack)

LocalStack emulates SQS locally. Queues are auto-created by `localstack-init/create-queues.sh` on container startup.

```bash
# Start everything
docker compose up

# Publish a test event manually
docker compose exec localstack awslocal sqs send-message \
  --queue-url http://localhost:4566/000000000000/league-caddie-events-dev \
  --message-body '{"type": "TOURNAMENT_COMPLETED", "tournament_id": "<uuid>"}'

# Check DLQ depth
docker compose exec localstack awslocal sqs get-queue-attributes \
  --queue-url http://localhost:4566/000000000000/league-caddie-events-dev-dlq \
  --attribute-names ApproximateNumberOfMessages
```

---

## Production Setup

### Queue Creation

```bash
aws sqs create-queue --queue-name league-caddie-events-prod-dlq --region us-east-2

DLQ_ARN=$(aws sqs get-queue-attributes \
  --queue-url https://sqs.us-east-2.amazonaws.com/<ACCOUNT_ID>/league-caddie-events-prod-dlq \
  --attribute-names QueueArn --query 'Attributes.QueueArn' --output text)

aws sqs create-queue --queue-name league-caddie-events-prod --region us-east-2 \
  --attributes "{
    \"VisibilityTimeout\": \"120\",
    \"ReceiveMessageWaitTimeSeconds\": \"20\",
    \"RedrivePolicy\": \"{\\\"deadLetterTargetArn\\\":\\\"${DLQ_ARN}\\\",\\\"maxReceiveCount\\\":\\\"3\\\"}\"
  }"
```

### IAM Permissions

EC2 instance profile needs `sqs:SendMessage`, `sqs:ReceiveMessage`, `sqs:DeleteMessage`, `sqs:GetQueueAttributes`, `sqs:ChangeMessageVisibility` on both queues. boto3 picks up instance profile credentials automatically — no access keys in env vars.

### CloudWatch DLQ Alarm

Monitor `ApproximateNumberOfMessagesVisible >= 1` on the DLQ. Set `TreatMissingData: notBreaching` so idle queue shows OK instead of "Insufficient data."

### Environment Variables

Scraper and worker need: `AWS_REGION`, `SQS_QUEUE_URL`. No `AWS_ENDPOINT_URL` in production (boto3 uses real AWS). Worker additionally needs: `RESEND_API_KEY`, `EMAIL_FROM`, `FRONTEND_URL` (for pick reminder emails).
