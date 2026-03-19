# AWS Setup Runbook

Step-by-step guide for provisioning all AWS resources for League Caddie. Follow in order — each step builds on the previous.

See [PLAN.md](PLAN.md) Phase 8 for the full resource list and cost breakdown.

---

## Phase 1: Account & IAM Foundation

### Step 1: Create AWS Account

- Sign up at aws.amazon.com with your personal email (starts the 12-month free tier clock)
- Use "League Caddie LLC" as the account name for clean billing records
- Add a payment method (credit card required even for free tier)

### Step 2: Secure the Root Account

- Enable MFA on root immediately: IAM → Security Credentials → MFA
- Use an authenticator app (1Password, Authy, or Google Authenticator) — not SMS
- **Never use root for daily work after this point**

### Step 3: Set Up AWS Budget Alert

- AWS Console → Billing → Budgets → Create Budget
- Monthly cost budget: **$20 threshold**
- Email notification to your personal email
- Free for up to 2 budgets — catches unexpected charges early

### Step 4: Create an Admin IAM User (for yourself)

This is the account you'll use day-to-day instead of root.

- IAM → Users → Create User
- Name: `blake-admin` (or similar)
- Attach the **AdministratorAccess** managed policy
- Enable console access + MFA
- Generate access keys for CLI use (`aws configure` on your machine)
- **Store credentials in 1Password** (or your password manager) — never in plain text files, never in git

### Step 5: Create the CI/CD Deploy User

- IAM → Users → Create User → `league-caddie-deploy`
- **Programmatic access only** (no console login)
- Create a custom policy with ECR push only permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ecr:GetAuthorizationToken",
        "ecr:BatchCheckLayerAvailability",
        "ecr:GetDownloadUrlForLayer",
        "ecr:PutImage",
        "ecr:InitiateLayerUpload",
        "ecr:UploadLayerPart",
        "ecr:CompleteLayerUpload"
      ],
      "Resource": "*"
    }
  ]
}
```

- Generate access keys → store in **GitHub repository secrets** (not your password manager — these only live in GitHub):
  - `AWS_ACCESS_KEY_ID`
  - `AWS_SECRET_ACCESS_KEY`
  - `AWS_ACCOUNT_ID`

### Step 6: Create the EC2 Instance Role

This is what your running app uses for SES + SQS at runtime (no hardcoded keys).

- IAM → Roles → Create Role → AWS Service → EC2
- Name: `league-caddie-ec2-role`
- Attach these managed policies:
  - `AmazonSESFullAccess` (or a scoped-down send-only policy)
  - `AmazonSQSFullAccess` (or scoped to your queue ARNs)
  - `CloudWatchLogsFullAccess` (for log shipping)
- This role gets attached to both EC2 instances at launch — no AWS keys needed in your app config

### Step 7: Generate an SSH Key Pair

```bash
ssh-keygen -t ed25519 -f ~/.ssh/league-caddie-ec2 -C "league-caddie-ec2"
```

- Import the **public key** into AWS: EC2 → Key Pairs → Import Key Pair
- Store the **private key** in:
  - Your password manager (1Password)
  - GitHub Secrets as `EC2_SSH_KEY` (for CI/CD deploys)

---

## Phase 2: Core Services

> Complete Phase 1 before starting Phase 2.

### Step 8: Create ECR Repositories

- ECR → Create Repository (one for each):
  - `league-caddie/backend`
  - `league-caddie/scraper`
  - `league-caddie/worker`
  - `league-caddie/frontend`
- Free tier: 500 MB/month storage
- Tag strategy: `latest` (prod) and `dev-latest` (dev) only — each push overwrites the previous tag

### Step 9: Create SQS Queues

- SQS → Create Queue (4 total — dev and prod each get a main queue + DLQ):
  - `league-caddie-events-dev` (Standard queue, VisibilityTimeout=120s, ReceiveMessageWaitTimeSeconds=20s)
  - `league-caddie-events-dev-dlq` (Standard queue — dead-letter queue)
  - `league-caddie-events-prod` (Standard queue, same settings as dev)
  - `league-caddie-events-prod-dlq` (Standard queue — dead-letter queue)
- Configure redrive policy on each main queue: DLQ after 3 receive attempts
- **Note:** LocalStack is only used for local docker-compose development. Both dev and prod on AWS use real SQS queues.
- Free tier: 1M requests/month — easily covers both environments

### Step 10: Set Up SES

- SES → Verified Identities → Create Identity
- Verify sender: `noreply@league-caddie.com` (or verify the entire domain)
- **Important:** SES starts in sandbox mode — only verified email addresses can receive emails
- Request sandbox exit via AWS Support (takes 1-3 days) — do this early
- IAM role (not keys) handles credentials on EC2

### Step 11: Create Route 53 Hosted Zone

- Route 53 → Hosted Zones → Create Hosted Zone
- Domain: `league-caddie.com` (or your chosen domain)
- Cost: $0.50/month per hosted zone
- If domain is registered elsewhere (Namecheap), update the nameservers to point to Route 53's NS records
- A records will be added after EC2 instances are launched (Step 13)

---

## Phase 3: Compute & Networking

> Complete Phase 2 before starting Phase 3.

### Step 12: Create Security Group

- EC2 → Security Groups → Create Security Group
- Name: `league-caddie-sg`
- Inbound rules:
  - Port 22 (SSH) — **your IP only** with `/32` suffix (e.g. `203.0.113.45/32`), not 0.0.0.0/0
  - Port 80 (HTTP) — 0.0.0.0/0
  - Port 443 (HTTPS) — 0.0.0.0/0
- Use this same security group for both dev and prod instances
- Find your current IP by Googling "what is my IP"
- **Important:** Your residential ISP may change your IP every few days to weeks (on router restart or DHCP lease expiry). If SSH suddenly times out, your IP has changed — update the security group's SSH rule with your new IP

### Step 13: Launch EC2 Instances

**Dev instance:**
- AMI: Amazon Linux 2023
- Instance type: `t2.micro` (free tier eligible)
- EBS: 8 GB gp3 volume (free tier: 30 GB total across all volumes)
- Attach IAM role: `league-caddie-ec2-role`
- Attach security group: `league-caddie-sg`
- Key pair: `league-caddie-ec2`

**Prod instance:**
- AMI: Amazon Linux 2023
- Instance type: `t3a.small` (2 vCPU, 2 GB RAM, ~$13.70/month — not free tier)
- EBS: 22 GB gp3 volume
- Attach IAM role: `league-caddie-ec2-role`
- Attach security group: `league-caddie-sg`
- Key pair: `league-caddie-ec2`

### Step 14: Assign Elastic IPs

- EC2 → Elastic IPs → Allocate (x2)
- Associate one with each instance
- Free while the instance is running — **charges apply if instance is stopped**
- Add these IPs to GitHub Secrets:
  - `EC2_HOST_DEV`
  - `EC2_HOST_PROD`

### Step 15: Configure DNS Records

Route 53 → Hosted Zone → `league-caddie.com` → Create Record for each:

**Prod (league-caddie.com):**
- Record name: leave blank (root domain)
- Record type: A
- Value: your prod Elastic IP (e.g. `3.95.123.45`)
- TTL: 300
- Routing policy: Simple routing

**Dev (dev.league-caddie.com):**
- Record name: `dev`
- Record type: A
- Value: your dev Elastic IP (e.g. `54.210.67.89`)
- TTL: 300
- Routing policy: Simple routing

**Verify:** After a few minutes, run `dig league-caddie.com` and `dig dev.league-caddie.com` — they should return your Elastic IPs. You can also ping the domains to confirm.

**Note:** If you also want `www.league-caddie.com` to work, create a CNAME record:
- Record name: `www`
- Record type: CNAME
- Value: `league-caddie.com`
- TTL: 300

### Step 16: Enable EBS Snapshot Automation

**Tag your EBS volumes first:**
1. EC2 → Volumes → select each volume
2. Tags → Add tag: Key = `Backup`, Value = `true`

**Create the lifecycle policy:**
1. EC2 → Lifecycle Manager → Create Lifecycle Policy
2. Policy type: **EBS snapshot policy**
3. Target resource type: **Volume**
4. Target resource tags: Key = `Backup`, Value = `true`
5. Policy description: `Daily snapshots for league-caddie EBS volumes`
6. IAM role: **Default role** (AWS creates one automatically)
7. Schedule name: `daily-snapshot`
8. Frequency: **Every 24 hours**
9. Starting at: `05:00 UTC` (overnight US time — low activity)
10. Retention type: **Count** → retain **7** snapshots (rolling 7-day window)
11. Enable **cross-region copy**: No (single region is fine)
12. Tags from source: **Copy tags from volume** (so you can identify which volume the snapshot came from)

**Verify:** After 24 hours, check EC2 → Snapshots — you should see automated snapshots tagged with `Backup: true`.

**Cost:** ~$0.05/GB/month for snapshot storage. With mostly-empty databases, this is near $0. Snapshots are incremental — only changed blocks are stored after the first one.

---

## Phase 4: Instance Setup

> SSH into each instance and run these commands.

**SSH shortcut:** Add this to `~/.ssh/config` on your local machine so you can connect with `ssh lc-dev` or `ssh lc-prod`:

```
Host lc-dev
  HostName <DEV_ELASTIC_IP>
  User ec2-user
  IdentityFile ~/.ssh/league-caddie-ec2

Host lc-prod
  HostName <PROD_ELASTIC_IP>
  User ec2-user
  IdentityFile ~/.ssh/league-caddie-ec2
```

### Step 17: Install K3s

```bash
ssh lc-dev   # or: ssh -i ~/.ssh/league-caddie-ec2 ec2-user@<ELASTIC_IP>
```

On each instance:
```bash
curl -sfL https://get.k3s.io | sh -
```

Verify:
```bash
sudo kubectl get nodes
```

### Step 18: Create Kubernetes Namespaces

On the dev instance:
```bash
sudo kubectl create namespace dev
```

On the prod instance:
```bash
sudo kubectl create namespace prod
```

### Step 19: Export Kubeconfigs

CI/CD needs kubeconfigs to run `helm upgrade` on each instance. K3s stores its kubeconfig at `/etc/rancher/k3s/k3s.yaml`.

**On each instance, copy the kubeconfig:**

```bash
sudo cat /etc/rancher/k3s/k3s.yaml
```

**Edit before saving to GitHub:**

1. Copy the output to your local machine
2. Replace `server: https://127.0.0.1:6443` with the instance's Elastic IP:
   - Dev: `server: https://<DEV_ELASTIC_IP>:6443`
   - Prod: `server: https://<PROD_ELASTIC_IP>:6443`
3. The kubeconfig contains a `certificate-authority-data`, `client-certificate-data`, and `client-key-data` — keep all of these as-is

**Store in GitHub Secrets:**
- Dev kubeconfig (full file contents) → `KUBECONFIG_DEV`
- Prod kubeconfig (full file contents) → `KUBECONFIG_PROD`

**Verify locally (optional):**

```bash
# Save the kubeconfig to a temp file
echo "<paste kubeconfig>" > /tmp/k3s-dev.yaml
KUBECONFIG=/tmp/k3s-dev.yaml kubectl get nodes
```

If it returns the node name and status `Ready`, the connection works.

**Important:** Port 6443 must be accessible from GitHub Actions runners. Add an inbound rule to your security group:
- Port 6443 (HTTPS/K8s API) — 0.0.0.0/0 (GitHub Actions IPs are dynamic, so you can't restrict by IP)

Alternatively, use the SSH tunnel approach in CI/CD to avoid exposing 6443 publicly.

### Step 20: Set Up CloudWatch Logs

Ship K3s pod logs to CloudWatch so you can query them without SSHing into instances.

**Option A: Fluent Bit as a K3s DaemonSet (recommended)**

First, install Helm if not already installed:

```bash
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
helm version  # verify
```

Set up the kubeconfig so Helm can talk to K3s:

```bash
echo 'export KUBECONFIG=/etc/rancher/k3s/k3s.yaml' >> ~/.bashrc
source ~/.bashrc
```

**Note:** K3s kubeconfig is owned by root, so all `helm` and `kubectl` commands must use `sudo` with an explicit `--kubeconfig` flag.

Then deploy Fluent Bit via Helm:

```bash
sudo helm repo add fluent https://fluent.github.io/helm-charts --kubeconfig /etc/rancher/k3s/k3s.yaml
sudo helm repo update --kubeconfig /etc/rancher/k3s/k3s.yaml

# Dev instance
sudo helm install fluent-bit fluent/fluent-bit \
  --namespace kube-system \
  --kubeconfig /etc/rancher/k3s/k3s.yaml \
  --set cloudWatchLogs.enabled=true \
  --set cloudWatchLogs.region=us-east-1 \
  --set cloudWatchLogs.logGroupName=/league-caddie/dev \
  --set cloudWatchLogs.autoCreateGroup=true

# Prod instance
sudo helm install fluent-bit fluent/fluent-bit \
  --namespace kube-system \
  --kubeconfig /etc/rancher/k3s/k3s.yaml \
  --set cloudWatchLogs.enabled=true \
  --set cloudWatchLogs.region=us-east-1 \
  --set cloudWatchLogs.logGroupName=/league-caddie/prod \
  --set cloudWatchLogs.autoCreateGroup=true
```

Fluent Bit runs as a DaemonSet — one pod per node that tails all container logs and ships them to CloudWatch. Credentials come from the EC2 IAM instance role automatically.

**Option B: CloudWatch Agent (simpler, less flexible)**

```bash
sudo yum install -y amazon-cloudwatch-agent
```

Then configure `/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json` to tail K3s log files and ship them to the appropriate log group.

**Set log retention (do this for both log groups):**

1. CloudWatch Console → Log Groups
2. Select `/league-caddie/dev` (or `/league-caddie/prod`)
3. Actions → Edit retention setting → **30 days**
4. Without this, logs are retained **forever** and storage costs grow indefinitely

**Verify:** After deploying, check CloudWatch → Log Groups → you should see log streams appearing within a few minutes.

**Cost:** Free tier includes 5 GB ingestion + 5 GB storage per month — more than enough for your scale.

### Step 21: Update Google Cloud OAuth Settings

Once you have your domain and Elastic IPs, update the OAuth client in Google Cloud Console:

- Google Cloud Console → APIs & Services → Credentials → your OAuth 2.0 Client ID
- **Authorized JavaScript Origins:**
  - `https://league-caddie.com` (prod)
  - `https://dev.league-caddie.com` (dev, if using a dev subdomain)
  - `http://localhost:5173` (local dev — keep this)
- **Authorized Redirect URIs:**
  - `https://league-caddie.com` (prod)
  - `https://dev.league-caddie.com` (dev)
  - `http://localhost:5173` (local dev — keep this)

Without this, Google OAuth login will fail on deployed environments.

### Step 22: Configure Stripe Webhook Endpoints

Stripe webhook secrets are **per-endpoint** — your local development secret won't work for deployed environments. You need a separate webhook endpoint for each environment.

**Create dev webhook endpoint:**
1. Stripe Dashboard → Developers → Webhooks → Add Endpoint
2. Endpoint URL: `https://dev.league-caddie.com/api/v1/stripe/webhook`
3. Events to listen for: `checkout.session.completed`
4. Click Add Endpoint
5. Copy the **Signing secret** (`whsec_...`) → save to GitHub Secrets as `STRIPE_WEBHOOK_SECRET_DEV`

**Create prod webhook endpoint:**
1. Stripe Dashboard → Developers → Webhooks → Add Endpoint
2. Endpoint URL: `https://league-caddie.com/api/v1/stripe/webhook`
3. Events to listen for: `checkout.session.completed`
4. Click Add Endpoint
5. Copy the **Signing secret** (`whsec_...`) → save to GitHub Secrets as `STRIPE_WEBHOOK_SECRET_PROD`

**Stripe API keys per environment:**

| Environment | Mode | GitHub Secret |
|---|---|---|
| Dev | **Test mode** (no real charges) | `STRIPE_SECRET_KEY_DEV` |
| Prod | **Live mode** (real payments) | `STRIPE_SECRET_KEY_PROD` |

- Toggle between test/live mode in the Stripe Dashboard (top-right switch)
- Test mode keys start with `sk_test_...`, live mode keys start with `sk_live_...`
- Use **test mode** for dev so you can test payments with card `4242 4242 4242 4242` without real charges
- The `STRIPE_PUBLISHABLE_KEY` also differs per mode — store as `STRIPE_PUBLISHABLE_KEY_DEV` and `STRIPE_PUBLISHABLE_KEY_PROD`
- `STRIPE_PRICE_ID_*` values (Starter, Standard, Pro, Elite) also differ between test and live mode — create products/prices in both modes

**Important:** Do not enable live mode until you're ready for real users. Test mode is fully functional for development and QA.

---

## Where to Store Secrets

| Secret | Where to Store |
|---|---|
| AWS root credentials | Password manager (1Password) — never use day-to-day |
| `blake-admin` IAM credentials | Password manager + `~/.aws/credentials` locally |
| `league-caddie-deploy` keys | GitHub repo secrets only |
| EC2 SSH private key | Password manager + GitHub secret `EC2_SSH_KEY` |
| JWT secrets (dev/prod) | GitHub secrets (`JWT_SECRET_DEV`, `JWT_SECRET_PROD`) → injected by Helm |
| Postgres passwords (dev/prod) | GitHub secrets (`POSTGRES_PASSWORD_DEV`, `POSTGRES_PASSWORD_PROD`) → injected by Helm |
| Stripe secret keys (dev/prod) | Password manager + GitHub secrets (`STRIPE_SECRET_KEY_DEV`, `STRIPE_SECRET_KEY_PROD`) → injected by Helm |
| Stripe publishable keys (dev/prod) | Password manager + GitHub secrets (`STRIPE_PUBLISHABLE_KEY_DEV`, `STRIPE_PUBLISHABLE_KEY_PROD`) → injected by Helm |
| Stripe webhook secrets (dev/prod) | Password manager + GitHub secrets (`STRIPE_WEBHOOK_SECRET_DEV`, `STRIPE_WEBHOOK_SECRET_PROD`) → injected by Helm |
| Stripe price IDs (dev/prod) | GitHub secrets (`STRIPE_PRICE_ID_STARTER`, etc. — separate for test/live mode) → injected by Helm |
| Google OAuth client ID | GitHub secrets (`GOOGLE_CLIENT_ID`) → injected by Helm |
| Kubeconfigs | GitHub secrets (`KUBECONFIG_DEV`, `KUBECONFIG_PROD`) |
| EC2 Elastic IPs | GitHub secrets (`EC2_HOST_DEV`, `EC2_HOST_PROD`) |

**The rule:** secrets live in exactly two places — your password manager (for human access) and GitHub Secrets (for CI/CD). Never in code, never in `.env` files checked into git, never in Slack/email.

---

## Checklist

- [ ] AWS account created (personal email, free tier started)
- [ ] Root MFA enabled
- [ ] Budget alert set ($20/month)
- [ ] Admin IAM user created with MFA
- [ ] `league-caddie-deploy` IAM user created (ECR push only)
- [ ] `league-caddie-ec2-role` IAM role created (SES + SQS + CloudWatch)
- [ ] SSH key pair generated and imported
- [ ] ECR repositories created (4)
- [ ] SQS queues created (dev: main + DLQ, prod: main + DLQ)
- [ ] SES sender identity verified
- [ ] SES sandbox exit requested
- [ ] Route 53 hosted zone created
- [ ] Security group created
- [ ] EC2 dev instance launched (t2.micro)
- [ ] EC2 prod instance launched (t3a.small)
- [ ] Elastic IPs assigned to both instances
- [ ] DNS A records configured
- [ ] EBS snapshot automation enabled
- [ ] K3s installed on both instances
- [ ] Kubernetes namespaces created (dev, prod)
- [ ] Kubeconfigs exported to GitHub Secrets
- [ ] CloudWatch log shipping configured
- [ ] Google Cloud OAuth origins + redirect URIs updated for prod/dev domains
- [ ] Stripe webhook endpoints created (dev + prod)
- [ ] Stripe test mode keys saved for dev, live mode keys saved for prod
- [ ] Stripe products/prices created in both test and live mode
- [ ] All secrets stored in password manager + GitHub Secrets
