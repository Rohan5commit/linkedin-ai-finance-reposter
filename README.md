# LinkedIn AI + Finance Auto-Reposter

Python automation that discovers public AI/finance LinkedIn posts and creates a **direct repost** on your profile on a biweekly schedule using GitHub Actions.

## What this repository does

- Discovers candidate public LinkedIn posts via free web search (`duckduckgo.com/html` fetched through `r.jina.ai`) constrained to `linkedin.com/posts` and AI/tech/finance queries.
- Extracts candidate parent URNs from public LinkedIn page metadata (`urn:li:share:*` / `urn:li:ugcPost:*`) and ranks them against the URL activity ID.
- Filters and ranks candidates for topical relevance and recency-style search ranking.
- Filters out personal career/job-change updates, personal achievement/certificate updates, and promotional non-news posts so reposts stay major-news-focused.
- Enforces a strict AI/finance-only topic gate (rejects `tech`-only or `general` posts) and blocks market recaps, roundups, and trading-signal/tips content.
- Enforces a strict direct-repost freshness gate: only candidates with derivable LinkedIn IDs newer than or equal to 7 days (configurable) are eligible.
- Publishes a **true direct repost** by trying:
  - LinkedIn Posts API (`POST /rest/posts`, `reshareContext.parent`)
  - compatibility fallback via `ugcPosts` (`responseContext.parent`)
- Posts reposts with **no text at all** (commentary is hardcoded to empty string).
- Falls back across multiple parent-URN variants and multiple candidates if one repost target is invalid/private.
- If the strict topic/freshness/cooldown filters reject every candidate, the run is skipped cleanly (article fallback is disabled in the workflow to guarantee pure reposts).
- Applies run-based candidate rotation plus persistent repost-history cooldown filtering to prevent heavy repeats.
- Persists repost and article cooldown history across workflow runs using GitHub Actions cache (`.cache/`).
- Keeps legacy article-summary mode available only if `LINKEDIN_DIRECT_REPOST_ONLY=false`.

## Repository structure

```text
.
├── .github/
│   └── workflows/
│       ├── post.yml          # scheduled repost automation
│       ├── keepalive.yml     # monthly commit to prevent Actions auto-disable
│       ├── delete_posts.yml  # manual workflow to delete posts by URN
│       └── tests.yml         # runs unit tests on push/PR
├── src/
│   ├── main.py               # main repost automation
│   ├── bootstrap_linkedin_secrets.py  # one-command token + URN bootstrap
│   └── delete_linkedin_posts.py       # delete posts by URN
├── tests/
│   └── test_main.py
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
- The Python script then picks **1 random weekday per 2-week (biweekly) window** (deterministic for that window), posting on that weekday — roughly once a week
- A retry window (default 2 days) allows a run if the selected day was missed and nothing was posted that window yet
- A monthly `keepalive.yml` commit prevents GitHub from auto-disabling scheduled workflows after 60 days of repo inactivity
- Also supports manual run via **workflow_dispatch** (manual runs bypass the random-day gate)

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

`--dry-run` discovers/ranks repost candidates and prints the repost preview (empty commentary by design) + parent URN attempts without publishing.

Mode switch:

- `LINKEDIN_DIRECT_REPOST_ONLY=true` (default): true direct repost path
- `LINKEDIN_DIRECT_REPOST_ONLY=false`: legacy article-summary posting path
- Reposts are always published with **no text** — commentary is hardcoded to empty (no env control)
- `DIRECT_REPOST_ARTICLE_FALLBACK=false`: if the direct repost path cannot publish, the run is skipped instead of posting an article (this repo's workflow sets `false` to guarantee pure text-free reposts)
- `RANDOMIZE_WEEKLY_RUN_DAYS=true` (default): enforce the 1-random-weekday-per-2-week-window gate on scheduled runs
- `RANDOM_SCHEDULE_SEED=<string>`: changes which weekday is selected each window
- `RANDOM_RETRY_WINDOW_DAYS=2`: retry window after the selected day if nothing was posted
- `POST_WINDOW_MARKER_FILE=.cache/post_window_key`: marker used to prevent duplicate posts within a window
- `REPOST_HISTORY_FILE=.cache/repost_history.json`: file used for cross-run repost memory
- `REPOST_HISTORY_MAX_ENTRIES=500`: max parent URNs retained in history
- `REPOST_COOLDOWN_POSTS=120`: most-recent reposts blocked from reuse
- `ARTICLE_HISTORY_FILE=.cache/article_history.json`: file used for cross-run article memory
- `ARTICLE_HISTORY_MAX_ENTRIES=500`: max article URLs retained in history
- `ARTICLE_COOLDOWN_POSTS=120`: most-recent article URLs blocked from reuse
- `MAX_REPOST_AGE_DAYS=7`: maximum candidate age for direct reposts; candidates older than this (or with unknown age) are skipped

## Error handling behavior

- In legacy article mode, if no relevant article remains after article cooldown filtering, the run is skipped with a warning and exits successfully.
- If no repostable LinkedIn post candidates are found, the run is skipped cleanly (article fallback is disabled in the deployed workflow).
- If all repost candidates are older than `MAX_REPOST_AGE_DAYS` (or their age cannot be derived from URL/URN IDs), the run is skipped cleanly.
- If all discovered repost candidates were used recently (cooldown history hit), the run is skipped cleanly.
- If the token is expired, the script attempts an auto-refresh when refresh-token secrets are configured; otherwise it exits non-zero with a clear re-bootstrap message.
- If every repost attempt returns `403`, the script logs an explicit permission warning to speed up LinkedIn access troubleshooting.

## Notes

- No sensitive data is stored in this repository.
- All credentials are expected through GitHub Actions secrets (or local `.env` for testing only).
