# SQS Migration Plan

## Overview

This document describes the plan to migrate playoff automation from APScheduler
polling jobs to event-driven SQS message processing. The scraper's time-based
jobs (schedule sync, field sync, live score sync) remain on APScheduler — those
are genuinely time-triggered. Only the event-triggered operations (playoff draft
resolution, playoff scoring, bracket advancement) move to SQS.

---

## Why This Matters

The APScheduler approach has three hard limits that SQS solves:

| Problem | APScheduler | SQS |
|---|---|---|
| Two scraper pods → race conditions | Unsafe — no cross-process locking | Safe — at-most-once processing per message via visibility timeout |
| Playoff resolution delay | Up to 5 minutes (polling interval) | Seconds after the trigger event |
| Silent failures | Logged but no retry, no alert | DLQ after N retries; monitorable |

---

## Architecture: What Changes, What Stays

### Stays on APScheduler (time-triggered)

| Job | Schedule | Reason |
|---|---|---|
| `schedule_sync` | Daily 06:00 UTC | No external trigger; must run on a clock |
| `field_sync_d2/d1/d0` | Daily at set times | Same — clock-based |
| `live_score_sync` | Every 5 min | Must run continuously during tournaments |
| `results_finalization` | 3× daily | **Kept as a safety net** — catches anything SQS missed (scraper down, message lost before DLQ) |

### Moves to SQS (event-triggered)

| Current job | Replaced by | Trigger |
|---|---|---|
| `_run_playoff_draft_resolve` | SQS consumer | `sync_tournament()` detects `in_progress` |
| `_run_playoff_bracket_advance` | SQS consumer | `score_picks()` completes for a tournament |

A third operation that was never automated — `score_round()` — is added to the
SQS consumer pipeline, completing the full playoff finalization chain.

---

## Message Contract

All SQS messages are JSON with a `type` field that routes to the correct handler.

### `TOURNAMENT_IN_PROGRESS`

Published by `sync_tournament()` when it flips a tournament's status to
`in_progress` for the first time.

```json
{
  "type": "TOURNAMENT_IN_PROGRESS",
  "tournament_id": "uuid"
}
```

**Consumer action:** Find all playoff rounds linked to this `tournament_id` with
`status == "drafting"` and `any_r1_teed_off() == True`. Call `resolve_draft()`
for each. Idempotent — `resolve_draft()` guards against double-resolution via
the `draft_resolved_at` timestamp check.

### `TOURNAMENT_COMPLETED`

Published by `sync_tournament()` when it flips a tournament's status to
`completed` for the first time.

```json
{
  "type": "TOURNAMENT_COMPLETED",
  "tournament_id": "uuid"
}
```

**Consumer action:** Run the full finalization pipeline in order:
1. `score_picks(db, tournament)` — score all regular `Pick` records
2. For each linked playoff round with `status == "locked"`: call `score_round()`
3. If all pod members are scored after step 2: call `advance_bracket()`

Each step is idempotent — safe to replay if SQS delivers the message more than once.

---

## Distributed Systems Guarantees

### At-Least-Once Delivery

SQS Standard Queues guarantee at-least-once delivery, not exactly-once. A
message may be delivered more than once (rare but must be handled). Every
consumer handler must be **idempotent** — running it twice produces the same
result as running it once.

All existing service functions already satisfy this:
- `resolve_draft()` checks `status == "drafting"` before acting
- `score_picks()` only processes picks where `points_earned IS NULL`
- `score_round()` checks `status == "locked"` before acting
- `advance_bracket()` checks `status == "locked"` before acting

No additional idempotency code is needed.

### Visibility Timeout

When a consumer receives a message, SQS makes it invisible to other consumers
for the visibility timeout duration. If the consumer crashes mid-processing, the
message reappears after the timeout and another consumer retries it.

Set to **120 seconds** — 2× the expected maximum processing time for the
heaviest operation (`score_picks()` includes ESPN API calls that can take 30–60
seconds).

### Dead-Letter Queue (DLQ)

After **3 failed delivery attempts**, the message moves to the DLQ instead of
being retried indefinitely. The DLQ holds failed messages for **14 days** for
inspection and manual re-driving.

Monitor the DLQ depth in CloudWatch. A non-zero DLQ depth should alert the
admin — it means at least one finalization operation failed permanently and may
need manual intervention.

### No Distributed Lock Required

SQS visibility timeout replaces the need for distributed locks. When one
consumer pod receives a message and begins processing, that message is invisible
to all other pods until processing completes. If processing succeeds and the
message is deleted, no other pod ever sees it. If processing fails, the message
reappears and is retried — but the idempotent handlers ensure safe re-execution.

### Message Deduplication (Publishing Side)

`sync_tournament()` is called repeatedly during a live tournament (every 5
minutes by `live_score_sync`). The status flip from `scheduled` → `in_progress`
should only publish one `TOURNAMENT_IN_PROGRESS` message, not one per call.

Implementation: check the previous status before publishing. Only publish when
the status actually changed in this sync call:

```python
# In sync_tournament(), after the status upsert:
if previous_status != "in_progress" and tournament.status == "in_progress":
    sqs_client.publish("TOURNAMENT_IN_PROGRESS", tournament_id=str(tournament.id))

if previous_status != "completed" and tournament.status == "completed":
    sqs_client.publish("TOURNAMENT_COMPLETED", tournament_id=str(tournament.id))
```

This keeps the queue clean and prevents hundreds of redundant messages per day.

---

## Queue Configuration

### Main Queue

| Setting | Value | Reason |
|---|---|---|
| Type | Standard (not FIFO) | Ordering not required; cheaper; idempotent handlers handle duplicates |
| Visibility timeout | 120 seconds | 2× max expected processing time |
| Message retention | 4 days | Default; enough time to investigate |
| Receive message wait time | 20 seconds | Long polling — reduces empty receive calls and cost |

### Dead-Letter Queue

| Setting | Value |
|---|---|
| Max receive count | 3 |
| Message retention | 14 days |

### Naming

```
Production:   fantasy-golf-events
              fantasy-golf-events-dlq
Development:  fantasy-golf-events-dev
              fantasy-golf-events-dev-dlq
```

---

## Changes to `scheduler.py`

### Remove

- `_run_playoff_draft_resolve()` — replaced by SQS consumer
- `_run_playoff_bracket_advance()` — replaced by SQS consumer

### Keep (unchanged)

- `_run_schedule_sync()`
- `_run_field_sync()`
- `_run_live_score_sync()`
- `_run_results_finalization()` — kept as a safety net / catch-up job

### Modify

`_run_live_score_sync()` and the underlying `sync_tournament()` gain SQS
publish calls at the status transition points (see deduplication section above).

---

## New Files

```
fantasy-golf-backend/
  app/
    services/
      sqs.py          ← SQS client wrapper (publish + consume)
    worker_main.py    ← SQS consumer entrypoint (separate process/container)
```

### `app/services/sqs.py`

Thin wrapper around `boto3` that:
- Reads `AWS_ENDPOINT_URL` from env (set to `http://localstack:4566` locally,
  unset in production so boto3 uses the real AWS endpoint)
- Exposes `publish(event_type, **payload)` and `consume(handler)` functions
- Handles serialization / deserialization

```python
import boto3, json, os, logging
from typing import Callable

log = logging.getLogger(__name__)

def _get_client():
    kwargs = {"region_name": os.environ["AWS_REGION"]}
    endpoint = os.environ.get("AWS_ENDPOINT_URL")   # set locally, absent in prod
    if endpoint:
        kwargs["endpoint_url"] = endpoint
    return boto3.client("sqs", **kwargs)

def get_queue_url() -> str:
    return os.environ["SQS_QUEUE_URL"]

def publish(event_type: str, **payload) -> None:
    client = _get_client()
    body = json.dumps({"type": event_type, **payload})
    client.send_message(QueueUrl=get_queue_url(), MessageBody=body)
    log.info("SQS published: %s", event_type)

def consume(handler: Callable[[dict], None], poll_interval_s: int = 20) -> None:
    """
    Long-polling consumer loop. Runs forever; call from worker_main.py.
    handler receives the parsed message dict and must not raise on known errors
    (raise only for unexpected failures that should trigger a retry).
    """
    client = _get_client()
    queue_url = get_queue_url()
    log.info("SQS consumer started on %s", queue_url)
    while True:
        response = client.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=10,
            WaitTimeSeconds=poll_interval_s,  # long polling
            VisibilityTimeout=120,
        )
        for msg in response.get("Messages", []):
            body = json.loads(msg["Body"])
            receipt = msg["ReceiptHandle"]
            try:
                handler(body)
                client.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt)
            except Exception as exc:
                log.error("SQS handler failed for %s: %s", body.get("type"), exc, exc_info=True)
                # Do NOT delete — message will reappear after visibility timeout
                # and be retried (up to max_receive_count, then DLQ)
```

### `app/worker_main.py`

Entrypoint for the SQS consumer process. Separate from `scraper_main.py` so the
scraper and consumer can scale independently.

```python
from app.services.sqs import consume
from app.database import SessionLocal
from app.models import PlayoffRound, Tournament, TournamentStatus
from app.services.scraper import score_picks
from app.services.playoff import resolve_draft, score_round, advance_bracket, any_r1_teed_off

def handle(message: dict) -> None:
    event_type = message.get("type")
    db = SessionLocal()
    try:
        if event_type == "TOURNAMENT_IN_PROGRESS":
            _handle_tournament_in_progress(db, message["tournament_id"])
        elif event_type == "TOURNAMENT_COMPLETED":
            _handle_tournament_completed(db, message["tournament_id"])
        else:
            # Unknown event — log and delete (don't retry indefinitely)
            import logging; logging.getLogger(__name__).warning("Unknown SQS event: %s", event_type)
    finally:
        db.close()

def _handle_tournament_in_progress(db, tournament_id: str) -> None:
    rounds = (
        db.query(PlayoffRound)
        .filter(
            PlayoffRound.tournament_id == tournament_id,
            PlayoffRound.status == "drafting",
            PlayoffRound.draft_resolved_at.is_(None),
        )
        .all()
    )
    for playoff_round in rounds:
        if any_r1_teed_off(db, playoff_round.tournament_id):
            resolve_draft(db, playoff_round)

def _handle_tournament_completed(db, tournament_id: str) -> None:
    tournament = db.query(Tournament).filter_by(id=tournament_id).first()
    if not tournament:
        return
    # 1. Score regular picks
    score_picks(db, tournament)
    # 2. Score + advance any linked playoff round
    playoff_round = (
        db.query(PlayoffRound)
        .filter_by(tournament_id=tournament_id, status="locked")
        .first()
    )
    if not playoff_round:
        return
    score_round(db, playoff_round)
    # advance_bracket checks internally that all members are scored
    advance_bracket(db, playoff_round)

if __name__ == "__main__":
    consume(handle)
```

---

## Local Development with LocalStack

### What LocalStack Is

LocalStack is a free, open-source Docker container that emulates AWS services
locally. With it, the local and production code paths are **identical** — only
the endpoint URL changes. There is no scheduler-vs-SQS divergence to worry about.

### docker-compose additions

Add the following to `docker-compose.yml`:

```yaml
  localstack:
    image: localstack/localstack:3
    ports:
      - "4566:4566"
    environment:
      - SERVICES=sqs
      - AWS_DEFAULT_REGION=us-east-1
      - LOCALSTACK_HOST=localstack
    volumes:
      - ./localstack-init:/etc/localstack/init/ready.d   # bootstrap script (see below)
    healthcheck:
      test: ["CMD", "awslocal", "sqs", "list-queues"]
      interval: 5s
      timeout: 5s
      retries: 10

  worker:
    build:
      context: ./fantasy-golf-backend
      dockerfile: Dockerfile.dev
    volumes:
      - ./fantasy-golf-backend:/app
    env_file:
      - ./fantasy-golf-backend/.env
    environment:
      DATABASE_URL: postgresql://fantasygolf:fantasygolf@postgres:5432/fantasygolf_dev
      AWS_ENDPOINT_URL: http://localstack:4566
      AWS_REGION: us-east-1
      AWS_ACCESS_KEY_ID: test       # LocalStack accepts any value
      AWS_SECRET_ACCESS_KEY: test
      SQS_QUEUE_URL: http://localstack:4566/000000000000/fantasy-golf-events-dev
    command: ["python", "-m", "app.worker_main"]
    depends_on:
      postgres:
        condition: service_healthy
      localstack:
        condition: service_healthy
    restart: unless-stopped

  scraper:
    # existing config — add these env vars:
    environment:
      DATABASE_URL: postgresql://fantasygolf:fantasygolf@postgres:5432/fantasygolf_dev
      AWS_ENDPOINT_URL: http://localstack:4566
      AWS_REGION: us-east-1
      AWS_ACCESS_KEY_ID: test
      AWS_SECRET_ACCESS_KEY: test
      SQS_QUEUE_URL: http://localstack:4566/000000000000/fantasy-golf-events-dev
```

### LocalStack Bootstrap Script

Create `localstack-init/create-queues.sh`. LocalStack runs scripts in
`/etc/localstack/init/ready.d/` automatically after startup:

```bash
#!/bin/bash
# Create the DLQ first, then the main queue with a redrive policy.
awslocal sqs create-queue \
  --queue-name fantasy-golf-events-dev-dlq \
  --region us-east-1

DLQ_ARN=$(awslocal sqs get-queue-attributes \
  --queue-url http://localhost:4566/000000000000/fantasy-golf-events-dev-dlq \
  --attribute-names QueueArn \
  --query 'Attributes.QueueArn' \
  --output text)

awslocal sqs create-queue \
  --queue-name fantasy-golf-events-dev \
  --region us-east-1 \
  --attributes "{
    \"VisibilityTimeout\": \"120\",
    \"ReceiveMessageWaitTimeSeconds\": \"20\",
    \"RedrivePolicy\": \"{\\\"deadLetterTargetArn\\\":\\\"${DLQ_ARN}\\\",\\\"maxReceiveCount\\\":\\\"3\\\"}\"
  }"

echo "SQS queues created."
```

Make it executable: `chmod +x localstack-init/create-queues.sh`

### Local Workflow

```bash
# Start everything
docker-compose up

# Publish a test event manually (useful for testing handlers without the scraper)
docker-compose exec localstack awslocal sqs send-message \
  --queue-url http://localhost:4566/000000000000/fantasy-golf-events-dev \
  --message-body '{"type": "TOURNAMENT_IN_PROGRESS", "tournament_id": "<uuid>"}'

# Check DLQ depth (non-zero = something failed)
docker-compose exec localstack awslocal sqs get-queue-attributes \
  --queue-url http://localhost:4566/000000000000/fantasy-golf-events-dev-dlq \
  --attribute-names ApproximateNumberOfMessages
```

---

## AWS Production Setup

### Queue Creation

Create both queues in the same region as the EC2 instance (no cross-region
charges). Use the AWS console or CLI:

```bash
# DLQ
aws sqs create-queue \
  --queue-name fantasy-golf-events-dlq \
  --region us-east-1

# Main queue with redrive policy (replace DLQ ARN)
aws sqs create-queue \
  --queue-name fantasy-golf-events \
  --region us-east-1 \
  --attributes '{
    "VisibilityTimeout": "120",
    "ReceiveMessageWaitTimeSeconds": "20",
    "RedrivePolicy": "{\"deadLetterTargetArn\":\"arn:aws:sqs:us-east-1:<account>:fantasy-golf-events-dlq\",\"maxReceiveCount\":\"3\"}"
  }'
```

### IAM Role (EC2 Instance Profile)

The EC2 instance already has an IAM role (for ECR access). Add an inline policy
or attach a managed policy with these permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "sqs:SendMessage",
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
        "sqs:GetQueueAttributes",
        "sqs:ChangeMessageVisibility"
      ],
      "Resource": [
        "arn:aws:sqs:us-east-1:<account>:fantasy-golf-events",
        "arn:aws:sqs:us-east-1:<account>:fantasy-golf-events-dlq"
      ]
    }
  ]
}
```

boto3 picks up the instance profile credentials automatically via the instance
metadata service (IMDS). **No access keys stored in environment variables or
secrets in production.**

### Helm / K8s Environment Variables

Add to the scraper and worker deployments in `helm/fantasy-golf/`:

```yaml
# No AWS_ENDPOINT_URL in production — boto3 uses real AWS
- name: AWS_REGION
  value: us-east-1
- name: SQS_QUEUE_URL
  value: https://sqs.us-east-1.amazonaws.com/<account>/fantasy-golf-events
```

The `worker` pod is a new Kubernetes Deployment alongside the existing `scraper`
Deployment. Both use the same Docker image; they differ only in the `command`:

```yaml
# scraper deployment
command: ["python", "-m", "app.scraper_main"]

# worker deployment
command: ["python", "-m", "app.worker_main"]
```

### CloudWatch Monitoring

Set a CloudWatch alarm on:

- **Metric**: `ApproximateNumberOfMessagesVisible` on `fantasy-golf-events-dlq`
- **Threshold**: >= 1
- **Action**: SNS email alert to the admin

This is the primary operational signal that something in the finalization
pipeline has failed permanently.

---

## boto3 Dependency

Add `boto3` to `fantasy-golf-backend/requirements.txt`. It is already an AWS
standard library with no additional cost and is pre-installed in most AWS
environments.

LocalStack is not a Python dependency — it runs as a Docker container.

---

## Migration Steps (Ordered)

1. Add `boto3` to `requirements.txt`
2. Write `app/services/sqs.py` (publish + consume)
3. Write `app/worker_main.py` (event handlers)
4. Add LocalStack + worker service to `docker-compose.yml`
5. Add bootstrap script `localstack-init/create-queues.sh`
6. Add SQS publish calls to `sync_tournament()` at status transition points
7. Test locally: start docker-compose, manually send test messages, verify handlers fire
8. Remove `_run_playoff_draft_resolve` and `_run_playoff_bracket_advance` from `scheduler.py`
9. Create SQS queues in AWS
10. Attach SQS permissions to EC2 IAM role
11. Add worker Deployment to Helm chart
12. Add `SQS_QUEUE_URL` and `AWS_REGION` env vars to Helm values (scraper + worker)
13. Deploy to dev namespace; smoke test with a manually published message
14. Deploy to prod

---

## Summary of Containers After Migration

| Container | Runs | Purpose |
|---|---|---|
| `backend` | FastAPI | HTTP API |
| `scraper` | APScheduler | Time-triggered: schedule/field/live sync, results finalization (safety net) |
| `worker` | SQS consumer | Event-triggered: playoff resolution, scoring, bracket advancement |
| `postgres` | PostgreSQL | Database |
| `localstack` | LocalStack | Local SQS emulation (dev only) |
