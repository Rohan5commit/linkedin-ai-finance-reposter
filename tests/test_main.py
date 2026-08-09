from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import main  # noqa: E402


class CadenceFallbackTests(unittest.TestCase):
    def test_publish_direct_repost_reports_no_unused_candidates_for_duplicate_only_run(self) -> None:
        candidate = main.RepostCandidate(
            title="Recent AI finance post",
            url="https://www.linkedin.com/posts/example_activity-7468246599257796608-test",
            source="test",
            topic="ai-finance",
            score=10.0,
            parent_urn_candidates=["urn:li:share:7468246599257796608"],
        )

        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "main.discover_parent_urn_candidates_from_page", return_value=[]
        ), patch("main.post_direct_reshare") as post_direct, patch(
            "main.post_direct_reshare_via_ugc"
        ) as post_ugc:
            result = main.publish_direct_repost(
                [candidate],
                token="token",
                person_urn="urn:li:person:test",
                recent_parent_urns=["urn:li:share:7468246599257796608"],
                cooldown_posts=120,
                history_file_path=str(Path(temp_dir) / "history.json"),
            )

        self.assertEqual(result, main.DIRECT_REPOST_NO_UNUSED_CANDIDATES)
        post_direct.assert_not_called()
        post_ugc.assert_not_called()

    def test_article_flow_relaxes_history_when_cooldown_filters_every_candidate(self) -> None:
        candidate = main.ArticleCandidate(
            title="AI startup raises new funding",
            url="https://example.com/story?utm_source=test",
            source="Example News",
            summary_hint="The company announced a new funding round for AI products.",
            published_at=datetime.now(timezone.utc),
            topic="ai-finance",
            score=50.0,
            preview_image_url="https://example.com/image.jpg",
        )
        history_key = main.normalize_article_url_for_history(candidate.url)

        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "main.collect_candidates", return_value=[candidate]
        ), patch("main.build_post", return_value="Generated post"), patch(
            "main.choose_length_profile", return_value=main.SHORT_PROFILE
        ):
            history_file = Path(temp_dir) / "article_history.json"
            main.save_article_history(str(history_file), [history_key], 10)
            result = main.run_article_post_flow(
                is_dry_run=True,
                article_history_file=str(history_file),
                article_history_max_entries=10,
                article_cooldown_posts=10,
            )

        self.assertEqual(result, 0)

    def test_main_falls_back_to_article_when_all_direct_reposts_are_duplicates(self) -> None:
        fresh_candidate = main.RepostCandidate(
            title="Fresh AI finance repost",
            url="https://www.linkedin.com/posts/example_activity-7468246599257796608-test",
            source="test",
            topic="ai-finance",
            score=10.0,
            parent_urn_candidates=["urn:li:share:7468246599257796608"],
            inferred_created_at=datetime.now(timezone.utc),
        )

        with patch.dict(
            "main.os.environ",
            {
                "LINKEDIN_TOKEN": "token",
                "LINKEDIN_PERSON_URN": "urn:li:person:test",
                "RANDOMIZE_WEEKLY_RUN_DAYS": "false",
                "LINKEDIN_DIRECT_REPOST_ONLY": "true",
                "DIRECT_REPOST_ARTICLE_FALLBACK": "true",
            },
            clear=True,
        ), patch("main.load_dotenv"), patch(
            "main.fetch_linkedin_repost_candidates", return_value=[fresh_candidate]
        ), patch("main.filter_repost_candidates_by_freshness", return_value=[fresh_candidate]), patch(
            "main.load_repost_history", return_value=[]
        ), patch("main.prioritize_repost_candidates_for_run", return_value=[fresh_candidate]), patch(
            "main.publish_direct_repost", return_value=main.DIRECT_REPOST_NO_UNUSED_CANDIDATES
        ), patch("main.check_linkedin_token_health", return_value="token"), patch(
            "main.run_article_post_flow", return_value=0
        ) as article_flow, patch(
            "sys.argv", ["main.py"]
        ):
            result = main.main()

        self.assertEqual(result, 0)
        article_flow.assert_called_once()


if __name__ == "__main__":
    unittest.main()
