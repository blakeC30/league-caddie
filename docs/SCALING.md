# Scaling Plan — League Caddie

A phased scaling roadmap tied to concrete metrics. Each stage describes **when** to act, **what** to change, and **why** — so decisions are data-driven, not premature.

## Current Architecture (Baseline)

All services run on a single **t3a.medium** EC2 instance (2 vCPU, 4 GB RAM) running K3s.

| Component | Replicas | CPU req/limit | Memory req/limit | DB Pool |
|-----------|----------|---------------|------------------|---------|
| API | 1 | 100m / 500m | 128Mi / 512Mi | 10 + 20 overflow |
| Scraper | 1 | 50m / 200m | 64Mi / 256Mi | 2 + 3 overflow |
| Worker | 1 | 50m / 200m | 64Mi / 256Mi | 2 + 5 overflow |
| Frontend | 1 | 50m / 200m | 32Mi / 64Mi | — |
| PostgreSQL | 1 | — | — | — |

- **Ingress**: Traefik (K3s built-in), TLS via cert-manager + Let's Encrypt
- **Storage**: 30 GB EBS (local-path PVC), PostgreSQL 10 Gi allocated
- **Deploy strategy**: RollingUpdate (maxUnavailable=0, maxSurge=1) for all except Postgres (Recreate)
- **Uvicorn workers**: 2

---

## Stage 0: Current (1–20 leagues, ~100–500 users)

**Where we are today.** Single node, single replica per service, no redundancy.

### Monitoring to Set Up Now

Before scaling, you need visibility. Without metrics, you're guessing.

1. **Node-level monitoring** — install `metrics-server` in K3s:
   ```bash
   kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
   ```
   Then check usage with `kubectl top nodes` and `kubectl top pods`.

2. **CloudWatch basic metrics** — EC2 dashboard shows CPU, network, disk I/O. Enable **detailed monitoring** ($2.10/month) for 1-minute granularity instead of 5-minute.

3. **PostgreSQL monitoring** — add `pg_stat_statements` extension and periodically check:
   ```sql
   SELECT query, calls, mean_exec_time, total_exec_time
   FROM pg_stat_statements ORDER BY total_exec_time DESC LIMIT 20;
   ```

4. **Application-level** — log slow requests. Add timing middleware to FastAPI:
   - Requests > 1s → WARNING log
   - Requests > 5s → ERROR log

### Triggers to Watch

| Metric | Current | Warning | Action needed |
|--------|---------|---------|---------------|
| Node CPU (sustained) | ~15% | > 60% for 10+ min | Move to Stage 1 |
| Node memory | ~2.5 GB used | > 3.2 GB (80%) | Move to Stage 1 |
| API response time (p95) | < 200ms | > 500ms | Investigate queries first, then Stage 1 |
| DB connections (active) | ~5 | > 25 of 30 pool | Increase pool or add replicas |
| Disk usage | ~5 GB | > 24 GB (80% of 30 GB) | Expand EBS volume |
| Pod restarts | 0 | > 3/hour | Investigate OOM or crash loops |

---

## Stage 1: Vertical Scaling (20–100 leagues, ~500–2,000 users)

### When to trigger

- Node CPU sustained > 60% during tournament weekends
- Node memory > 3.2 GB
- API p95 latency > 500ms under normal load

### What to do

#### 1.1 Upgrade EC2 instance

Move from **t3a.medium** (2 vCPU, 4 GB) to **t3a.large** (2 vCPU, 8 GB):

```bash
# Stop the instance first
aws ec2 stop-instances --instance-ids <instance-id> --region us-east-2
aws ec2 modify-instance-attribute --instance-id <instance-id> --instance-type '{"Value":"t3a.large"}' --region us-east-2
aws ec2 start-instances --instance-ids <instance-id> --region us-east-2
```

**Cost**: ~$55/month (vs ~$27/month for t3a.medium). No architecture changes needed.

#### 1.2 Increase API resources and Uvicorn workers

Update `values-prod.yaml` or Helm `--set` overrides:

```yaml
api:
  replicas: 1
  resources:
    requests:
      cpu: "200m"
      memory: "256Mi"
    limits:
      cpu: "1000m"
      memory: "1Gi"
```

Update backend Dockerfile to use 4 Uvicorn workers (matches 2 vCPU with headroom):
```dockerfile
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

#### 1.3 Increase DB pool size

In `api-deployment.yaml` environment:
```yaml
DB_POOL_SIZE: "20"
DB_MAX_OVERFLOW: "30"
```

Total connections per API pod: 50. With 1 pod, PostgreSQL handles this easily.

#### 1.4 Expand EBS volume if needed

```bash
aws ec2 modify-volume --volume-id <vol-id> --size 50 --region us-east-2
# Then on the instance:
sudo growpart /dev/nvme0n1 1
sudo xfs_growfs /
```

#### 1.5 Add PostgreSQL connection pooling (optional at this stage)

Deploy PgBouncer as a sidecar or separate pod to multiplex application connections onto fewer PostgreSQL connections:

```yaml
# Add as a sidecar in api-deployment.yaml
- name: pgbouncer
  image: bitnami/pgbouncer:latest
  env:
    - name: PGBOUNCER_DATABASE
      value: league_caddie_prod
    - name: POSTGRESQL_HOST
      value: postgres
    - name: PGBOUNCER_POOL_MODE
      value: transaction
    - name: PGBOUNCER_MAX_CLIENT_CONN
      value: "200"
    - name: PGBOUNCER_DEFAULT_POOL_SIZE
      value: "20"
```

This becomes critical in Stage 2 when multiple API replicas each have their own pool.

### Estimated Cost

~$55–65/month (t3a.large + 50 GB EBS + data transfer).

---

## Stage 2: Horizontal API Scaling (100–500 leagues, ~2,000–10,000 users)

### When to trigger

- Single API pod CPU sustained > 70% (even after vertical scale)
- API p95 latency > 500ms with 4 Uvicorn workers
- Tournament weekends cause noticeable slowdowns (pick submission spikes)
- Memory pressure on the node from running all pods on one machine

### What to do

#### 2.1 Scale API replicas

```yaml
api:
  replicas: 3
```

Traefik automatically load-balances across pods. The RollingUpdate strategy (maxUnavailable=0, maxSurge=1) ensures zero-downtime deploys.

**Important**: Each replica gets its own DB connection pool. 3 replicas x 50 connections = 150 potential connections. PostgreSQL's default `max_connections` is 100 — you **must** either:
- Increase PostgreSQL `max_connections` to 200+
- Deploy PgBouncer (recommended — see 1.5 above)

Add to `postgres-deployment.yaml` args:
```yaml
args: ["-c", "max_connections=200"]
```

#### 2.2 Scale frontend replicas

```yaml
frontend:
  replicas: 2
```

Frontend pods are stateless nginx — scale freely. Minimal resource cost.

#### 2.3 Deploy PgBouncer (required at this stage)

Move PgBouncer from optional sidecar to a standalone Deployment:

```yaml
# pgbouncer-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: pgbouncer
spec:
  replicas: 1
  template:
    spec:
      containers:
        - name: pgbouncer
          image: bitnami/pgbouncer:latest
          resources:
            requests: { cpu: "50m", memory: "32Mi" }
            limits: { cpu: "200m", memory: "128Mi" }
```

Point all API/Scraper/Worker `DATABASE_URL` to `pgbouncer:5432` instead of `postgres:5432`.

#### 2.4 Add session affinity for WebSocket-like features (if added)

If you add real-time features (polling is fine without this), configure Traefik sticky sessions:

```yaml
# ingress annotation
traefik.ingress.kubernetes.io/service.sticky.cookie: "true"
```

#### 2.5 Consider moving PostgreSQL to RDS

At this user count, database reliability matters. A single PostgreSQL Deployment on K3s has:
- No automated backups (unless you script `pg_dump`)
- No point-in-time recovery
- No failover

**Option A — RDS PostgreSQL** (managed):
- db.t3.micro: ~$15/month (free tier eligible for 12 months)
- db.t3.small: ~$30/month
- Automated backups, Multi-AZ failover, monitoring built-in

**Option B — Stay on K3s but add backups**:
- CronJob running `pg_dump` to S3 daily
- ~$1/month for S3 storage
- Manual failover (downtime if disk fails)

At 2,000–10,000 users, **Option A is strongly recommended**. The operational burden of self-managed PostgreSQL isn't worth saving $15–30/month.

If you move to RDS:
- Remove `postgres-deployment.yaml`, `postgres-service.yaml`, PVC
- Update `DATABASE_URL` to point to RDS endpoint
- Update security group to allow K3s node → RDS on port 5432

### Estimated Cost

~$100–150/month (t3a.large + 3 API pods + RDS t3.small + EBS + data transfer).

---

## Stage 3: Multi-Node Cluster (500–2,000 leagues, ~10,000–50,000 users)

### When to trigger

- Single EC2 instance can't fit all pods (CPU/memory exhausted even on t3a.large)
- Need high availability (single node failure = total outage)
- RDS is already in use, but API latency still climbing
- Tournament weekend traffic spikes cause pod evictions

### What to do

#### 3.1 Add worker nodes to K3s

K3s supports multi-node clusters. Add 1–2 worker nodes:

```bash
# On new EC2 instance (t3a.medium or t3a.large):
curl -sfL https://get.k3s.io | K3S_URL=https://<master-ip>:6443 K3S_TOKEN=<node-token> sh -
```

K3s scheduler distributes pods across nodes automatically. Use node affinity to pin PostgreSQL (if still self-hosted) to a specific node with fast storage.

**Node layout (3 nodes)**:
| Node | Role | Instance | Pods |
|------|------|----------|------|
| Node 1 | Master + workload | t3a.large | API x1, Frontend x1, Scraper, Worker |
| Node 2 | Worker | t3a.medium | API x2, Frontend x1 |
| Node 3 | Worker (optional) | t3a.medium | API x1, overflow |

#### 3.2 Move to EBS CSI driver for persistent storage

Replace `local-path` provisioner with AWS EBS CSI driver for cross-node persistent volumes:

```bash
kubectl apply -k "github.com/kubernetes-sigs/aws-ebs-csi-driver/deploy/kubernetes/overlays/stable/?ref=release-1.25"
```

Create a StorageClass:
```yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: ebs-sc
provisioner: ebs.csi.aws.com
parameters:
  type: gp3
  encrypted: "true"
volumeBindingMode: WaitForFirstConsumer
```

#### 3.3 Add a load balancer

Replace direct EC2 access with an AWS ALB or NLB:

**Option A — AWS ALB** (Application Load Balancer):
- ~$22/month base + $0.008/LCU-hour
- Handles TLS termination (offload from Traefik)
- Health checks, access logs, WAF integration
- Good for HTTP/HTTPS traffic

**Option B — Keep Traefik + NLB**:
- NLB is ~$16/month (cheaper)
- Traefik still handles TLS and routing
- NLB just forwards TCP to the K3s node(s)

For cost-consciousness, **Option B** (NLB + Traefik) is recommended. Traefik already works well and NLB is simpler.

#### 3.4 Add pod anti-affinity

Ensure API pods spread across nodes:

```yaml
# api-deployment.yaml
affinity:
  podAntiAffinity:
    preferredDuringSchedulingIgnoredDuringExecution:
      - weight: 100
        podAffinityTerm:
          labelSelector:
            matchExpressions:
              - key: app.kubernetes.io/component
                operator: In
                values: ["api"]
          topologyKey: kubernetes.io/hostname
```

#### 3.5 Scale scraper carefully

The scraper **must remain at 1 replica** — APScheduler is not distributed. Running 2 scrapers causes duplicate ESPN API calls, duplicate SQS events, and potential data corruption.

If scraper performance is a bottleneck (unlikely — ESPN calls are I/O bound, not CPU):
- Increase scraper resources (CPU/memory limits)
- Increase `_FETCH_WORKERS` thread pool size in `scraper.py`
- Add more concurrent tournament syncs in `full_sync()`

#### 3.6 Worker scaling considerations

The worker **should stay at 1 replica** unless you add distributed locking. The SQS visibility timeout (120s) prevents duplicate processing within a single message, but multiple workers could process different messages that affect the same playoff bracket concurrently (e.g., two `TOURNAMENT_COMPLETED` events for back-to-back tournaments).

If you need worker throughput:
- Increase `DB_POOL_SIZE` for the worker
- Process messages in parallel within a single worker (thread pool)
- Add advisory locks per league_id before bracket operations

### Estimated Cost

~$200–350/month (3 nodes + RDS + NLB + EBS + data transfer).

---

## Stage 4: Production-Grade (2,000+ leagues, ~50,000+ users)

### When to trigger

- Need 99.9%+ uptime SLA
- Regulatory or contractual reliability requirements
- Revenue justifies infrastructure investment
- Geographic expansion (users outside US)

### What to do

#### 4.1 Upgrade to EKS (managed Kubernetes)

K3s is excellent for cost, but at scale you want:
- Managed control plane (AWS handles etcd, API server)
- IAM integration for pod-level permissions (IRSA)
- Managed node groups with auto-scaling
- Better observability (CloudWatch Container Insights)

**Cost**: $72/month for the EKS control plane + node costs.

**Migration path**:
1. Set up EKS cluster with `eksctl`
2. Deploy the same Helm chart (no application changes needed)
3. Point DNS to new cluster's load balancer
4. Decommission K3s node

#### 4.2 Horizontal Pod Autoscaler (HPA)

Auto-scale API pods based on CPU:

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: api-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: league-caddie-api
  minReplicas: 3
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
```

#### 4.3 RDS Multi-AZ

Upgrade RDS to Multi-AZ for automatic failover:
- ~$60/month (db.t3.small Multi-AZ)
- Automatic failover in ~60 seconds
- Synchronous replication to standby

Add a **read replica** if read-heavy queries (standings, leaderboards) are bottlenecking:
- Point standings/leaderboard queries to the read replica
- Requires application-level read/write split (separate `DATABASE_READ_URL`)

#### 4.4 Redis for caching and session management

Deploy Redis (ElastiCache or self-hosted) for:
- **Standings cache**: move from DB column (`season.standings_cache`) to Redis with TTL
- **Rate limiting**: move from in-memory to Redis (distributed across API pods)
- **Session data**: if JWT refresh tokens need server-side invalidation

ElastiCache t3.micro: ~$13/month.

#### 4.5 CDN for frontend

Put CloudFront in front of the frontend:
- Global edge caching for static assets (JS, CSS, images)
- Reduces load on nginx pods
- Better latency for users outside `us-east-2`
- ~$0–5/month at this scale (free tier: 1 TB/month)

#### 4.6 Observability stack

Deploy a monitoring stack:

**Option A — AWS native**:
- CloudWatch Container Insights ($0.30/container/hour — can add up)
- CloudWatch Logs for application logs
- X-Ray for distributed tracing (free tier: 100K traces/month)

**Option B — Open source** (recommended for cost):
- **Prometheus** + **Grafana** on K8s (free, self-hosted)
- Prometheus scrapes metrics from pods, node-exporter, kube-state-metrics
- Grafana dashboards for API latency, error rates, DB connections, pod health
- **Loki** for centralized log aggregation

#### 4.7 Automated backups

If not on RDS:
```yaml
# CronJob: pg_dump to S3 every 6 hours
apiVersion: batch/v1
kind: CronJob
metadata:
  name: pg-backup
spec:
  schedule: "0 */6 * * *"
  jobTemplate:
    spec:
      template:
        spec:
          containers:
            - name: backup
              image: postgres:15-alpine
              command:
                - /bin/sh
                - -c
                - |
                  pg_dump -h postgres -U league_caddie league_caddie_prod | \
                  gzip | aws s3 cp - s3://league-caddie-backups/$(date +%Y%m%d-%H%M).sql.gz
```

### Estimated Cost

~$400–700/month (EKS + Multi-AZ RDS + ElastiCache + NLB + nodes + CDN).

---

## Stage 5: High Scale (10,000+ leagues, ~200,000+ users)

### When to trigger

This stage is aspirational. Only pursue if the business justifies it.

### What to do

#### 5.1 Database sharding or partitioning

Partition the `picks` table by `league_id` or `season_id`:
```sql
ALTER TABLE picks RENAME TO picks_old;
CREATE TABLE picks (LIKE picks_old INCLUDING ALL) PARTITION BY HASH (league_id);
CREATE TABLE picks_p0 PARTITION OF picks FOR VALUES WITH (modulus 4, remainder 0);
CREATE TABLE picks_p1 PARTITION OF picks FOR VALUES WITH (modulus 4, remainder 1);
-- etc.
```

This keeps query performance linear as data grows.

#### 5.2 Separate read/write database endpoints

- Primary RDS for writes (picks, scoring, admin operations)
- Read replica for reads (standings, leaderboards, tournament data)
- Application-level routing: `DATABASE_URL` for writes, `DATABASE_READ_URL` for reads

#### 5.3 Move scraper to Lambda or Fargate

If the scraper's 5-minute sync cycle becomes a bottleneck:
- Run each tournament sync as a separate Lambda invocation
- EventBridge cron triggers instead of APScheduler
- Eliminates the single-scraper-pod constraint
- Pay per invocation (~$0.20/million requests)

#### 5.4 Multi-region (only if needed)

If users span multiple continents:
- Deploy a second EKS cluster in `eu-west-1`
- RDS cross-region read replica
- Route 53 latency-based routing
- CloudFront already provides global edge caching for static assets

**Cost**: Doubles infrastructure cost. Only justify if >30% of users are outside the US.

---

## Quick Reference: Scaling Decision Tree

```
Is node CPU > 60% sustained?
  ├─ Yes → Is it from API pods?
  │         ├─ Yes → Add API replicas (Stage 2) or upgrade instance (Stage 1)
  │         └─ No  → Upgrade instance type (Stage 1)
  └─ No

Is node memory > 80%?
  ├─ Yes → Upgrade instance type (Stage 1)
  └─ No

Is API p95 > 500ms?
  ├─ Yes → Check slow queries first (pg_stat_statements)
  │         ├─ DB bottleneck → Add indexes, optimize queries, then RDS
  │         └─ App bottleneck → More Uvicorn workers, then more replicas
  └─ No

Is DB connection pool exhausted?
  ├─ Yes → Deploy PgBouncer (Stage 1.5 / 2.3)
  └─ No

Is disk > 80% full?
  ├─ Yes → Expand EBS volume
  └─ No

Are pods being evicted (OOM)?
  ├─ Yes → Increase pod memory limits, then upgrade node
  └─ No

Do you need HA (zero single-point-of-failure)?
  ├─ Yes → Multi-node K3s (Stage 3) or EKS (Stage 4)
  └─ No  → Stay on single node

Everything is fine → Do nothing. Premature scaling wastes money.
```

---

## Cost Summary by Stage

| Stage | Users | Monthly Cost | Key Change |
|-------|-------|-------------|------------|
| 0 (current) | ~500 | ~$30 | t3a.medium, single node |
| 1 | ~2,000 | ~$55–65 | t3a.large, more workers |
| 2 | ~10,000 | ~$100–150 | 3 API replicas, RDS |
| 3 | ~50,000 | ~$200–350 | Multi-node K3s, NLB |
| 4 | ~50,000+ | ~$400–700 | EKS, HPA, Redis, CDN |
| 5 | ~200,000+ | ~$1,000+ | Sharding, multi-region |

**Golden rule**: Don't move to the next stage until you've measured and confirmed the bottleneck. Every stage adds operational complexity. Scale only what's actually stressed.
