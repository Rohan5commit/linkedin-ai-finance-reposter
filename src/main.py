#!/usr/bin/env python3
"""Automated LinkedIn repost bot for trending AI and finance news."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import random
import re
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import parse_qs, quote_plus, unquote, urlencode, urljoin, urlparse

import feedparser
import requests
from dotenv import load_dotenv

USER_AGENT = "linkedin-ai-finance-reposter/1.0"
REQUEST_TIMEOUT = 20
LINKEDIN_MAX_POST_CHARS = 3000
LINKEDIN_MEDIA_SCAN_LIMIT = 8
LINKEDIN_MEDIA_IMAGE_BONUS = 14.0
LINKEDIN_MEDIA_TIMEOUT = 8
LINKEDIN_MAX_MEDIA_TITLE_CHARS = 200
LINKEDIN_MAX_MEDIA_DESC_CHARS = 256
HN_TOP_STORIES_URL = "https://hacker-news.firebaseio.com/v0/topstories.json"
HN_ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{story_id}.json"
LINKEDIN_UGC_API_URL = "https://api.linkedin.com/v2/ugcPosts"
LINKEDIN_POSTS_API_URL = "https://api.linkedin.com/rest/posts"
LINKEDIN_API_VERSION = "202510"
NVIDIA_NIM_CHAT_API_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
DIRECT_REPOST_RESULT_LIMIT = 20
DEFAULT_REPOST_HISTORY_FILE = ".cache/repost_history.json"
DEFAULT_REPOST_HISTORY_MAX_ENTRIES = 250
DEFAULT_REPOST_COOLDOWN_POSTS = 80
DEFAULT_ARTICLE_HISTORY_FILE = ".cache/article_history.json"
DEFAULT_ARTICLE_HISTORY_MAX_ENTRIES = 250
DEFAULT_ARTICLE_COOLDOWN_POSTS = 80
DEFAULT_MAX_REPOST_AGE_DAYS = 7
MAX_REPOST_AGE_DAYS_MIN = 1
MAX_REPOST_AGE_DAYS_MAX = 365

DIRECT_REPOST_QUERIES = [
    (
        "ai",
        'site:linkedin.com/posts ("artificial intelligence" OR AI OR GenAI OR LLM) (launch OR product OR funding OR finance OR technology)',
    ),
    (
        "finance",
        'site:linkedin.com/posts (finance OR fintech OR markets OR banking) (AI OR technology OR startup)',
    ),
    (
        "tech",
        'site:linkedin.com/posts (technology OR startup OR software OR semiconductor OR cloud) (AI OR finance)',
    ),
]

FALLBACK_LINKEDIN_POST_URLS: list[str] = []

RSS_SOURCES = [
    ("TechCrunch AI", "https://techcrunch.com/tag/artificial-intelligence/feed/"),
    ("Reuters Finance", "https://feeds.reuters.com/reuters/businessNews"),
    (
        "Reuters Finance Fallback",
        "https://news.google.com/rss/search?q=site:reuters.com+finance+when:7d&hl=en-US&gl=US&ceid=US:en",
    ),
    (
        "Google News AI",
        "https://news.google.com/rss/search?q=artificial+intelligence+when:7d&hl=en-US&gl=US&ceid=US:en",
    ),
    (
        "Google News Finance",
        "https://news.google.com/rss/search?q=finance+markets+when:7d&hl=en-US&gl=US&ceid=US:en",
    ),
    ("Yahoo Finance", "https://finance.yahoo.com/news/rssindex"),
]

SOURCE_WEIGHTS = {
    "TechCrunch AI": 16.0,
    "Reuters Finance": 18.0,
    "Reuters Finance Fallback": 17.0,
    "Google News AI": 13.0,
    "Google News Finance": 13.0,
    "Yahoo Finance": 15.0,
    "Hacker News": 17.0,
}

AI_KEYWORDS = (
    "ai",
    "artificial intelligence",
    "machine learning",
    "llm",
    "generative",
    "genai",
    "openai",
    "anthropic",
    "nvidia",
    "deep learning",
)

TECH_KEYWORDS = (
    "tech",
    "technology",
    "startup",
    "software",
    "platform",
    "cloud",
    "semiconductor",
    "chip",
    "cybersecurity",
    "developer",
)

FINANCE_KEYWORDS = (
    "finance",
    "markets",
    "stocks",
    "equities",
    "economy",
    "economic",
    "bank",
    "federal reserve",
    "interest rate",
    "inflation",
    "fintech",
    "earnings",
    "ipo",
    "merger",
    "acquisition",
    "treasury",
    "credit",
    "nasdaq",
    "dow jones",
    "s&p 500",
    "crypto",
    "bond",
)

NEWS_EVENT_KEYWORDS = (
    "announces",
    "announced",
    "launches",
    "launch",
    "rollout",
    "release",
    "agreement",
    "partnership",
    "acquires",
    "acquisition",
    "merger",
    "funding",
    "raises",
    "policy",
    "regulation",
    "investigation",
    "approval",
    "earnings",
    "ipo",
)

MARKET_RECAP_PATTERNS = (
    r"\bstock market today\b",
    r"\bmarket recap\b",
    r"\bmarket wrap\b",
    r"\bclosing bell\b",
    r"\bpre[- ]market\b",
    r"\bfutures (rise|rally|slip|fall|edge|tick|dip|mixed)\b",
    r"\b(dow|nasdaq|s&p 500).*(futures|close|closed|slip|fall|rise|rally|mixed)\b",
    r"\b(stocks|shares).*(rise|fall|mixed|edge|close|closed)\b",
)

PERSONAL_JOB_SIGNAL_TERMS = (
    "new role",
    "new position",
    "excited to announce",
    "thrilled to announce",
    "happy to share",
    "delighted to share",
    "joined as",
    "joining as",
    "joined ",
    "joining ",
    "starting as",
    "starting my",
    "promoted to",
    "promotion",
    "appointed as",
)

PERSONAL_FIRST_PERSON_TERMS = (
    " i ",
    " i'm ",
    " i’m ",
    " my ",
    " me ",
)

PERSONAL_ACHIEVEMENT_SIGNAL_TERMS = (
    "certificate",
    "certification",
    "certified",
    "award",
    "awarded",
    "honored",
    "honoured",
    "grateful",
    "proud to share",
    "completed",
    "completion",
    "graduated",
)

PROMOTIONAL_SIGNAL_TERMS = (
    "introducing",
    "learn more",
    "register now",
    "sign up",
    "join us",
    "webinar",
    "workshop",
    "demo",
    "book a demo",
    "our solution",
    "managed services",
    "case study",
    "whitepaper",
    "newsletter",
)

BLOCKLIST_TERMS = (
    "kill",
    "killed",
    "killing",
    "murder",
    "suicide",
    "terror",
    "bomb",
    "shooting",
    "hostage",
)

TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")
WORD_RE = re.compile(r"[A-Za-z0-9#@'_-]+")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
MARKET_RECAP_REGEXES = tuple(
    re.compile(pattern, re.IGNORECASE) for pattern in MARKET_RECAP_PATTERNS
)


@dataclass
class ArticleCandidate:
    title: str
    url: str
    source: str
    summary_hint: str
    published_at: Optional[datetime]
    topic: str
    score: float
    preview_image_url: Optional[str] = None


@dataclass
class RepostCandidate:
    title: str
    url: str
    source: str
    topic: str
    score: float
    parent_urn_candidates: list[str]
    inferred_created_at: Optional[datetime] = None


@dataclass(frozen=True)
class LengthProfile:
    name: str
    min_words: int
    max_words: int


SHORT_PROFILE = LengthProfile(name="short", min_words=150, max_words=300)
LONG_PROFILE = LengthProfile(name="long", min_words=400, max_words=600)
WEEKDAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

HOOKS = {
    "ai": [
        "AI trend watch: this headline is moving quickly across major free feeds.",
        "Today in AI: this story is getting outsized attention in the latest cycle.",
        "Notable AI update: this item is surfacing repeatedly in current coverage.",
    ],
    "tech": [
        "Tech trend watch: this headline is gaining traction across major coverage.",
        "Today in tech: this development is drawing notable industry attention.",
        "Notable tech update: this story is surfacing repeatedly in current reporting.",
    ],
    "finance": [
        "Finance trend watch: this market-focused headline is rising in visibility.",
        "Today in finance: this report is one of the most discussed updates right now.",
        "Notable finance update: this story is climbing across major news feeds.",
    ],
    "ai-finance": [
        "AI + finance trend watch: this crossover headline is gaining momentum.",
        "Today in AI and finance: this development is drawing broad attention.",
        "Notable AI/finance update: this story is surfacing across multiple sources.",
    ],
    "general": [
        "Trend watch: this tech-and-markets story is gaining attention.",
        "Headline snapshot: this update is rising across open news feeds.",
        "Current watchlist item: this story is drawing significant coverage.",
    ],
}

GENERAL_CLAUSES = [
    "coverage emphasizes concrete operational updates rather than speculative commentary",
    "the reporting cycle highlights measurable signals such as timelines, adoption pace, and execution risk",
    "public discussion is centering on implementation details, governance expectations, and near-term milestones",
    "the latest feed activity points to sustained interest from both technical and business audiences",
    "the update is being tracked for practical implications across product strategy, budgets, and workflows",
    "this development is notable because follow-up reporting continues to expand around adjacent sectors",
    "current reporting remains fact-first, with attention on verifiable disclosures and source documents",
    "stakeholders are monitoring how quickly related announcements translate into concrete market behavior",
    "the narrative is evolving through incremental updates rather than a single isolated signal",
    "the story sits at the intersection of technology rollout, policy framing, and commercial execution",
    "coverage quality is strongest where outlets cite explicit metrics, dates, and accountable statements",
    "this trend is being interpreted through both near-term indicators and longer planning horizons",
    "the update is now part of a broader pattern appearing in multiple independent feed ecosystems",
    "discussion has shifted from headline reaction toward operational consequences and execution discipline",
    "reporting reflects an ongoing balance between innovation speed and reliability expectations",
]

AI_CLAUSES = [
    "AI teams are evaluating model performance, deployment constraints, and inference cost trade-offs",
    "industry observers are tracking compute availability, data quality, and model governance requirements",
    "product leaders are assessing how this update influences roadmap priorities and release sequencing",
    "enterprise adoption conversations remain focused on security controls, accuracy, and compliance pathways",
    "technical coverage highlights model lifecycle management, monitoring, and rollback readiness",
    "market attention includes implications for cloud capacity, semiconductor demand, and platform competition",
    "reporting frequently references integration complexity across existing systems and business processes",
    "the update is being mapped to practical use cases with measurable productivity and quality outcomes",
]

FINANCE_CLAUSES = [
    "finance reporting is focused on liquidity conditions, valuation sensitivity, and risk pricing",
    "market participants are watching policy signals, earnings guidance, and macroeconomic data releases",
    "coverage highlights capital allocation discipline, margin pressure, and demand visibility",
    "analysts are comparing this development with prior cycles to contextualize durability",
    "discussion includes possible second-order effects on rates, credit conditions, and sector rotation",
    "the reporting pattern emphasizes execution quality over short-lived sentiment spikes",
    "financial stakeholders are assessing exposure, concentration risk, and timing assumptions",
    "news flow is being interpreted alongside broader indicators for confidence and spending behavior",
]


def log(level: str, message: str) -> None:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    print(f"[{timestamp}] [{level}] {message}")


def weekly_random_run_days(seed_material: str, now_utc: datetime) -> list[int]:
    iso_year, iso_week, _ = now_utc.isocalendar()
    week_key = f"{seed_material}:{iso_year}-W{iso_week}"
    digest = hashlib.sha256(week_key.encode("utf-8")).hexdigest()
    rng = random.Random(int(digest[:16], 16))
    return sorted(rng.sample(list(range(7)), 2))


def parse_positive_int_env(name: str, default_value: int) -> int:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default_value
    if raw_value.isdigit() and int(raw_value) > 0:
        return int(raw_value)
    log("WARN", f"Invalid {name}='{raw_value}'; using default {default_value}.")
    return default_value


def parse_max_repost_age_days_env(default_value: int = DEFAULT_MAX_REPOST_AGE_DAYS) -> int:
    raw_value = os.getenv("MAX_REPOST_AGE_DAYS", "").strip()
    if not raw_value:
        return default_value
    try:
        parsed_value = int(raw_value)
    except ValueError:
        log("WARN", f"Invalid MAX_REPOST_AGE_DAYS='{raw_value}'; using default {default_value}.")
        return default_value
    if MAX_REPOST_AGE_DAYS_MIN <= parsed_value <= MAX_REPOST_AGE_DAYS_MAX:
        return parsed_value
    log(
        "WARN",
        "Invalid MAX_REPOST_AGE_DAYS="
        f"'{raw_value}'; expected {MAX_REPOST_AGE_DAYS_MIN}-{MAX_REPOST_AGE_DAYS_MAX}. "
        f"Using default {default_value}.",
    )
    return default_value


def extract_numeric_linkedin_ids_for_candidate(candidate: RepostCandidate) -> list[int]:
    extracted_ids: list[int] = []
    for parent_urn in candidate.parent_urn_candidates:
        urn_id = parent_urn.rsplit(":", 1)[-1].strip()
        if urn_id.isdigit():
            extracted_ids.append(int(urn_id))

    activity_id = extract_activity_id_from_linkedin_post_url(candidate.url)
    if activity_id and activity_id.isdigit():
        extracted_ids.append(int(activity_id))

    for urn_id in re.findall(r"urn:li:(?:share|ugcPost|activity):(\d+)", candidate.url):
        if urn_id.isdigit():
            extracted_ids.append(int(urn_id))

    unique_ids: list[int] = []
    seen_ids: set[int] = set()
    for identifier in extracted_ids:
        if identifier not in seen_ids:
            unique_ids.append(identifier)
            seen_ids.add(identifier)
    return unique_ids


def linkedin_id_to_utc_datetime(identifier: int, now_utc: Optional[datetime] = None) -> Optional[datetime]:
    if identifier <= 0:
        return None
    epoch_ms = identifier >> 22
    if epoch_ms <= 0:
        return None
    try:
        created_at = datetime.fromtimestamp(epoch_ms / 1000.0, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None

    reference_now = now_utc or datetime.now(timezone.utc)
    if created_at.year < 2000:
        return None
    if created_at > reference_now + timedelta(days=2):
        return None
    return created_at


def infer_repost_candidate_created_at(
    candidate: RepostCandidate, now_utc: Optional[datetime] = None
) -> Optional[datetime]:
    timestamps: list[datetime] = []
    for identifier in extract_numeric_linkedin_ids_for_candidate(candidate):
        created_at = linkedin_id_to_utc_datetime(identifier, now_utc=now_utc)
        if created_at is not None:
            timestamps.append(created_at)
    if not timestamps:
        return None
    return max(timestamps)


def filter_repost_candidates_by_freshness(
    candidates: list[RepostCandidate],
    max_age_days: int,
    now_utc: Optional[datetime] = None,
) -> list[RepostCandidate]:
    reference_now = now_utc or datetime.now(timezone.utc)
    max_age = timedelta(days=max_age_days)
    fresh_candidates: list[RepostCandidate] = []
    filtered_old = 0
    filtered_unknown = 0

    for candidate in candidates:
        inferred_created_at = infer_repost_candidate_created_at(candidate, now_utc=reference_now)
        if inferred_created_at is None:
            filtered_unknown += 1
            log(
                "WARN",
                "Skipping repost candidate with unknown age: "
                f"title='{candidate.title}' | source={candidate.source} | url={candidate.url}",
            )
            continue

        candidate.inferred_created_at = inferred_created_at
        candidate_age = reference_now - inferred_created_at
        if candidate_age > max_age:
            filtered_old += 1
            age_days = candidate_age.total_seconds() / 86400.0
            log(
                "INFO",
                "Skipping stale repost candidate: "
                f"title='{candidate.title}' | source={candidate.source} | "
                f"age_days={age_days:.1f} | max_age_days={max_age_days}",
            )
            continue

        fresh_candidates.append(candidate)

    if filtered_old or filtered_unknown:
        log(
            "INFO",
            "Freshness filter results: "
            f"kept={len(fresh_candidates)} | filtered_old={filtered_old} | "
            f"filtered_unknown_age={filtered_unknown} | max_age_days={max_age_days}",
        )

    return fresh_candidates


def load_repost_history(file_path: str, max_entries: int) -> list[str]:
    if not file_path or not os.path.exists(file_path):
        return []
    try:
        with open(file_path, "r", encoding="utf-8") as history_file:
            payload = json.load(history_file)
    except (OSError, ValueError) as error:
        log("WARN", f"Failed to load repost history from {file_path} ({error}).")
        return []

    urn_values = payload.get("recent_parent_urns", [])
    if not isinstance(urn_values, list):
        return []

    cleaned_urns = [
        urn.strip()
        for urn in urn_values
        if isinstance(urn, str) and urn.strip().startswith("urn:li:")
    ]
    return unique_preserve_order(cleaned_urns)[-max_entries:]


def save_repost_history(file_path: str, recent_parent_urns: list[str], max_entries: int) -> None:
    directory = os.path.dirname(file_path)
    if directory:
        os.makedirs(directory, exist_ok=True)

    deduped_urns = unique_preserve_order(
        [urn for urn in recent_parent_urns if isinstance(urn, str) and urn.startswith("urn:li:")]
    )
    payload = {
        "recent_parent_urns": deduped_urns[-max_entries:],
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    with open(file_path, "w", encoding="utf-8") as history_file:
        json.dump(payload, history_file, ensure_ascii=True, indent=2)
        history_file.write("\n")


def recent_parent_urn_window(recent_parent_urns: list[str], cooldown_posts: int) -> set[str]:
    if cooldown_posts <= 0:
        return set()
    return set(recent_parent_urns[-cooldown_posts:])


def normalize_article_url_for_history(raw_url: str) -> str:
    cleaned = html.unescape((raw_url or "").strip())
    if not cleaned:
        return ""

    parsed = urlparse(cleaned)
    if not parsed.scheme or not parsed.netloc:
        return clean_text(cleaned).lower()

    filtered_query: list[tuple[str, str]] = []
    for key, values in parse_qs(parsed.query, keep_blank_values=True).items():
        if key.lower().startswith("utm_") or key.lower() in {"trk", "ref", "source"}:
            continue
        for value in values:
            filtered_query.append((key, value))

    query = urlencode(filtered_query)
    normalized_path = re.sub(r"/+", "/", parsed.path or "/")
    normalized_path = re.sub(r"/$", "", normalized_path) or "/"
    normalized = parsed._replace(
        scheme=parsed.scheme.lower(),
        netloc=parsed.netloc.lower(),
        path=normalized_path,
        query=query,
        fragment="",
    )
    return normalized.geturl()


def load_article_history(file_path: str, max_entries: int) -> list[str]:
    if not file_path or not os.path.exists(file_path):
        return []
    try:
        with open(file_path, "r", encoding="utf-8") as history_file:
            payload = json.load(history_file)
    except (OSError, ValueError) as error:
        log("WARN", f"Failed to load article history from {file_path} ({error}).")
        return []

    key_values = payload.get("recent_article_keys", [])
    if not isinstance(key_values, list):
        return []

    cleaned_keys = [
        key.strip()
        for key in key_values
        if isinstance(key, str) and key.strip()
    ]
    return unique_preserve_order(cleaned_keys)[-max_entries:]


def save_article_history(file_path: str, recent_article_keys: list[str], max_entries: int) -> None:
    directory = os.path.dirname(file_path)
    if directory:
        os.makedirs(directory, exist_ok=True)

    deduped_keys = unique_preserve_order(
        [key for key in recent_article_keys if isinstance(key, str) and key.strip()]
    )
    payload = {
        "recent_article_keys": deduped_keys[-max_entries:],
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    with open(file_path, "w", encoding="utf-8") as history_file:
        json.dump(payload, history_file, ensure_ascii=True, indent=2)
        history_file.write("\n")


def recent_article_key_window(recent_article_keys: list[str], cooldown_posts: int) -> set[str]:
    if cooldown_posts <= 0:
        return set()
    return set(recent_article_keys[-cooldown_posts:])


def clean_text(raw: str) -> str:
    without_tags = TAG_RE.sub(" ", raw or "")
    decoded = html.unescape(without_tags)
    return SPACE_RE.sub(" ", decoded).strip()


def word_count(text: str) -> int:
    return len(WORD_RE.findall(text))


def normalize_title(title: str) -> str:
    normalized = re.sub(r"[^a-z0-9\s]", " ", title.lower())
    return SPACE_RE.sub(" ", normalized).strip()


def truncate_words(text: str, max_words: int) -> str:
    tokens = text.split()
    if len(tokens) <= max_words:
        return text.strip()
    return " ".join(tokens[:max_words]).rstrip(",;:-") + "."


def truncate_chars(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    if max_chars <= 1:
        return text[:max_chars]
    return text[: max_chars - 1].rstrip(" ,;:-") + "…"


def split_sentences(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []
    return [segment.strip() for segment in SENTENCE_SPLIT_RE.split(text) if segment.strip()]


def parse_datetime_from_entry(entry: feedparser.FeedParserDict) -> Optional[datetime]:
    for field_name in ("published_parsed", "updated_parsed"):
        parsed = entry.get(field_name)
        if parsed:
            return datetime.fromtimestamp(time.mktime(parsed), tz=timezone.utc)
    return None


def is_http_url(url: str) -> bool:
    parsed = urlparse(url.strip())
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def extract_preview_image_from_feed_entry(entry: feedparser.FeedParserDict) -> Optional[str]:
    image_field = entry.get("image")
    if isinstance(image_field, dict):
        image_url = str(image_field.get("href") or image_field.get("url") or "").strip()
        if is_http_url(image_url):
            return image_url

    for key in ("media_content", "media_thumbnail"):
        media_items = entry.get(key, [])
        if isinstance(media_items, list):
            for item in media_items:
                if isinstance(item, dict):
                    media_url = str(item.get("url", "")).strip()
                    if is_http_url(media_url):
                        return media_url

    links = entry.get("links", [])
    if isinstance(links, list):
        for link_item in links:
            if not isinstance(link_item, dict):
                continue
            rel = str(link_item.get("rel", "")).strip().lower()
            link_type = str(link_item.get("type", "")).strip().lower()
            href = str(link_item.get("href", "")).strip()
            if rel == "enclosure" and link_type.startswith("image/") and is_http_url(href):
                return href
    return None


def extract_preview_image_from_html(html_body: str, page_url: str) -> Optional[str]:
    meta_tag_pattern = re.compile(r"<meta\s+[^>]*>", re.IGNORECASE)
    attr_pattern = re.compile(r'([a-zA-Z_:][-a-zA-Z0-9_:]*)\s*=\s*["\']([^"\']+)["\']')
    accepted_keys = {"og:image", "og:image:url", "twitter:image", "twitter:image:src"}

    for match in meta_tag_pattern.finditer(html_body):
        tag = match.group(0)
        attrs: dict[str, str] = {}
        for attr_name, attr_value in attr_pattern.findall(tag):
            attrs[attr_name.lower()] = attr_value.strip()

        meta_key = (attrs.get("property") or attrs.get("name") or "").lower()
        if meta_key not in accepted_keys:
            continue

        content_url = html.unescape(attrs.get("content", "")).strip()
        if not content_url:
            continue
        resolved_url = urljoin(page_url, content_url)
        if is_http_url(resolved_url):
            return resolved_url
    return None


def discover_preview_image_from_url(article_url: str) -> Optional[str]:
    if not is_http_url(article_url):
        return None

    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
    try:
        response = requests.get(
            article_url,
            timeout=LINKEDIN_MEDIA_TIMEOUT,
            headers=headers,
            allow_redirects=True,
        )
        response.raise_for_status()
    except requests.RequestException:
        return None

    content_type = response.headers.get("Content-Type", "").lower()
    if "text/html" not in content_type:
        return None

    html_body = response.text[:250000]
    return extract_preview_image_from_html(html_body, response.url or article_url)


def recency_points(published_at: Optional[datetime]) -> float:
    if not published_at:
        return 8.0
    age_hours = (datetime.now(timezone.utc) - published_at).total_seconds() / 3600
    return max(0.0, 72.0 - age_hours) * 0.6


def extract_google_news_target(url: str) -> str:
    parsed = urlparse(url)
    query_params = parse_qs(parsed.query)
    if "url" in query_params and query_params["url"]:
        return unquote(query_params["url"][0])
    return url


def unique_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique_values: list[str] = []
    for value in values:
        if value not in seen:
            unique_values.append(value)
            seen.add(value)
    return unique_values


def normalize_linkedin_post_url(url: str) -> str:
    cleaned = html.unescape(url).strip().split("&rut=", 1)[0]
    parsed = urlparse(cleaned)
    if not parsed.scheme or not parsed.netloc:
        return cleaned

    filtered_query: list[tuple[str, str]] = []
    for key, values in parse_qs(parsed.query, keep_blank_values=True).items():
        if key.lower().startswith("utm_") or key.lower() == "trk":
            continue
        for value in values:
            filtered_query.append((key, value))

    query = urlencode(filtered_query)
    normalized_path = re.sub(r"/+$", "", parsed.path) or parsed.path
    normalized = parsed._replace(query=query, fragment="", path=normalized_path)
    return normalized.geturl()


def extract_parent_urn_candidates_from_url(post_url: str) -> list[str]:
    urns: list[str] = []
    for urn_type, urn_id in re.findall(r"urn:li:(share|ugcPost):([A-Za-z0-9_-]+)", post_url):
        urns.append(f"urn:li:{urn_type}:{urn_id}")

    activity_match = re.search(r"activity-(\d+)", post_url)
    if not activity_match:
        activity_match = re.search(r"urn:li:activity:(\d+)", post_url)
    if activity_match:
        activity_id = activity_match.group(1)
        urns.extend(
            [
                f"urn:li:share:{activity_id}",
                f"urn:li:ugcPost:{activity_id}",
            ]
        )

    return unique_preserve_order(urns)


def extract_activity_id_from_linkedin_post_url(post_url: str) -> Optional[str]:
    activity_match = re.search(r"activity-(\d+)", post_url)
    if activity_match:
        return activity_match.group(1)

    activity_urn_match = re.search(r"urn:li:activity:(\d+)", post_url)
    if activity_urn_match:
        return activity_urn_match.group(1)
    return None


def common_prefix_length(a: str, b: str) -> int:
    total = 0
    for left, right in zip(a, b):
        if left != right:
            break
        total += 1
    return total


def rank_parent_urn_candidates(
    urn_counts: dict[str, int],
    activity_id: Optional[str],
) -> list[str]:
    ranked_items: list[tuple[str, tuple[int, int, int, int]]] = []
    for urn, count in urn_counts.items():
        urn_id = urn.rsplit(":", 1)[-1]
        prefix_len = common_prefix_length(urn_id, activity_id) if activity_id else 0
        distance = (
            abs(int(urn_id) - int(activity_id))
            if activity_id and urn_id.isdigit() and activity_id.isdigit()
            else 10**30
        )
        type_bias = 0 if ":share:" in urn else 1
        sort_key = (-prefix_len, distance, -count, type_bias)
        ranked_items.append((urn, sort_key))

    ranked_items.sort(key=lambda item: item[1])
    return [urn for urn, _ in ranked_items]


def discover_parent_urn_candidates_from_page(post_url: str) -> list[str]:
    headers = {"User-Agent": "Mozilla/5.0 (compatible; linkedin-ai-finance-reposter/1.0)"}
    activity_id = extract_activity_id_from_linkedin_post_url(post_url)
    try:
        response = requests.get(post_url, timeout=REQUEST_TIMEOUT, headers=headers)
        response.raise_for_status()
    except requests.RequestException:
        return []

    html_body = response.text
    urn_matches = re.findall(r"urn:li:(?:share|ugcPost):\d+", html_body)
    if not urn_matches:
        return []

    urn_counts: dict[str, int] = {}
    for urn in urn_matches:
        urn_counts[urn] = urn_counts.get(urn, 0) + 1

    ranked = rank_parent_urn_candidates(urn_counts, activity_id)
    return ranked[:8]


def build_title_from_linkedin_post_url(post_url: str) -> str:
    path = urlparse(post_url).path
    slug_match = re.search(r"/posts/([^/?#]+)", path)
    if not slug_match:
        return "Trending LinkedIn post"

    slug = slug_match.group(1)
    cleaned = re.sub(r"-activity-\d+.*$", "", slug)
    cleaned = cleaned.replace("_", " ")
    cleaned = re.sub(r"[-]+", " ", cleaned)
    cleaned = SPACE_RE.sub(" ", cleaned).strip()
    if not cleaned:
        return "Trending LinkedIn post"

    # Keep readable but concise for commentary text.
    return truncate_words(cleaned, 18)


def fetch_duckduckgo_results_html(query_topic: str, query_text: str, headers: dict[str, str]) -> Optional[str]:
    query_urls = [
        (
            "r.jina.ai",
            "https://r.jina.ai/http://duckduckgo.com/html/?q=" + quote_plus(query_text),
        ),
        (
            "duckduckgo-direct",
            "https://duckduckgo.com/html/?q=" + quote_plus(query_text),
        ),
    ]
    for source_name, query_url in query_urls:
        try:
            response = requests.get(
                query_url,
                timeout=REQUEST_TIMEOUT,
                headers=headers,
            )
            response.raise_for_status()
        except requests.RequestException as error:
            log("WARN", f"DuckDuckGo query failed for topic '{query_topic}' via {source_name} ({error})")
            continue

        response_body = response.text.strip()
        if not response_body:
            log("WARN", f"DuckDuckGo query returned empty body for topic '{query_topic}' via {source_name}")
            continue
        if source_name != "r.jina.ai":
            log("INFO", f"Using DuckDuckGo direct fallback for topic '{query_topic}'.")
        return response_body
    return None


def extract_linkedin_post_urls_from_duckduckgo_html(html_body: str) -> list[str]:
    redirect_param_regex = re.compile(r"uddg=([^&\s\"'<>)]{8,})", re.IGNORECASE)
    direct_url_regex = re.compile(
        r"https?://(?:[a-z]+\.)?linkedin\.com/(?:posts|feed/update)/[^\s\"'<>)]*",
        re.IGNORECASE,
    )
    extracted_urls: list[str] = []
    for match in redirect_param_regex.finditer(html_body):
        extracted_urls.append(unquote(html.unescape(match.group(1))))
    for match in direct_url_regex.finditer(html_body):
        extracted_urls.append(match.group(0))
    return unique_preserve_order([normalize_linkedin_post_url(url) for url in extracted_urls if url.strip()])


def build_article_matched_repost_queries(max_queries: int = 8) -> list[tuple[str, str]]:
    article_candidates = collect_candidates()
    if not article_candidates:
        return []

    now = datetime.now(timezone.utc)
    queries: list[tuple[str, str]] = []
    seen_phrases: set[str] = set()

    for candidate in sorted(article_candidates, key=lambda item: item.score, reverse=True):
        if candidate.published_at is not None and (now - candidate.published_at) > timedelta(days=7):
            continue

        phrase = truncate_words(clean_text(candidate.title), 10)
        if len(phrase.split()) < 3:
            continue

        phrase_key = phrase.lower()
        if phrase_key in seen_phrases:
            continue
        seen_phrases.add(phrase_key)

        topic = candidate.topic if candidate.topic != "general" else "ai-finance"
        query_text = f'site:linkedin.com/posts "{phrase}" when:7d'
        queries.append((topic, query_text))
        if len(queries) >= max_queries:
            break

    if queries:
        log("INFO", f"Generated {len(queries)} article-matched LinkedIn search queries.")
    return queries


def fetch_linkedin_repost_candidates(max_items_per_query: int = DIRECT_REPOST_RESULT_LIMIT) -> list[RepostCandidate]:
    headers = {"User-Agent": "Mozilla/5.0 (compatible; linkedin-ai-finance-reposter/1.0)"}

    candidates_by_urn: dict[str, RepostCandidate] = {}

    search_queries = list(DIRECT_REPOST_QUERIES)
    article_match_queries = build_article_matched_repost_queries()
    if article_match_queries:
        search_queries.extend(article_match_queries)

    for query_topic, query_text in search_queries:
        response_body = fetch_duckduckgo_results_html(query_topic, query_text, headers)
        if not response_body:
            continue

        result_urls = extract_linkedin_post_urls_from_duckduckgo_html(response_body)
        if not result_urls:
            log("WARN", f"DuckDuckGo ({query_topic}): no LinkedIn post URLs found in results.")
            continue

        collected_for_query = 0
        for rank, target_url in enumerate(result_urls, start=1):
            if collected_for_query >= max_items_per_query:
                break

            lower_target = target_url.lower()
            if "linkedin.com/posts/" not in lower_target and "linkedin.com/feed/update/" not in lower_target:
                continue

            parent_urn_candidates = extract_parent_urn_candidates_from_url(target_url)
            if not parent_urn_candidates:
                continue

            title = build_title_from_linkedin_post_url(target_url)
            if contains_blocklisted_terms(title):
                continue
            if is_personal_job_announcement(title):
                log("INFO", f"Skipping personal job-update candidate: title='{title}'")
                continue
            if is_personal_achievement_update(title):
                log("INFO", f"Skipping personal achievement candidate: title='{title}'")
                continue
            if is_promotional_non_news_post(title):
                log("INFO", f"Skipping promotional non-news candidate: title='{title}'")
                continue

            combined_text = f"{title} {query_text}".lower()
            topic, keyword_points = detect_topic(combined_text)
            if topic == "general":
                topic = query_topic
            if should_skip_for_recap(topic, combined_text):
                continue

            primary_urn = parent_urn_candidates[0]
            if primary_urn in candidates_by_urn:
                candidates_by_urn[primary_urn].score += 8.0
                continue

            score = (
                float(keyword_points)
                + topical_relevance_points(combined_text)
                + max(0.0, 36.0 - float(rank))
                + 18.0
            )
            candidates_by_urn[primary_urn] = RepostCandidate(
                title=title,
                url=target_url,
                source=f"DuckDuckGo Search ({query_topic})",
                topic=topic,
                score=score,
                parent_urn_candidates=parent_urn_candidates,
            )
            collected_for_query += 1

        log("INFO", f"DuckDuckGo ({query_topic}): collected {collected_for_query} repost candidates")

    ranked = sorted(candidates_by_urn.values(), key=lambda candidate: candidate.score, reverse=True)
    if ranked:
        return ranked

    if not FALLBACK_LINKEDIN_POST_URLS:
        log(
            "WARN",
            "Search discovery returned no repost candidates and static fallback URLs are disabled; skipping run.",
        )
        return []

    fallback_candidates: list[RepostCandidate] = []
    for index, post_url in enumerate(FALLBACK_LINKEDIN_POST_URLS):
        title = build_title_from_linkedin_post_url(post_url)
        topic, _ = detect_topic(title.lower())
        if topic == "general":
            topic = "ai-finance"
        fallback_candidates.append(
            RepostCandidate(
                title=title,
                url=post_url,
                source="Fallback LinkedIn URL List",
                topic=topic,
                score=40.0 - float(index),
                parent_urn_candidates=extract_parent_urn_candidates_from_url(post_url),
            )
        )

    log(
        "WARN",
        "Search discovery returned no repost candidates; falling back to curated public LinkedIn post URLs.",
    )
    return fallback_candidates


def detect_topic(text: str) -> tuple[str, int]:
    ai_hits = keyword_hit_count(text, AI_KEYWORDS)
    finance_hits = keyword_hit_count(text, FINANCE_KEYWORDS)
    tech_hits = keyword_hit_count(text, TECH_KEYWORDS)

    if ai_hits and finance_hits:
        return "ai-finance", (ai_hits + finance_hits + tech_hits) * 9
    if ai_hits:
        return "ai", (ai_hits + tech_hits) * 9
    if finance_hits:
        return "finance", (finance_hits + tech_hits) * 9
    if tech_hits:
        return "tech", tech_hits * 9
    return "general", 0


def keyword_hit_count(text: str, keywords: tuple[str, ...]) -> int:
    lower_text = text.lower()
    hit_total = 0
    for keyword in keywords:
        pattern = rf"\b{re.escape(keyword.lower())}\b"
        if re.search(pattern, lower_text):
            hit_total += 1
    return hit_total


def contains_blocklisted_terms(text: str) -> bool:
    lower_text = text.lower()
    for term in BLOCKLIST_TERMS:
        pattern = rf"\b{re.escape(term)}\b"
        if re.search(pattern, lower_text):
            return True
    return False


def is_personal_job_announcement(text: str) -> bool:
    normalized = f" {clean_text(text).lower()} "
    if not normalized.strip():
        return False

    has_job_signal = any(term in normalized for term in PERSONAL_JOB_SIGNAL_TERMS)
    has_first_person_signal = any(term in normalized for term in PERSONAL_FIRST_PERSON_TERMS)
    return has_job_signal and has_first_person_signal


def is_personal_achievement_update(text: str) -> bool:
    normalized = f" {clean_text(text).lower()} "
    if not normalized.strip():
        return False

    has_achievement_signal = any(term in normalized for term in PERSONAL_ACHIEVEMENT_SIGNAL_TERMS)
    has_first_person_signal = any(term in normalized for term in PERSONAL_FIRST_PERSON_TERMS)
    return has_achievement_signal and has_first_person_signal


def is_promotional_non_news_post(text: str) -> bool:
    normalized = f" {clean_text(text).lower()} "
    if not normalized.strip():
        return False

    has_promotional_signal = any(term in normalized for term in PROMOTIONAL_SIGNAL_TERMS)
    has_news_signal = keyword_hit_count(normalized, NEWS_EVENT_KEYWORDS) > 0
    return has_promotional_signal and not has_news_signal


def is_market_recap(text: str) -> bool:
    return any(regex.search(text) for regex in MARKET_RECAP_REGEXES)


def topical_relevance_points(text: str) -> float:
    event_hits = keyword_hit_count(text, NEWS_EVENT_KEYWORDS)
    tech_hits = keyword_hit_count(text, TECH_KEYWORDS)
    return float(event_hits * 5 + tech_hits * 3)


def should_skip_for_recap(topic: str, text: str) -> bool:
    if is_market_recap(text):
        return True

    # Avoid generic market movement recaps; prefer concrete finance/tech news events.
    if topic == "finance":
        event_hits = keyword_hit_count(text, NEWS_EVENT_KEYWORDS)
        ai_hits = keyword_hit_count(text, AI_KEYWORDS)
        tech_hits = keyword_hit_count(text, TECH_KEYWORDS)
        if event_hits == 0 and ai_hits == 0 and tech_hits == 0:
            return True
    return False


def fetch_rss_candidates(source_name: str, feed_url: str, max_items: int = 20) -> list[ArticleCandidate]:
    headers = {"User-Agent": USER_AGENT}
    try:
        response = requests.get(feed_url, timeout=REQUEST_TIMEOUT, headers=headers)
        response.raise_for_status()
    except requests.RequestException as error:
        log("WARN", f"{source_name}: failed to fetch RSS ({error})")
        return []

    parsed_feed = feedparser.parse(response.content)
    candidates: list[ArticleCandidate] = []

    for rank, entry in enumerate(parsed_feed.entries[:max_items]):
        title = clean_text(entry.get("title", ""))
        link = entry.get("link", "").strip()
        summary_hint = clean_text(entry.get("summary", "") or entry.get("description", ""))

        if not title or not link:
            continue
        if contains_blocklisted_terms(f"{title} {summary_hint}"):
            continue
        if source_name.startswith("Google News"):
            link = extract_google_news_target(link)

        combined_text = f"{title} {summary_hint}".lower()
        topic, keyword_points = detect_topic(combined_text)
        if keyword_points == 0:
            continue
        if should_skip_for_recap(topic, combined_text):
            continue

        published_at = parse_datetime_from_entry(entry)
        score = (
            keyword_points
            + topical_relevance_points(combined_text)
            + recency_points(published_at)
            + SOURCE_WEIGHTS.get(source_name, 10.0)
            + max(0.0, 20.0 - float(rank))
        )

        candidates.append(
            ArticleCandidate(
                title=title,
                url=link,
                source=source_name,
                summary_hint=summary_hint,
                published_at=published_at,
                topic=topic,
                score=score,
                preview_image_url=extract_preview_image_from_feed_entry(entry),
            )
        )

    log("INFO", f"{source_name}: collected {len(candidates)} relevant candidates")
    return candidates


def fetch_hn_candidates(max_stories: int = 60) -> list[ArticleCandidate]:
    headers = {"User-Agent": USER_AGENT}
    try:
        top_response = requests.get(HN_TOP_STORIES_URL, timeout=REQUEST_TIMEOUT, headers=headers)
        top_response.raise_for_status()
    except requests.RequestException as error:
        log("WARN", f"Hacker News: failed to fetch top stories ({error})")
        return []

    story_ids = top_response.json()[:max_stories]
    candidates: list[ArticleCandidate] = []

    for rank, story_id in enumerate(story_ids):
        item_url = HN_ITEM_URL.format(story_id=story_id)
        try:
            item_response = requests.get(item_url, timeout=REQUEST_TIMEOUT, headers=headers)
            item_response.raise_for_status()
        except requests.RequestException:
            continue

        item = item_response.json() or {}
        if item.get("type") != "story":
            continue

        title = clean_text(str(item.get("title", "")))
        if not title:
            continue
        if contains_blocklisted_terms(title):
            continue

        url = item.get("url") or f"https://news.ycombinator.com/item?id={story_id}"
        text_preview = clean_text(str(item.get("text", "")))
        combined_text = f"{title} {text_preview}".lower()
        topic, keyword_points = detect_topic(combined_text)
        if keyword_points == 0:
            continue
        if should_skip_for_recap(topic, combined_text):
            continue
        if keyword_points < 18 and topic not in ("ai", "tech", "ai-finance"):
            continue

        hn_points = min(
            45.0,
            float(item.get("score", 0)) * 0.06 + float(item.get("descendants", 0)) * 0.08,
        )
        published_at = (
            datetime.fromtimestamp(item["time"], tz=timezone.utc)
            if item.get("time")
            else None
        )
        summary_hint = (
            truncate_words(text_preview, 70)
            if text_preview
            else (
                f"This story is trending on Hacker News with {item.get('score', 0)} points "
                f"and {item.get('descendants', 0)} comments."
            )
        )

        score = (
            keyword_points
            + topical_relevance_points(combined_text)
            + hn_points
            + recency_points(published_at)
            + SOURCE_WEIGHTS["Hacker News"]
            + max(0.0, 22.0 - (float(rank) * 0.4))
        )

        candidates.append(
            ArticleCandidate(
                title=title,
                url=url,
                source="Hacker News",
                summary_hint=summary_hint,
                published_at=published_at,
                topic=topic,
                score=score,
            )
        )

    log("INFO", f"Hacker News: collected {len(candidates)} relevant candidates")
    return candidates


def collect_candidates() -> list[ArticleCandidate]:
    all_candidates: list[ArticleCandidate] = []
    for source_name, feed_url in RSS_SOURCES:
        all_candidates.extend(fetch_rss_candidates(source_name, feed_url))
    all_candidates.extend(fetch_hn_candidates())
    return all_candidates


def choose_top_article(candidates: list[ArticleCandidate]) -> Optional[ArticleCandidate]:
    if not candidates:
        return None

    title_counts = Counter(normalize_title(candidate.title) for candidate in candidates)
    for candidate in candidates:
        candidate.score += float(title_counts[normalize_title(candidate.title)] - 1) * 20.0

    ranked = sorted(candidates, key=lambda candidate: candidate.score, reverse=True)
    for candidate in ranked[:LINKEDIN_MEDIA_SCAN_LIMIT]:
        if not candidate.preview_image_url:
            candidate.preview_image_url = discover_preview_image_from_url(candidate.url)
        if candidate.preview_image_url:
            candidate.score += LINKEDIN_MEDIA_IMAGE_BONUS

    ranked = sorted(candidates, key=lambda candidate: candidate.score, reverse=True)
    image_first = [candidate for candidate in ranked if candidate.preview_image_url]
    if image_first:
        return image_first[0]

    log("WARN", "No image metadata found in top candidates; posting best-ranked article link.")
    return ranked[0]


def choose_length_profile() -> LengthProfile:
    return random.choice([SHORT_PROFILE, LONG_PROFILE])


def choose_hook(topic: str) -> str:
    hooks = HOOKS.get(topic, HOOKS["general"])
    return random.choice(hooks)


def choose_hashtags(topic: str) -> list[str]:
    if topic == "ai":
        pool = ["#AI", "#Tech", "#MachineLearning", "#GenAI", "#Innovation", "#DataScience"]
    elif topic == "tech":
        pool = ["#Tech", "#Innovation", "#Software", "#Startups", "#Cloud", "#AI"]
    elif topic == "finance":
        pool = ["#Finance", "#Tech", "#Markets", "#FinTech", "#Business", "#Economy"]
    elif topic == "ai-finance":
        pool = ["#AI", "#Finance", "#Tech", "#FinTech", "#Markets", "#GenAI", "#Innovation"]
    else:
        pool = ["#Tech", "#Business", "#Innovation", "#AI", "#Finance"]

    base_tags = ["#Tech"]
    if topic in ("ai", "ai-finance"):
        base_tags.append("#AI")
    if topic in ("finance", "ai-finance"):
        base_tags.append("#Finance")

    unique_base = list(dict.fromkeys(base_tags))
    optional = [tag for tag in pool if tag not in unique_base]
    random.shuffle(optional)
    target_count = random.randint(3, 5)
    selected = unique_base + optional[: max(0, target_count - len(unique_base))]
    return selected[:5]


def build_direct_reshare_commentary(candidate: RepostCandidate) -> str:
    style = os.getenv("DIRECT_REPOST_COMMENTARY_STYLE", "none").strip().lower()
    hashtags_line = " ".join(choose_hashtags(candidate.topic))

    if style in {"none", "off", "silent"}:
        return ""

    if style in {"hashtags", "tags", "minimal"}:
        return truncate_chars(hashtags_line, LINKEDIN_MAX_POST_CHARS)

    if style == "full":
        hook = choose_hook(candidate.topic)
        commentary = (
            f"{hook}\n\n"
            f"Direct repost signal: {candidate.title}\n\n"
            f"{hashtags_line}"
        )
        return truncate_chars(commentary, LINKEDIN_MAX_POST_CHARS)

    log("WARN", f"Unknown DIRECT_REPOST_COMMENTARY_STYLE='{style}'; defaulting to hashtags-only.")
    return truncate_chars(hashtags_line, LINKEDIN_MAX_POST_CHARS)


def prioritize_repost_candidates_for_run(candidates: list[RepostCandidate]) -> list[RepostCandidate]:
    if len(candidates) <= 1:
        return candidates

    ordered = list(candidates)
    run_id_raw = os.getenv("GITHUB_RUN_ID", "").strip()
    if not run_id_raw.isdigit():
        return ordered

    run_id = int(run_id_raw)
    fallback_only = all(candidate.source == "Fallback LinkedIn URL List" for candidate in ordered)
    if fallback_only:
        offset = run_id % len(ordered)
        if offset:
            ordered = ordered[offset:] + ordered[:offset]
        log("INFO", f"Applied fallback candidate rotation (offset={offset}) for run_id={run_id}.")
        return ordered

    pool_size = min(5, len(ordered))
    offset = run_id % pool_size
    if offset:
        rotated_pool = ordered[:pool_size]
        rotated_pool = rotated_pool[offset:] + rotated_pool[:offset]
        ordered = rotated_pool + ordered[pool_size:]
    log("INFO", f"Applied top-candidate rotation (pool={pool_size}, offset={offset}) for run_id={run_id}.")
    return ordered


def append_clause(sentence: str, clause: str) -> str:
    trimmed = sentence.rstrip().rstrip(".")
    return f"{trimmed}; {clause.rstrip('.')}."


def summary_clause_pool(topic: str) -> list[str]:
    clauses = list(GENERAL_CLAUSES)
    if topic == "ai":
        clauses.extend(AI_CLAUSES)
    elif topic == "finance":
        clauses.extend(FINANCE_CLAUSES)
    elif topic == "ai-finance":
        clauses.extend(AI_CLAUSES + FINANCE_CLAUSES)
    random.shuffle(clauses)
    return clauses


def generate_summary_with_nvidia_nim(
    candidate: ArticleCandidate,
    target_words: int,
    sentence_count: int,
) -> Optional[str]:
    api_key = os.getenv("NVIDIA_NIM_API_KEY", "").strip()
    if not api_key:
        return None

    model = os.getenv("NIM_MODEL", "meta/llama-3.1-8b-instruct").strip() or "meta/llama-3.1-8b-instruct"
    prompt = (
        "Create a neutral, professional LinkedIn news summary.\n"
        f"Use exactly {sentence_count} sentences and aim for about {target_words} words.\n"
        "Do not use first-person language.\n"
        "Keep it factual and suitable for reposting.\n"
        f"Title: {candidate.title}\n"
        f"Source: {candidate.source}\n"
        f"Snippet: {candidate.summary_hint or 'No snippet available.'}\n"
    )
    payload = {
        "model": model,
        "temperature": 0.5,
        "messages": [
            {"role": "system", "content": "You write concise, factual news summaries."},
            {"role": "user", "content": prompt},
        ],
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(
            NVIDIA_NIM_CHAT_API_URL,
            headers=headers,
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as error:
        log("WARN", f"NVIDIA NIM summarization request failed ({error}); using fallback summary.")
        return None

    if response.status_code >= 400:
        log("WARN", f"NVIDIA NIM summarization returned HTTP {response.status_code}; using fallback summary.")
        return None

    try:
        data = response.json()
    except ValueError:
        log("WARN", "NVIDIA NIM returned non-JSON response; using fallback summary.")
        return None

    choices = data.get("choices", [])
    if not choices:
        return None
    message = choices[0].get("message", {})
    content = clean_text(str(message.get("content", "")))
    if not content:
        return None

    sentence_total = len(split_sentences(content))
    if sentence_total < 2 or sentence_total > 3:
        return None
    return content


def generate_fallback_summary(
    candidate: ArticleCandidate,
    target_words: int,
    sentence_count: int,
) -> str:
    snippet = truncate_words(candidate.summary_hint or "", 55)
    if not snippet:
        snippet = "the initial reports focus on concrete developments and directly stated facts"

    topic_label = {
        "ai": "AI",
        "finance": "finance",
        "ai-finance": "AI and finance",
        "general": "technology and markets",
    }.get(candidate.topic, "technology and markets")

    sentence_one = (
        f"{candidate.title} is one of the most visible updates in current {topic_label} coverage, "
        f"with {candidate.source} and related open feeds highlighting the core development and its "
        "immediate implications for product strategy, operating priorities, and execution pace."
    )
    sentence_two = (
        f"Current reporting indicates {snippet.rstrip('.')}, while follow-up attention is centered on "
        "verifiable milestones, delivery timelines, and practical constraints that determine whether "
        "the headline translates into sustained impact across technical and commercial decision-making."
    )
    sentence_three = (
        "Across the broader news cycle, this item is being tracked alongside adjacent signals that can "
        "shape near-term planning, resource allocation, and risk management in organizations that are "
        "actively monitoring technology adoption and market behavior."
    )

    sentences = [sentence_one, sentence_two]
    if sentence_count == 3:
        sentences.append(sentence_three)

    clauses = summary_clause_pool(candidate.topic)
    clause_index = 0
    while word_count(" ".join(sentences)) < target_words:
        sentence_slot = clause_index % len(sentences)
        sentences[sentence_slot] = append_clause(sentences[sentence_slot], clauses[clause_index % len(clauses)])
        clause_index += 1
        if clause_index > 200:
            break

    summary = " ".join(sentences)
    upper_bound = target_words + 25
    if word_count(summary) > upper_bound:
        summary = truncate_words(summary, upper_bound)
    return summary


def build_post(candidate: ArticleCandidate, profile: LengthProfile) -> str:
    hook = choose_hook(candidate.topic)
    hashtags = choose_hashtags(candidate.topic)
    headline_line = f"Trending headline: {candidate.title}"
    target_total_words = random.randint(profile.min_words, profile.max_words)
    reserved_words = (
        word_count(hook)
        + word_count(headline_line)
        + word_count(f"Source: {candidate.url}")
        + len(hashtags)
        + 8
    )
    target_summary_words = max(80, target_total_words - reserved_words)
    sentence_count = 2 if profile.name == "short" else 3

    summary = generate_summary_with_nvidia_nim(candidate, target_summary_words, sentence_count)
    if not summary:
        summary = generate_fallback_summary(candidate, target_summary_words, sentence_count)

    post_text = (
        f"{hook}\n\n"
        f"{headline_line}\n\n"
        f"{summary}\n\n"
        f"Source: {candidate.url}\n\n"
        f"{' '.join(hashtags)}"
    )

    # Keep output within target word band while preserving the required format.
    min_words = profile.min_words
    max_words = profile.max_words
    while word_count(post_text) < min_words:
        summary = append_clause(summary, random.choice(summary_clause_pool(candidate.topic)))
        post_text = (
            f"{hook}\n\n"
            f"{headline_line}\n\n"
            f"{summary}\n\n"
            f"Source: {candidate.url}\n\n"
            f"{' '.join(hashtags)}"
        )

    if word_count(post_text) > max_words:
        allowed_summary_words = max_words - reserved_words
        summary = truncate_words(summary, max(50, allowed_summary_words))
        post_text = (
            f"{hook}\n\n"
            f"{headline_line}\n\n"
            f"{summary}\n\n"
            f"Source: {candidate.url}\n\n"
            f"{' '.join(hashtags)}"
        )

    # LinkedIn UGC posts reject share commentary beyond 3000 chars.
    if len(post_text) > LINKEDIN_MAX_POST_CHARS:
        prefix = f"{hook}\n\n{headline_line}\n\n"
        suffix = f"\n\nSource: {candidate.url}\n\n{' '.join(hashtags)}"
        allowed_summary_chars = max(0, LINKEDIN_MAX_POST_CHARS - len(prefix) - len(suffix))
        summary = truncate_chars(summary, allowed_summary_chars)
        post_text = f"{prefix}{summary}{suffix}"

    return post_text


def normalize_person_urn(raw_person_urn: str) -> str:
    value = raw_person_urn.strip()
    if value.startswith("urn:li:person:"):
        return value
    return f"urn:li:person:{value}"


def post_direct_reshare(
    commentary: str,
    parent_urn: str,
    token: str,
    person_urn: str,
) -> requests.Response:
    payload = {
        "author": normalize_person_urn(person_urn),
        "visibility": "PUBLIC",
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": [],
        },
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
        "reshareContext": {"parent": parent_urn},
    }
    commentary_text = commentary.strip()
    payload["commentary"] = commentary_text if commentary_text else ""

    headers = {
        "Authorization": f"Bearer {token}",
        "X-Restli-Protocol-Version": "2.0.0",
        "Linkedin-Version": LINKEDIN_API_VERSION,
        "Content-Type": "application/json",
    }
    return requests.post(
        LINKEDIN_POSTS_API_URL,
        json=payload,
        headers=headers,
        timeout=REQUEST_TIMEOUT,
    )


def post_direct_reshare_via_ugc(
    commentary: str,
    parent_urn: str,
    token: str,
    person_urn: str,
) -> requests.Response:
    share_content: dict[str, object] = {
        "shareMediaCategory": "NONE",
    }
    commentary_text = commentary.strip()
    share_content["shareCommentary"] = {"text": commentary_text if commentary_text else ""}

    payload = {
        "author": normalize_person_urn(person_urn),
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": share_content
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
        "responseContext": {"parent": parent_urn},
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Restli-Protocol-Version": "2.0.0",
        "Content-Type": "application/json",
    }
    return requests.post(
        LINKEDIN_UGC_API_URL,
        json=payload,
        headers=headers,
        timeout=REQUEST_TIMEOUT,
    )


def publish_direct_repost(
    candidates: list[RepostCandidate],
    token: str,
    person_urn: str,
    recent_parent_urns: Optional[list[str]] = None,
    cooldown_posts: int = DEFAULT_REPOST_COOLDOWN_POSTS,
    history_file_path: str = DEFAULT_REPOST_HISTORY_FILE,
    history_max_entries: int = DEFAULT_REPOST_HISTORY_MAX_ENTRIES,
) -> int:
    last_error_body = ""
    attempt_count = 0
    forbidden_count = 0
    duplicate_skip_count = 0
    history_urns = list(recent_parent_urns or [])
    recent_urn_set = recent_parent_urn_window(history_urns, cooldown_posts)
    for candidate in candidates:
        commentary = build_direct_reshare_commentary(candidate)
        discovered_parent_urns = discover_parent_urn_candidates_from_page(candidate.url)
        parent_urns = unique_preserve_order(discovered_parent_urns + candidate.parent_urn_candidates)
        if discovered_parent_urns:
            log(
                "INFO",
                f"Resolved parent URNs from page metadata for '{candidate.title}': "
                + ", ".join(parent_urns[:4]),
            )
        if recent_urn_set:
            matching_recent_urns = [urn for urn in parent_urns if urn in recent_urn_set]
            if matching_recent_urns:
                duplicate_skip_count += 1
                log(
                    "INFO",
                    f"Skipping candidate due to recent repost history: title='{candidate.title}' "
                    f"| recent_parent={matching_recent_urns[0]}",
                )
                continue

        for parent_urn in parent_urns:
            log(
                "INFO",
                f"Trying direct repost: topic={candidate.topic} | parent={parent_urn} | title='{candidate.title}'",
            )
            try:
                response = post_direct_reshare(commentary, parent_urn, token, person_urn)
            except requests.RequestException as error:
                log("WARN", f"Direct repost request failed ({error})")
                last_error_body = str(error)
                continue

            attempt_count += 1
            if response.status_code in (200, 201):
                log("INFO", f"Direct repost created successfully via parent={parent_urn}.")
                history_urns = unique_preserve_order(history_urns + [parent_urn])[-history_max_entries:]
                try:
                    save_repost_history(history_file_path, history_urns, history_max_entries)
                except OSError as error:
                    log("WARN", f"Repost succeeded but failed to persist history ({error}).")
                else:
                    log("INFO", f"Persisted repost history: {len(history_urns)} entries.")
                response_id = response.headers.get("x-restli-id") or response.headers.get("X-RestLi-Id")
                if response.text.strip():
                    print(response.text)
                elif response_id:
                    print(f'{{"id":"{response_id}"}}')
                return 0

            if response.status_code == 403:
                forbidden_count += 1
            log("WARN", f"Direct repost failed for parent={parent_urn} with HTTP {response.status_code}")
            if response.text:
                log("WARN", truncate_chars(clean_text(response.text), 350))
            last_error_body = response.text

            # Fallback: try legacy ugcPosts reshare context for broader compatibility.
            if response.status_code in (403, 404, 422):
                try:
                    ugc_response = post_direct_reshare_via_ugc(commentary, parent_urn, token, person_urn)
                except requests.RequestException as error:
                    log("WARN", f"UGC repost fallback request failed ({error})")
                    last_error_body = str(error)
                    continue

                attempt_count += 1
                if ugc_response.status_code in (200, 201):
                    log("INFO", f"Direct repost created successfully via ugcPosts parent={parent_urn}.")
                    history_urns = unique_preserve_order(history_urns + [parent_urn])[-history_max_entries:]
                    try:
                        save_repost_history(history_file_path, history_urns, history_max_entries)
                    except OSError as error:
                        log("WARN", f"Repost succeeded but failed to persist history ({error}).")
                    else:
                        log("INFO", f"Persisted repost history: {len(history_urns)} entries.")
                    response_id = ugc_response.headers.get("x-restli-id") or ugc_response.headers.get("X-RestLi-Id")
                    if ugc_response.text.strip():
                        print(ugc_response.text)
                    elif response_id:
                        print(f'{{"id":"{response_id}"}}')
                    return 0

                if ugc_response.status_code == 403:
                    forbidden_count += 1
                log(
                    "WARN",
                    f"UGC repost fallback failed for parent={parent_urn} with HTTP {ugc_response.status_code}",
                )
                if ugc_response.text:
                    log("WARN", truncate_chars(clean_text(ugc_response.text), 350))
                last_error_body = ugc_response.text

    if candidates and duplicate_skip_count == len(candidates):
        log(
            "WARN",
            "All repost candidates were recently used; skipping this run to prevent duplicate reposts.",
        )
        return 0

    if attempt_count > 0 and forbidden_count == attempt_count:
        log(
            "ERROR",
            "LinkedIn returned HTTP 403 for all repost attempts. "
            "Direct repost of third-party posts is blocked for this app/token. "
            "This usually requires LinkedIn-approved restricted access (for example r_member_social) "
            "and repostable target content visibility.",
        )

    log("ERROR", "Could not create a direct repost from discovered LinkedIn posts.")
    if last_error_body:
        print(last_error_body)
    return 1


def post_to_linkedin(
    post_text: str,
    candidate: ArticleCandidate,
    token: str,
    person_urn: str,
) -> requests.Response:
    media_description = clean_text(candidate.summary_hint)
    if not media_description:
        media_description = f"Trending {candidate.topic} news from {candidate.source}"

    payload = {
        "author": normalize_person_urn(person_urn),
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": post_text},
                "shareMediaCategory": "ARTICLE",
                "media": [
                    {
                        "status": "READY",
                        "originalUrl": candidate.url,
                        "title": {
                            "text": truncate_chars(candidate.title, LINKEDIN_MAX_MEDIA_TITLE_CHARS)
                        },
                        "description": {
                            "text": truncate_chars(media_description, LINKEDIN_MAX_MEDIA_DESC_CHARS)
                        },
                    }
                ],
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Restli-Protocol-Version": "2.0.0",
        "Content-Type": "application/json",
    }
    return requests.post(
        LINKEDIN_UGC_API_URL,
        json=payload,
        headers=headers,
        timeout=REQUEST_TIMEOUT,
    )


def run_article_post_flow(
    is_dry_run: bool,
    article_history_file: str,
    article_history_max_entries: int,
    article_cooldown_posts: int,
) -> int:
    log("INFO", "Collecting candidates from RSS feeds and Hacker News...")
    candidates = collect_candidates()

    recent_article_keys = load_article_history(article_history_file, article_history_max_entries)
    recent_article_set = recent_article_key_window(recent_article_keys, article_cooldown_posts)
    if recent_article_set:
        before_count = len(candidates)
        candidates = [
            candidate
            for candidate in candidates
            if normalize_article_url_for_history(candidate.url) not in recent_article_set
        ]
        filtered_count = before_count - len(candidates)
        if filtered_count > 0:
            log(
                "INFO",
                f"Article history pre-filter removed {filtered_count} candidate(s) "
                f"(cooldown={min(article_cooldown_posts, len(recent_article_keys))}).",
            )

    selected = choose_top_article(candidates)

    if not selected:
        log("WARN", "No relevant AI/finance article found; skipping this run.")
        return 0

    selected_article_key = normalize_article_url_for_history(selected.url)

    profile = choose_length_profile()
    post_text = build_post(selected, profile)
    log(
        "INFO",
        f"Selected article: '{selected.title}' ({selected.source}) | "
        f"profile={profile.name} | words={word_count(post_text)} | "
        f"image_preview={'yes' if selected.preview_image_url else 'no'}",
    )

    if is_dry_run:
        print("\n--- LinkedIn Post Preview ---\n")
        print(post_text)
        return 0

    linkedin_token = os.getenv("LINKEDIN_TOKEN", "").strip()
    linkedin_person_urn = os.getenv("LINKEDIN_PERSON_URN", "").strip()
    if not linkedin_token or not linkedin_person_urn:
        log("ERROR", "Missing LINKEDIN_TOKEN or LINKEDIN_PERSON_URN. Cannot publish.")
        return 1

    try:
        response = post_to_linkedin(post_text, selected, linkedin_token, linkedin_person_urn)
    except requests.RequestException as error:
        log("ERROR", f"LinkedIn API request failed: {error}")
        return 1

    if response.status_code not in (200, 201):
        log("ERROR", f"LinkedIn API failed with HTTP {response.status_code}")
        print(response.text)
        return 1

    if selected_article_key:
        updated_article_history = unique_preserve_order(recent_article_keys + [selected_article_key])[
            -article_history_max_entries:
        ]
        try:
            save_article_history(article_history_file, updated_article_history, article_history_max_entries)
        except OSError as error:
            log("WARN", f"Article post succeeded but failed to persist history ({error}).")
        else:
            log("INFO", f"Persisted article history: {len(updated_article_history)} entries.")

    log("INFO", "LinkedIn post created successfully.")
    print(response.text)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Auto-repost trending AI and finance news to LinkedIn.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and generate a post, but do not publish to LinkedIn.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Optional random seed for deterministic local testing.",
    )
    parser.add_argument(
        "--ignore-random-schedule",
        action="store_true",
        help="Run immediately even if today's scheduled random weekday gate would skip.",
    )
    args = parser.parse_args()

    load_dotenv()
    if args.seed is not None:
        random.seed(args.seed)
    is_dry_run = args.dry_run or os.getenv("DRY_RUN", "").strip().lower() == "true"
    direct_repost_only = os.getenv("LINKEDIN_DIRECT_REPOST_ONLY", "true").strip().lower() != "false"
    randomize_weekly_run_days = os.getenv("RANDOMIZE_WEEKLY_RUN_DAYS", "true").strip().lower() != "false"
    event_name = os.getenv("GITHUB_EVENT_NAME", "").strip().lower()
    repost_history_file = (
        os.getenv("REPOST_HISTORY_FILE", DEFAULT_REPOST_HISTORY_FILE).strip()
        or DEFAULT_REPOST_HISTORY_FILE
    )
    repost_history_max_entries = parse_positive_int_env(
        "REPOST_HISTORY_MAX_ENTRIES",
        DEFAULT_REPOST_HISTORY_MAX_ENTRIES,
    )
    repost_cooldown_posts = parse_positive_int_env("REPOST_COOLDOWN_POSTS", DEFAULT_REPOST_COOLDOWN_POSTS)
    article_history_file = (
        os.getenv("ARTICLE_HISTORY_FILE", DEFAULT_ARTICLE_HISTORY_FILE).strip()
        or DEFAULT_ARTICLE_HISTORY_FILE
    )
    article_history_max_entries = parse_positive_int_env(
        "ARTICLE_HISTORY_MAX_ENTRIES",
        DEFAULT_ARTICLE_HISTORY_MAX_ENTRIES,
    )
    article_cooldown_posts = parse_positive_int_env("ARTICLE_COOLDOWN_POSTS", DEFAULT_ARTICLE_COOLDOWN_POSTS)
    max_repost_age_days = parse_max_repost_age_days_env()
    direct_repost_article_fallback = os.getenv("DIRECT_REPOST_ARTICLE_FALLBACK", "true").strip().lower() != "false"

    if randomize_weekly_run_days and event_name == "schedule" and not args.ignore_random_schedule:
        now_utc = datetime.now(timezone.utc)
        seed_material = (
            os.getenv("RANDOM_SCHEDULE_SEED", "").strip()
            or os.getenv("GITHUB_REPOSITORY", "").strip()
            or "linkedin-ai-finance-reposter"
        )
        selected_days = weekly_random_run_days(seed_material, now_utc)
        today = now_utc.weekday()
        selected_day_labels = [WEEKDAY_NAMES[day] for day in selected_days]
        log(
            "INFO",
            f"Weekly random schedule days: {', '.join(selected_day_labels)} | today={WEEKDAY_NAMES[today]}",
        )
        if today not in selected_days:
            log("INFO", "Today is not one of this week's selected random run days; skipping.")
            return 0

    if direct_repost_only:
        log("INFO", "Direct repost mode enabled. Discovering public LinkedIn posts...")
        repost_candidates = fetch_linkedin_repost_candidates()
        if not repost_candidates:
            log("WARN", "No repostable LinkedIn post candidates found.")
            if direct_repost_article_fallback:
                log("WARN", "Falling back to article mode to keep posting cadence.")
                return run_article_post_flow(
                    is_dry_run,
                    article_history_file,
                    article_history_max_entries,
                    article_cooldown_posts,
                )
            log("WARN", "Skipping this run because fallback mode is disabled.")
            return 0
        repost_candidates = filter_repost_candidates_by_freshness(repost_candidates, max_repost_age_days)
        if not repost_candidates:
            log(
                "WARN",
                "All discovered repost candidates were older than the freshness window or had unknown age; "
                f"MAX_REPOST_AGE_DAYS={max_repost_age_days}.",
            )
            if direct_repost_article_fallback:
                log("WARN", "Falling back to article mode to keep posting cadence.")
                return run_article_post_flow(
                    is_dry_run,
                    article_history_file,
                    article_history_max_entries,
                    article_cooldown_posts,
                )
            log("WARN", "Skipping this run because fallback mode is disabled.")
            return 0
        repost_candidates = prioritize_repost_candidates_for_run(repost_candidates)
        recent_parent_urns = load_repost_history(repost_history_file, repost_history_max_entries)
        if recent_parent_urns:
            log(
                "INFO",
                f"Loaded repost history entries={len(recent_parent_urns)} from {repost_history_file}.",
            )
            recent_urn_set = recent_parent_urn_window(recent_parent_urns, repost_cooldown_posts)
            before_count = len(repost_candidates)
            repost_candidates = [
                candidate
                for candidate in repost_candidates
                if not any(urn in recent_urn_set for urn in candidate.parent_urn_candidates)
            ]
            filtered_count = before_count - len(repost_candidates)
            if filtered_count > 0:
                log(
                    "INFO",
                    f"History pre-filter removed {filtered_count} URL-derived candidate(s) "
                    f"(cooldown={min(repost_cooldown_posts, len(recent_parent_urns))}).",
                )
        else:
            log("INFO", f"No repost history found at {repost_history_file}; starting with an empty history.")

        if not repost_candidates:
            log(
                "WARN",
                "All current repost candidates are in the recent history cooldown window.",
            )
            if direct_repost_article_fallback:
                log("WARN", "Falling back to article mode to keep posting cadence.")
                return run_article_post_flow(
                    is_dry_run,
                    article_history_file,
                    article_history_max_entries,
                    article_cooldown_posts,
                )
            log("WARN", "Skipping this run because fallback mode is disabled.")
            return 0

        top_candidate = repost_candidates[0]
        top_commentary = build_direct_reshare_commentary(top_candidate)
        age_days = None
        if top_candidate.inferred_created_at is not None:
            age_days = (datetime.now(timezone.utc) - top_candidate.inferred_created_at).total_seconds() / 86400.0
        log(
            "INFO",
            f"Top direct repost candidate: '{top_candidate.title}' ({top_candidate.source}) | "
            f"score={top_candidate.score:.1f} | urn_options={len(top_candidate.parent_urn_candidates)}"
            + (f" | age_days={age_days:.1f}" if age_days is not None else ""),
        )

        if is_dry_run:
            print("\n--- Direct Repost Preview ---\n")
            print(top_commentary)
            print(f"\nSource post URL: {top_candidate.url}")
            print("Parent URN attempts:")
            for parent_urn in top_candidate.parent_urn_candidates:
                print(f"- {parent_urn}")
            return 0

        linkedin_token = os.getenv("LINKEDIN_TOKEN", "").strip()
        linkedin_person_urn = os.getenv("LINKEDIN_PERSON_URN", "").strip()
        if not linkedin_token or not linkedin_person_urn:
            log("ERROR", "Missing LINKEDIN_TOKEN or LINKEDIN_PERSON_URN. Cannot publish.")
            return 1

        direct_result = publish_direct_repost(
            repost_candidates[:15],
            linkedin_token,
            linkedin_person_urn,
            recent_parent_urns=recent_parent_urns,
            cooldown_posts=repost_cooldown_posts,
            history_file_path=repost_history_file,
            history_max_entries=repost_history_max_entries,
        )
        if direct_result != 0 and direct_repost_article_fallback:
            log("WARN", "Direct repost publish failed; falling back to article mode.")
            return run_article_post_flow(
                    is_dry_run,
                    article_history_file,
                    article_history_max_entries,
                    article_cooldown_posts,
                )
        return direct_result

    return run_article_post_flow(
                    is_dry_run,
                    article_history_file,
                    article_history_max_entries,
                    article_cooldown_posts,
                )


if __name__ == "__main__":
    raise SystemExit(main())
