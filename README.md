# LinkedIn AI + Finance Auto-Reposter

Python automation that fetches trending AI and finance news from free sources and reposts one top story to LinkedIn twice a week using GitHub Actions.

## What this repository does

- Pulls candidates from free sources:
  - TechCrunch AI RSS
  - Reuters Finance RSS (plus Reuters-targeted RSS fallback if Reuters blocks direct feed access)
  - Hacker News API (top stories)
  - Google News RSS (AI and finance filters)
  - Yahoo Finance RSS
- Scores each candidate by relevance, recency, and source signals.
- Filters out generic market-recap style headlines (e.g., daily futures/closing summaries).
- Picks one top trending/relevant article per run.
- Prefers candidates with discoverable preview-image metadata (Open Graph / Twitter image tags) for richer LinkedIn rendering.
- Enforces LinkedIn commentary length limit (max 3000 chars) before posting.
- Builds a neutral, professional LinkedIn post:
  - engaging hook
  - headline line
  - 2-3 sentence summary
  - source link
  - 3-5 relevant hashtags
- Publishes as an **ARTICLE share** via LinkedIn `ugcPosts`, so the post appears as a repost-style link card (with image preview when available).
- Randomly alternates between:
  - short posts: 150-300 words
  - long posts: 400-600 words
- Posts directly to LinkedIn via `ugcPosts`.

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
- `NVIDIA_NIM_API_KEY` = your NVIDIA NIM API key (optional; fallback summarizer is used when absent)

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

## 4) Get NVIDIA NIM API key (optional AI summarization)

1. Sign in at <https://build.nvidia.com/> (or NVIDIA API catalog).
2. Generate an API key.
3. Add it as GitHub secret: `NVIDIA_NIM_API_KEY`.
4. Optional model override:
   - Workflow env: `NIM_MODEL`
   - Local `.env`: `NIM_MODEL=meta/llama-3.1-8b-instruct`

If no NIM key is set, the bot uses deterministic local summarization automatically.

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

`--dry-run` fetches/scoring/generates post content but does not publish to LinkedIn.

## Error handling behavior

- If no relevant article is found, the run is skipped with a warning and exits successfully.
- If no image metadata is discovered in top candidates, the bot still posts the best-ranked article link (LinkedIn may still render a link card image).
- If LinkedIn API posting fails, the script prints the API error body and exits non-zero, so the GitHub Action is marked failed.

## Notes

- No sensitive data is stored in this repository.
- All credentials are expected through GitHub Actions secrets (or local `.env` for testing only).
