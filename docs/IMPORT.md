# Importing a Real League into League Caddie

This guide walks through importing an existing fantasy golf league (currently run on spreadsheets/PDFs) into League Caddie. The approach uses the admin UI and existing APIs — no direct database manipulation.

---

## Overview

The import is done in phases through the Admin page:

1. **Manual setup** — create the league, set the schedule, enable auto-accept (all via UI)
2. **Bulk member import** — upload a members CSV in the Admin page to create accounts and add them to the league
3. **Picks import** — upload a picks CSV per completed tournament in the Admin page to backfill historical picks
4. **Verification** — compare standings against the commissioner's spreadsheet

---

## Prerequisites

1. **Run a full admin sync** (`POST /admin/sync` from the Admin page) so all 2026 tournaments and golfers are in the database
2. **Have the commissioner's PDFs** — one per tournament week, each with Player and Pick columns
3. **Collect email addresses** for every league member
4. **Your platform admin account** will be the league manager

---

## Phase 1: Manual League Setup (UI)

1. **Create the league** from the Create League page (you are the manager)
2. **Set the tournament schedule** from the Manage page — check every tournament your league has played this season plus all upcoming tournaments
3. **Enable auto-accept requests** in League Settings (so imported members are auto-approved)

> **Note:** The league purchase is automatically created for platform admins (free Elite tier), so no Stripe payment is needed.

---

## Phase 2: Prepare CSV Files

### 2.1 Members CSV

Create `members.csv` with two columns:

```csv
name,email
Blake Chambers,blake@example.com
Bo Thompson,bo@example.com
Lee Linkous,lee@example.com
```

**Rules:**
- `name` = the display name shown in the app
- `email` = must be unique per member; used for login
- Do **not** include yourself (you're already in the league as the manager)
- One row per member

### 2.2 Picks CSV (one per tournament)

Create one CSV per completed tournament. Each file has two columns:

```csv
email,golfer_name
blake@example.com,Scottie Scheffler
bo@example.com,Rory McIlroy
lee@example.com,No Pick
```

**Rules:**
- `email` = must match the email in the members CSV exactly
- `golfer_name` = must match the golfer name in the database exactly (see validation below)
- Use `No Pick` for members who didn't pick that week — the script will skip these rows (the no-pick penalty is applied automatically by the standings calculation based on the absence of a pick row)
- One row per member per tournament

### 2.3 Validate Golfer Names

Before uploading, run the validation script to check all golfer names against the database.

Create `backend/scripts/validate_golfers.py`:

```python
"""
Validate golfer names in picks CSVs against the database.

Usage:
    python scripts/validate_golfers.py picks_week1.csv picks_week2.csv ...

Prints any golfer names NOT found in the database and suggests close matches.
"""

import csv
import sys

sys.path.insert(0, "/app")

from sqlalchemy import func

from app.database import SessionLocal
from app.models import Golfer


def main():
    if len(sys.argv) < 2:
        print("Usage: python validate_golfers.py <csv_file> [csv_file ...]")
        sys.exit(1)

    db = SessionLocal()
    all_golfer_names: set[str] = set()

    for csv_path in sys.argv[1:]:
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = row["golfer_name"].strip()
                if name.lower() != "no pick":
                    all_golfer_names.add(name)

    print(f"Checking {len(all_golfer_names)} unique golfer names...\n")

    missing = []
    for name in sorted(all_golfer_names):
        golfer = db.query(Golfer).filter(Golfer.name == name).first()
        if not golfer:
            # Find close matches.
            parts = name.split()
            suggestions = []
            for part in parts:
                if len(part) > 2:
                    matches = (
                        db.query(Golfer.name)
                        .filter(func.lower(Golfer.name).contains(part.lower()))
                        .limit(5)
                        .all()
                    )
                    suggestions.extend([m[0] for m in matches])
            # Deduplicate.
            suggestions = list(dict.fromkeys(suggestions))
            missing.append((name, suggestions[:5]))

    if not missing:
        print("All golfer names found in the database!")
        sys.exit(0)

    print("MISSING GOLFERS:")
    print("-" * 60)
    for name, suggestions in missing:
        print(f"\n  '{name}' — NOT FOUND")
        if suggestions:
            print("    Possible matches:")
            for s in suggestions:
                print(f"      - {s}")
        else:
            print("    No close matches found")

    print(f"\n{len(missing)} golfer(s) need to be fixed in the CSV.")
    sys.exit(1)


if __name__ == "__main__":
    main()
```

Run locally:

```bash
docker cp scripts/validate_golfers.py league-caddie-backend-1:/app/scripts/validate_golfers.py
docker cp picks_week1.csv league-caddie-backend-1:/app/scripts/picks_week1.csv

docker exec league-caddie-backend-1 python /app/scripts/validate_golfers.py \
    /app/scripts/picks_week1.csv /app/scripts/picks_week2.csv
```

Fix any mismatches in the CSV before proceeding to upload.

---

## Phase 3: Bulk Member Import (Admin Page)

### What the Admin UI does

A new section in the Admin page: **"Import Members"**

1. Select a league from a dropdown
2. Upload the `members.csv` file
3. The backend processes each row:
   - **If the email exists in the database**: uses the existing user account
   - **If the email is new**: creates a new account with `password123` as the temporary password
   - **Adds the user to the selected league** as an approved member (same result as joining through the invite link)
   - **Skips users already in the league** (no duplicate members)
4. Shows a summary: X accounts created, Y existing accounts linked, Z members added to league, W skipped (already in league)

### API Endpoint

```
POST /admin/import-members
Body: multipart/form-data
  - league_id: UUID
  - file: CSV file (name, email columns)

Response: {
    "accounts_created": 12,
    "existing_accounts": 3,
    "members_added": 15,
    "skipped_already_in_league": 0
}
```

### Rate Limiting

The register endpoint has a rate limit of 5/hour. The bulk import endpoint bypasses this because:
- It does not call the register endpoint — it creates `User` rows directly in the service layer
- It is restricted to platform admins only
- It sets a known temporary password (`password123`) for all new accounts

---

## Phase 4: Picks Import (Admin Page)

### What the Admin UI does

A new section in the Admin page: **"Import Picks"**

1. Select a league from a dropdown
2. Select a tournament from a dropdown (filtered to the league's schedule)
3. Upload the picks CSV file (email, golfer_name columns)
4. The backend processes each row:
   - Matches `email` to a user in the league
   - Matches `golfer_name` to a golfer in the database
   - Skips rows where `golfer_name` is `No Pick`
   - Uses the admin override endpoint logic to create or replace the pick for that member + tournament
   - After all picks are processed, if the tournament is completed, automatically triggers `score_picks()` to populate `points_earned`
5. Shows a summary: X picks created, Y picks updated, Z skipped (No Pick), W errors

### API Endpoint

```
POST /admin/import-picks
Body: multipart/form-data
  - league_id: UUID
  - tournament_id: UUID
  - file: CSV file (email, golfer_name columns)

Response: {
    "picks_created": 12,
    "picks_updated": 0,
    "skipped_no_pick": 3,
    "scored": true,
    "errors": []
}
```

### Validation

The endpoint validates before writing any data:
- All emails in the CSV belong to members of the selected league
- All golfer names exist in the database
- No golfer is picked by two different members (one golfer per member per tournament)
- The no-repeat rule is respected: no member has already used this golfer in a previous tournament this season

If validation fails, no data is written and the response lists all errors.

---

## Phase 5: Verification

After importing all members and picks:

1. **Compare standings** — check the Standings page against the commissioner's spreadsheet
2. **Spot-check picks** — select a few members in the Picks page and verify their pick history matches the PDFs
3. **Check edge cases**:
   - Members with no picks for certain weeks should show the no-pick penalty
   - Completed tournaments should have `points_earned` calculated
   - The current week's pick window should be open for all members

---

## Phase 6: Notify Members

Send each member their login credentials:

- **Email**: their email address
- **Temporary password**: `password123`
- **Login URL**: `https://league-caddie.com/login`
- **Action required**: Change password immediately after first login (Settings page)
- **League invite link**: share the invite link from the Manage page so they can bookmark the league

> **Security note:** `password123` is intentionally weak — it's a temporary password for onboarding only. Remind all members to change it immediately. Consider adding a "force password change on first login" feature in the future.

---

## Troubleshooting

### Golfer name mismatches

Run the validation script (Phase 2.3) before uploading. Common mismatches:
- `"Si Woo Kim"` vs `"Kim Si-woo"` — ESPN uses different formats
- `"Joaquín Niemann"` vs `"Joaquin Niemann"` — accented characters
- `"Sungjae Im"` vs `"Sung-jae Im"` — hyphenation differences

### Member already in league

The import skips members who are already in the league (no error, just counted as "skipped"). This is safe to re-run.

### Pick already exists for tournament

The admin override logic replaces existing picks. If you re-upload a picks CSV for the same tournament, it overwrites previous picks with the new data.

### Scoring shows $0 for completed tournaments

Earnings may not be published by ESPN yet. Run an admin sync for the specific tournament, or wait for the `results_finalization` safety net (runs 3x daily). See the earnings pipeline documentation for details.

---

## Production Import

The same process works in production — the Admin page is the same. Just:
1. Make sure you're logged in as a platform admin on `https://league-caddie.com`
2. Run the golfer validation script on the prod instance:

```bash
sudo kubectl cp validate_golfers.py \
    prod/league-caddie-api-<pod-name>:/app/scripts/validate_golfers.py \
    --kubeconfig /etc/rancher/k3s/k3s.yaml

sudo kubectl cp picks_week1.csv \
    prod/league-caddie-api-<pod-name>:/app/scripts/picks_week1.csv \
    --kubeconfig /etc/rancher/k3s/k3s.yaml

sudo kubectl exec -n prod deploy/league-caddie-api \
    --kubeconfig /etc/rancher/k3s/k3s.yaml -- \
    python /app/scripts/validate_golfers.py /app/scripts/picks_week1.csv
```

3. Use the Admin page UI to upload members and picks — same flow as local
