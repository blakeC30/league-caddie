# League Caddie

A web application for running private fantasy golf leagues — replacing spreadsheets and Google Forms with picks, scoring, and standings that update automatically from live PGA Tour data.

## What it does

- Members join a league and pick one golfer per tournament each week
- Points = dollars earned by the picked golfer (majors are 2×)
- No repeat golfers within a season
- Standings update automatically after each tournament completes
- Optional playoff bracket for end-of-season competition

## Repository layout

```
├── backend/          # FastAPI + Python API, scraper, and SQS worker
├── frontend/         # React + TypeScript web app
├── helm/             # Kubernetes Helm chart (league-caddie)
├── localstack-init/  # LocalStack bootstrap scripts (SQS queues, SES identity)
├── docker-compose.yml
└── docs/             # Architecture notes and design documents
```

See [`backend/README.md`](backend/README.md) and [`frontend/README.md`](frontend/README.md) for service-specific details.

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | React 19, TypeScript, Vite, Tailwind CSS v4 |
| Backend | FastAPI, SQLAlchemy 2.0, Alembic, PostgreSQL |
| Scraping | httpx + ESPN unofficial API, APScheduler |
| Messaging | AWS SQS (LocalStack locally) |
| Email | AWS SES |
| Infrastructure | Docker, K3s, Helm 3, AWS EC2 + ECR |

## Local development

**Prerequisites:** Docker Desktop, `docker compose` v2

```bash
# Copy and fill in the backend env file
cp backend/.env.example backend/.env

# Copy and fill in the frontend env file
cp frontend/.env.local.example frontend/.env.local

# Start everything
docker compose up
```

Services:
- Frontend: http://localhost:5173
- API: http://localhost:8000
- API docs: http://localhost:8000/docs
- LocalStack (SQS/SES): http://localhost:4566

## Environments

| Environment | Namespace | Branch | Database |
|---|---|---|---|
| Local | docker compose | — | `league_caddie_dev` |
| Dev | `dev` (K8s) | `dev` | `league_caddie_dev` |
| Production | `prod` (K8s) | `main` | `league_caddie_prod` |

Kubernetes deployments use the Helm chart in `helm/league-caddie/`. Deploy with:

```bash
helm upgrade --install league-caddie helm/league-caddie \
  --namespace prod --create-namespace \
  -f helm/league-caddie/values-prod.yaml \
  --set secrets.secretKey="..." \
  --set secrets.postgresPassword="..." \
  --set certManager.email="your@email.com"
```
