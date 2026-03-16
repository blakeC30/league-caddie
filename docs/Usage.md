# Capacity & Usage Estimates

## Usage Pattern

Fantasy golf is a **bursty, low-sustained-load** application — the most favorable
pattern for a small instance:

| Time | Activity |
|---|---|
| Sunday night / Monday morning | Tournament finishes; members check standings; pick window opens |
| Tuesday–Wednesday | Pick submission; moderate traffic |
| Thursday morning | Last-minute picks before tee times |
| Thursday–Sunday | Occasional leaderboard checks during live tournament |
| ~80% of the week | Near-zero traffic |

Members typically make 5–7 API calls per session, 1–2 minutes per session.
Most API responses are simple DB reads completing in <10ms.

---

## Instance Comparison

| | t2.micro | t3a.small |
|---|---|---|
| RAM | 1 GB | 2 GB |
| vCPU | 1 (10% baseline) | 2 (40% baseline) |
| Free tier | Yes (750 hrs/mo, 12 months) | No |
| Cost after free tier | ~$8.50/month | ~$13.50/month |
| Comfortable active leagues | 10–20 | 75–200 |
| Total registered users | 100–300 | 1,000–3,000 |
| Simultaneous active users | 5–15 | 50–100 |
| Peak picks per week | 100–200 | 1,000–3,000 |
| Primary bottleneck | Memory (K3s overhead) | DB connection pool / query throughput |
| Appropriate for | Private league, development, testing | Early public launch |

---

## Why K3s is the Binding Constraint on t2.micro

K3s alone consumes ~450–600 MB of the 1 GB:

| Component | Memory |
|---|---|
| k3s server process | 200–350 MB |
| System pods (CoreDNS, Traefik, local-path-provisioner) | 100–200 MB |
| OS + system | 100–150 MB |
| **K3s + system total** | **~450–600 MB** |

Remaining for application containers (~400–500 MB):

| Container | Memory |
|---|---|
| PostgreSQL (`shared_buffers=64MB`, tuned) | 100–150 MB |
| FastAPI backend (1 uvicorn worker) | 80–120 MB |
| Scraper (APScheduler, mostly idle) | 70–100 MB |
| Worker (SQS consumer, mostly idle) | 70–100 MB |
| Nginx (static frontend) | 15–25 MB |
| **App containers total** | **~335–495 MB** |

Combined: **785–1,095 MB** on a 1 GB machine — right at the edge. Memory spikes
(e.g., `results_finalization` running while users hit the API) can cause swap,
which is slow on EBS (~1–5 ms vs RAM's ~0.1 ms) and causes visible latency
spikes.

**The same workload on docker-compose (no K3s) would handle 2–3× more leagues**
on identical hardware, because ~400–500 MB more RAM would be available.

### PostgreSQL Tuning for t2.micro

Set `shared_buffers=64MB` (default is 128MB) to reduce Postgres footprint.
Add to `postgresql.conf` or pass as a startup flag.

---

## t3a.small: Constraint Removed

With 2 GB RAM, after K3s (~500 MB) and app containers (~500 MB), there is
~1 GB of headroom. At this scale:

- Run 2–4 uvicorn workers (better concurrency)
- Increase PostgreSQL `shared_buffers` to 256 MB (hot data cached, faster queries)
- Absorb memory spikes without touching swap
- 4× more CPU burst credits — tournament-day spikes easily handled

At ~200 leagues, the constraint shifts to DB connection pool pressure and query
result set sizes — well beyond what a new public launch will encounter.

---

## CPU Burst Credits

t2.micro earns **6 credits/hour** (10% baseline).
t3a.small earns **24 credits/hour** (40% baseline).

When credits are exhausted, the instance is hard-throttled to its baseline CPU
percentage until credits recharge. For t2.micro this is a real risk on heavy
tournament days with 20+ concurrent leagues. For t3a.small it is not a
practical concern at this scale.

---

## Scaling Path

| Stage | Instance | RAM | Cost/month | When to move |
|---|---|---|---|---|
| Development / testing | t2.micro | 1 GB | Free (12 mo) | — |
| Pre-public / early launch | t3a.small | 2 GB | ~$13.50 | Before going public |
| Early growth | t3a.medium | 4 GB, 2 vCPU | ~$28 | First signs of strain |
| DB bottleneck | Separate RDS (t3.micro) + t3a.medium | — | ~$43 total | When DB becomes the bottleneck |

**Resizing EC2 is a 5–10 minute operation** (stop instance → change type → start).
No code or architecture changes required. All containers come back automatically.

---

## Free Improvements Worth Doing at Launch

**CloudFront CDN (free tier: 1 TB/month transfer)** in front of the static
frontend removes Nginx from the cluster entirely and eliminates frontend traffic
from hitting the EC2 instance. This:

- Frees ~15–25 MB of RAM
- Removes the Nginx container from K3s
- Reduces CPU load for static file serving
- Improves global frontend load time

Worth doing before going public regardless of instance size.

---

## Caveats

- All estimates assume **normal bursty usage**, not a sudden viral spike.
- A Reddit post sending 5,000 users in one hour would overwhelm both instances.
  The fix (vertical resize to t3a.medium) takes 5 minutes — it is a fast
  reaction, not a pre-planned architecture change.
- Numbers assume ~15 members per league average.
- With the SQS worker container added (~80–100 MB), the t2.micro memory math
  becomes slightly tighter. Budget it in when tuning PostgreSQL.
