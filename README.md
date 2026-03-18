# LinkedIn AI + Finance Auto-Reposter

Python automation that discovers public AI/tech/finance LinkedIn posts and creates a **direct repost** on your profile twice a week using GitHub Actions.

## What this repository does

- Discovers candidate public LinkedIn posts via free web search (`duckduckgo.com/html`) constrained to `linkedin.com/posts` and AI/tech/finance queries.
- Extracts candidate parent URNs from LinkedIn post URLs (`activity`, `share`, `ugcPost` variants).
- Filters and ranks candidates for topical relevance and recency-style search ranking.
- Publishes a **true direct repost** via LinkedIn Posts API (`POST /rest/posts`) using `reshareContext.parent`.
- Adds short professional commentary + hashtags to improve feed engagement while still being a direct repost.
- Falls back across multiple parent-URN variants and multiple candidates if one repost target is invalid/private.
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

- Runs at **09:00 UTC** on **Tuesday and Friday** (`cron: 0 9 * * 2,5`)
- Also supports manual run via **workflow_dispatch**

Workflow steps:

1. Install dependencies
2. Run `python src/main.py`
3. Log success/failure

## 6) Local testing

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python src/main.py --dry-run
```

`--dry-run` discovers/ranks repost candidates and prints the repost commentary + parent URN attempts without publishing.

Mode switch:

- `LINKEDIN_DIRECT_REPOST_ONLY=true` (default): true direct repost path
- `LINKEDIN_DIRECT_REPOST_ONLY=false`: legacy article-summary posting path

## Error handling behavior

- In legacy article mode, if no relevant article is found, the run is skipped with a warning and exits successfully.
- If no repostable LinkedIn post candidates are found, the run is skipped with a warning and exits successfully.
- If all repost attempts fail (invalid parent/private post/permissions), the script prints the last API error body and exits non-zero, so GitHub Actions marks the run as failed.

## Notes

- No sensitive data is stored in this repository.
- All credentials are expected through GitHub Actions secrets (or local `.env` for testing only).
