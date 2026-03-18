# LinkedIn AI + Finance Auto-Reposter

Python automation that discovers public AI/tech/finance LinkedIn posts and creates a **direct repost** on your profile twice a week using GitHub Actions.

## What this repository does

- Discovers candidate public LinkedIn posts via free web search (`duckduckgo.com/html` fetched through `r.jina.ai`) constrained to `linkedin.com/posts` and AI/tech/finance queries.
- Extracts candidate parent URNs from public LinkedIn page metadata (`urn:li:share:*` / `urn:li:ugcPost:*`) and ranks them against the URL activity ID.
- Filters and ranks candidates for topical relevance and recency-style search ranking.
- Publishes a **true direct repost** by trying:
  - LinkedIn Posts API (`POST /rest/posts`, `reshareContext.parent`)
  - compatibility fallback via `ugcPosts` (`responseContext.parent`)
- Adds short professional commentary + hashtags to improve feed engagement while still being a direct repost.
- Falls back across multiple parent-URN variants and multiple candidates if one repost target is invalid/private.
- If live search discovery is temporarily blocked, uses a curated fallback list of public AI/tech/finance LinkedIn post URLs so runs can still execute.
- Applies run-based candidate rotation plus persistent repost-history cooldown filtering to prevent heavy repeats.
- Persists recent repost parent URNs across workflow runs using GitHub Actions cache (`.cache/repost_history.json`).
- Keeps legacy article-summary mode available only if `LINKEDIN_DIRECT_REPOST_ONLY=false`.

## Repository structure

```text
.
├── .github/
│   └── workflows/
│       └── post.yml
├── src/
│   └── main.py
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

## 1) Fork and enable Actions

1. Fork this repository.
2. In your fork, open **Settings → Actions → General** and ensure workflows are enabled.

## 2) Add required GitHub secrets

In your fork: **Settings → Secrets and variables → Actions → New repository secret**

- `LINKEDIN_TOKEN` = your LinkedIn user access token with posting scope
- `LINKEDIN_PERSON_URN` = your person URN (example: `urn:li:person:abc123...`)
- `NVIDIA_NIM_API_KEY` = optional, only used when `LINKEDIN_DIRECT_REPOST_ONLY=false` (legacy summary mode)

### Fast local bootstrap (recommended)

After creating your LinkedIn app, you can let a helper script fetch token + URN and save both secrets automatically:

```bash
python src/bootstrap_linkedin_secrets.py \
  --client-id "<YOUR_LINKEDIN_CLIENT_ID>" \
  --repo "Rohan5commit/linkedin-ai-finance-reposter"
```

It opens LinkedIn auth in your browser, captures callback locally, exchanges token, calls `/v2/me`, and writes:

- `LINKEDIN_TOKEN`
- `LINKEDIN_PERSON_URN`

If `/v2/me` is not permitted for your token, the script automatically falls back to `/v2/userinfo` and uses `sub`.

## 3) Get a LinkedIn API token and person URN

1. Create a LinkedIn app: <https://www.linkedin.com/developers/apps>
2. In your app settings, add an OAuth redirect URL (for local testing, `http://localhost:8080/callback` works).
3. Request auth code (replace placeholders):

```text
https://www.linkedin.com/oauth/v2/authorization
?response_type=code
&client_id=<LINKEDIN_CLIENT_ID>
&redirect_uri=<URL_ENCODED_REDIRECT_URI>
&scope=openid%20profile%20w_member_social
```

Important for **direct reposts of third-party posts**: if LinkedIn returns HTTP `403 FORBIDDEN` for all repost attempts, your app/token likely does not have sufficient approved access for member-content repost operations (commonly restricted access such as `r_member_social` plus repostable target visibility).

4. Exchange auth code for access token:

```bash
curl -sS -X POST https://www.linkedin.com/oauth/v2/accessToken \
  -d grant_type=authorization_code \
  -d code=<AUTH_CODE> \
  -d redirect_uri=<REDIRECT_URI> \
  -d client_id=<LINKEDIN_CLIENT_ID> \
  -d client_secret=<LINKEDIN_CLIENT_SECRET>
```

5. Save `access_token` as your `LINKEDIN_TOKEN`.
6. Get your member ID with:

```bash
curl -sS \
  -H "Authorization: Bearer <LINKEDIN_TOKEN>" \
  https://api.linkedin.com/v2/me
```

If that returns permission errors, use:

```bash
curl -sS \
  -H "Authorization: Bearer <LINKEDIN_TOKEN>" \
  https://api.linkedin.com/v2/userinfo
```

7. Convert the returned identifier to person URN:

```text
urn:li:person:<id_or_sub>
```

8. Save `LINKEDIN_TOKEN` and `LINKEDIN_PERSON_URN` in GitHub Actions secrets.

## 4) Get NVIDIA NIM API key (optional, legacy summary mode only)

1. Sign in at <https://build.nvidia.com/> (or NVIDIA API catalog).
2. Generate an API key.
3. Add it as GitHub secret: `NVIDIA_NIM_API_KEY`.
4. Optional model override:
   - Workflow env: `NIM_MODEL`
   - Local `.env`: `NIM_MODEL=meta/llama-3.1-8b-instruct`

If no NIM key is set, the legacy summary mode uses deterministic local summarization automatically.

## 5) Schedule and execution

Workflow file: `.github/workflows/post.yml`

- Workflow triggers **daily at 09:00 UTC** (`cron: 0 9 * * *`)
- The Python script then selects **2 random days per ISO week** (deterministic for that week) and only posts on those two days
- Also supports manual run via **workflow_dispatch**

Workflow steps:

1. Install dependencies
2. Restore repost history cache (`.cache/repost_history.json`)
3. Run `python src/main.py`
4. Save updated repost history cache automatically at job end
5. Log success/failure

## 6) Local testing

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python src/main.py --dry-run --ignore-random-schedule
```

`--dry-run` discovers/ranks repost candidates and prints the repost commentary + parent URN attempts without publishing.

Mode switch:

- `LINKEDIN_DIRECT_REPOST_ONLY=true` (default): true direct repost path
- `LINKEDIN_DIRECT_REPOST_ONLY=false`: legacy article-summary posting path
- `RANDOMIZE_WEEKLY_RUN_DAYS=true` (default): enforce 2-random-days-per-week gate on scheduled runs
- `RANDOM_SCHEDULE_SEED=<string>`: changes which two days are selected each week
- `REPOST_HISTORY_FILE=.cache/repost_history.json`: file used for cross-run repost memory
- `REPOST_HISTORY_MAX_ENTRIES=500`: max parent URNs retained in history
- `REPOST_COOLDOWN_POSTS=120`: most-recent reposts blocked from reuse

## Error handling behavior

- In legacy article mode, if no relevant article is found, the run is skipped with a warning and exits successfully.
- If no repostable LinkedIn post candidates are found, the run is skipped with a warning and exits successfully.
- If all discovered repost candidates were used recently (cooldown history hit), the run is skipped with a warning to avoid duplicates.
- If all repost attempts fail (invalid parent/private post/permissions), the script prints the last API error body and exits non-zero, so GitHub Actions marks the run as failed.
- If every repost attempt returns `403`, the script logs an explicit permission warning to speed up LinkedIn access troubleshooting.

## Notes

- No sensitive data is stored in this repository.
- All credentials are expected through GitHub Actions secrets (or local `.env` for testing only).
