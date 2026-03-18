# AI Takeover Notes (Operational Whiteboard)

This file is for agent-to-agent handoff.  
It records **what was done**, **why those choices were made**, and **what to do next**.

## 1) Current project state

- Repository: `Rohan5commit/linkedin-ai-finance-reposter`
- Default branch: `master`
- Core automation script: `src/main.py`
- LinkedIn bootstrap helper: `src/bootstrap_linkedin_secrets.py`
- Workflow: `.github/workflows/post.yml`
- Schedule: Tuesday + Friday at 09:00 UTC (`0 9 * * 2,5`)
- Last verified manual workflow run: `23202704582` (**success**)

## 2) What was implemented (chronological)

1. Scaffolded repository with Python-only implementation and GitHub Actions.
2. Implemented news ingestion + ranking pipeline:
   - TechCrunch AI RSS
   - Reuters Finance RSS (+ fallback)
   - Google News AI RSS
   - Google News Finance RSS
   - Yahoo Finance RSS
   - Hacker News API
3. Implemented LinkedIn post generation:
   - hook + 2-3 sentence summary + source link + 3-5 hashtags
   - randomized short/long post profile
4. Implemented LinkedIn publish via `ugcPosts`.
5. Added workflow with scheduled + manual runs.
6. Added privacy policy file (`PRIVACY_POLICY.md`) for LinkedIn app setup.
7. Replaced OpenAI summarization path with NVIDIA NIM support.
8. Added one-command LinkedIn secret bootstrap helper script.
9. Completed live token setup and validated successful workflow execution.

## 3) Key decisions and rationale

### A) Reuters source reliability fallback

- Direct Reuters feed (`feeds.reuters.com`) was intermittently unavailable / unresolved.
- Added Reuters-targeted Google News RSS fallback to keep runs robust.

### B) Safety/content guardrail in article selection

- Added blocklist terms in `main.py` to avoid violent/sensitive headlines being selected for reposting.
- Reason: account is a neutral/professional repost bot.

### C) LinkedIn identity endpoint fallback

- Token exchange worked, but `/v2/me` can return permission denial for some OAuth scope combinations.
- Added fallback in bootstrap helper: if `/v2/me` fails, use `/v2/userinfo` and `sub` as member identifier.
- URN normalization: `urn:li:person:<id_or_sub>`.

### D) NVIDIA NIM over OpenAI

- Switched summarization integration from OpenAI to NVIDIA NIM per user preference.
- If NIM key is absent or call fails, deterministic local fallback summary remains active.

## 4) Secrets and credentials model

Repository expects these GitHub Actions secrets:

- `LINKEDIN_TOKEN`
- `LINKEDIN_PERSON_URN`
- `NVIDIA_NIM_API_KEY`

No secrets are stored in committed files.

## 5) Known caveats / maintenance notes

1. LinkedIn access token is time-bound; if runs fail with `INVALID_ACCESS_TOKEN`, refresh token and reset secret.
2. GitHub Actions currently shows Node 20 deprecation annotations for `actions/checkout@v4` and `actions/setup-python@v5`. Track updates.
3. Reuters direct feed failures are expected in some environments; fallback path is intentional.

## 6) Useful operational commands

### Trigger workflow manually

```bash
gh workflow run 247479029 -R Rohan5commit/linkedin-ai-finance-reposter
```

### Check latest runs

```bash
gh run list -R Rohan5commit/linkedin-ai-finance-reposter --workflow 247479029 --limit 5
```

### View failed logs

```bash
gh run view <RUN_ID> -R Rohan5commit/linkedin-ai-finance-reposter --log-failed
```

### Check secrets configured

```bash
gh secret list -R Rohan5commit/linkedin-ai-finance-reposter
```

### One-command LinkedIn secret bootstrap

```bash
python src/bootstrap_linkedin_secrets.py \
  --client-id "<LINKEDIN_CLIENT_ID>" \
  --repo "Rohan5commit/linkedin-ai-finance-reposter"
```

## 7) User preferences that matter for future agents

- User requested: **do not quit/kill apps without explicit permission**.
- User prefers high-autonomy execution (agent should do as much as possible end-to-end).

## 8) Recommended next actions for successor agent

1. Keep token freshness checks in mind before scheduled runs.
2. Optionally add a lightweight token-health precheck before attempting post.
3. Consider updating workflow action versions when Node 24-compatible updates are available.

