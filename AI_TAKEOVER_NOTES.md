# AI Takeover Notes (Operational Whiteboard)

This file is for agent-to-agent handoff.  
It records **what was done**, **why those choices were made**, and **what to do next**.

## 1) Current project state

- Repository: `Rohan5commit/linkedin-ai-finance-reposter`
- Default branch: `master`
- Core automation script: `src/main.py`
- LinkedIn bootstrap helper: `src/bootstrap_linkedin_secrets.py`
- Workflow: `.github/workflows/post.yml`
- Schedule trigger: Tuesday + Friday at 09:00 UTC (`0 9 * * 2` and `0 9 * * 5`)
- Last successful manual workflow run: `23226222725` (**success**, article card mode)
- Latest direct-repost validation runs:
  - `23226616001`, `23226692481`, `23226778661` (**failed**, 403 on all attempts before parent URN resolver fix)
  - `23226908393` (**success**, direct repost)
  - `23226942183` (**success**, direct repost, share id `urn:li:share:7439867589482340352`)

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
10. Switched LinkedIn payload from text-only posts to ARTICLE shares with link cards.
11. Added image-first candidate preference by detecting OG/Twitter image metadata from feeds/pages.
12. Live-validated article-card posting after the change (`share urn:li:share:7439860186632101888`).
13. Added true direct-repost mode using LinkedIn Posts API (`/rest/posts` + `reshareContext.parent`) with default `LINKEDIN_DIRECT_REPOST_ONLY=true`.
14. Added public LinkedIn post discovery via DuckDuckGo HTML search and URN extraction from post URLs.
15. Added page-metadata parent URN resolver (extract `share`/`ugcPost` URNs from public post HTML and rank vs activity ID), which unlocked successful third-party direct reposts.
16. Added compatibility fallback from `/rest/posts` reshare to `ugcPosts` response-context reshare; latest success used this fallback path.
17. Replaced fixed Tue/Fri cadence with weekly random day selection (2 random days chosen per ISO week, deterministic from seed).
18. Added fallback candidate source: curated public LinkedIn post URL list used when live search discovery is unavailable.
19. Added run-based candidate rotation to avoid posting the same source repeatedly in burst/manual runs.
20. Added persistent anti-duplication state:
   - tracks recently reposted parent URNs in `.cache/repost_history.json`
   - blocks candidates that hit the recent cooldown window
   - persists history across runs via GitHub Actions cache restore/save
   - cleanly skips runs (success) when all candidates are recently used, instead of reposting duplicates

## 3) Key decisions and rationale

### A) Reuters source reliability fallback

- Direct Reuters feed (`feeds.reuters.com`) was intermittently unavailable / unresolved.
- Added Reuters-targeted Google News RSS fallback to keep runs robust.

### B) Safety/content guardrail in article selection

- Added blocklist terms in `main.py` to avoid violent/sensitive headlines being selected for reposting.
- Reason: account is a neutral/professional repost bot.

### C) Non-recap editorial filter

- Added explicit market-recap exclusion patterns (daily futures/closing-bell style headlines).
- Added event/news relevance weighting to prioritize substantive tech/AI/finance developments over routine market movement summaries.
- Reason: target content should feel like meaningful industry/news updates, not generic market recap blurbs.

### D) LinkedIn identity endpoint fallback

- Token exchange worked, but `/v2/me` can return permission denial for some OAuth scope combinations.
- Added fallback in bootstrap helper: if `/v2/me` fails, use `/v2/userinfo` and `sub` as member identifier.
- URN normalization: `urn:li:person:<id_or_sub>`.

### E) NVIDIA NIM over OpenAI

- Switched summarization integration from OpenAI to NVIDIA NIM per user preference.
- If NIM key is absent or call fails, deterministic local fallback summary remains active.

### F) LinkedIn max-length enforcement

- Added strict post-length enforcement so final `shareCommentary.text` is always <= 3000 characters.
- Reason: LinkedIn `ugcPosts` rejects payloads above 3000 chars with HTTP 400.

### G) Repost-style output with images

- User asked for repost-like output with images rather than plain market recap text.
- Updated `ugcPosts` payload to use `shareMediaCategory: ARTICLE` and attach `originalUrl` media.
- Added image-preference scoring (feed media metadata + OG/Twitter image discovery from top candidates) to bias selections toward links that render with preview images on LinkedIn.

### H) True direct repost requirement

- User clarified that ARTICLE shares were still not acceptable; they wanted an actual LinkedIn repost.
- Implemented direct repost path through `POST /rest/posts` with `reshareContext.parent`.
- Since member-feed APIs are restricted, discovery now uses free public search (DuckDuckGo HTML via `r.jina.ai`) for `linkedin.com/posts` URLs and derives candidate parent URNs (`share`, `ugcPost`) from URL activity IDs.
- Publisher retries multiple URN variants and multiple candidates before failing.

### I) Random weekly schedule (2 days)

- User requested non-fixed weekdays.
- Workflow now triggers daily at 09:00 UTC, and Python gate decides whether today is one of this week's 2 random selected days.
- Day selection is deterministic per ISO week using `RANDOM_SCHEDULE_SEED`, avoiding drift/re-randomization within the same week.

### K) Scheduler simplification (non-daily)

- User requested non-daily scheduling again after live tests.
- Updated workflow schedule back to fixed twice-weekly runs (Tue/Fri 09:00 UTC).
- Set `RANDOMIZE_WEEKLY_RUN_DAYS=false` in workflow env so schedule behavior is explicit and predictable.

### J) Persistent duplicate suppression (cross-run)

- Run-rotation alone reduced repeats in bursts but did not fully prevent reusing the same parent posts over many manual runs.
- Implemented hard cooldown using persisted parent-URN history (`REPOST_COOLDOWN_POSTS`) and capped retention (`REPOST_HISTORY_MAX_ENTRIES`).
- Added workflow cache for `.cache/repost_history.json` so history survives between GitHub Action runs.
- If every candidate is in cooldown, the run now skips with warning (prevents feed spam/repetition).

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
4. Direct repost now works with page-derived parent URNs + API fallback. Keep the 403 diagnostic in place because permissions/target visibility can still cause failures on specific posts.
5. Search discovery via `r.jina.ai` can intermittently return HTTP 451; fallback URL list is in place to avoid full-run skips.
6. During aggressive manual burst testing, repeated reposts can happen if history persistence is disabled/missing; keep cache + history env vars enabled.

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
