from __future__ import annotations

import sys
import tempfile
import threading
import time
import unittest
import urllib.error
from argparse import Namespace
from datetime import datetime, timedelta, timezone
from email.message import Message
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import discover_tools
import generate_editor_choice
import import_exakat_catalog
import update_catalog
import catalog_lib
from catalog_lib import (
    CATEGORY_IDS,
    CATEGORY_ORDER,
    dump_yaml,
    load_yaml,
    read_editor_choice_copy,
    read_editor_choice_slugs,
    read_pros_cons,
    save_tool,
)
from generate_readme import (
    CATEGORY_TITLES,
    apply_editor_choice_copy,
    editor_row,
    editor_section,
    is_dead,
    latest_release_value,
    lifecycle,
    memorial_section,
    repository_badges,
    resources_value,
    saas_row,
    section,
    sorted_for_table,
    tool_row,
)


class CatalogScriptTests(unittest.TestCase):
    REFERENCE_TIME = datetime(2026, 8, 6, tzinfo=timezone.utc)

    def test_repository_badges_use_current_repository_name(self) -> None:
        self.assertEqual(
            repository_badges(),
            [
                "![GitHub last commit](https://img.shields.io/github/last-commit/ValentinNikolaev/php-analysis-tools-catalog)",
                "![visitors](https://visitor-badge.laobi.icu/badge?page_id=ValentinNikolaev.php-analysis-tools-catalog)",
            ],
        )

    def test_yaml_round_trip_keeps_public_url_fields(self) -> None:
        data = {
            "slug": "sample",
            "name": "Sample",
            "public_url": "https://example.com",
            "website_status": "available",
            "website_status_code": 200,
            "website_checked_at": "2026-07-25T00:00:00Z",
            "website_error": "",
            "latest_version": "1.2.3",
            "latest_version_released_at": "2026-07-20T00:00:00+00:00",
            "latest_release_name": "Released Sample 1.2.3",
            "latest_release_tag": "v1.2.3",
            "latest_release_url": "https://github.com/example/sample/releases/tag/v1.2.3",
            "latest_release_published_at": "2026-07-20T00:00:00Z",
            "latest_release_checked_at": "2026-08-06T00:00:00Z",
            "quality_tags": ["php", "static-analysis"],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.yaml"
            path.write_text(dump_yaml(data), encoding="utf-8")
            self.assertEqual(load_yaml(path), data)

    def test_yaml_round_trip_supports_nested_and_empty_containers(self) -> None:
        data = {
            "metadata": {"enabled": True, "count": 2, "tags": ["php", "analysis"]},
            "empty_mapping": {},
            "empty_list": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested.yaml"
            path.write_text(dump_yaml(data), encoding="utf-8")
            self.assertEqual(load_yaml(path), data)

    def test_catalog_timestamps_support_as_of_and_source_date_epoch(self) -> None:
        self.assertEqual(catalog_lib.now_iso("2026-08-08"), "2026-08-08T00:00:00Z")
        with patch.dict(catalog_lib.os.environ, {"SOURCE_DATE_EPOCH": "0"}):
            self.assertEqual(catalog_lib.now_iso(), "1970-01-01T00:00:00Z")

    def test_discovery_static_analysis_query_uses_inclusive_star_threshold(self) -> None:
        self.assertIn("topic:php topic:static-analysis stars:>20", discover_tools.QUERIES)
        self.assertNotIn("topic:php topic:static-analysis stars:>100", discover_tools.QUERIES)

    def test_discovery_covers_extensions_rulesets_and_non_php_implementations(self) -> None:
        self.assertTrue(any("PHPStan extension" in query for query in discover_tools.QUERIES))
        self.assertTrue(any("PHPCS coding standard" in query for query in discover_tools.QUERIES))
        self.assertTrue(any("PHP static analyzer" in query and "language:" not in query for query in discover_tools.QUERIES))
        self.assertIn(("phpstan extension", "Bugs finders"), discover_tools.PACKAGIST_QUERIES)
        self.assertIn(("phpcs standard", "Coding standards"), discover_tools.PACKAGIST_QUERIES)
        self.assertIn(("rector rules", "Fixers"), discover_tools.PACKAGIST_QUERIES)

    def test_discovery_infers_categories_instead_of_defaulting_everything_to_bug_finders(self) -> None:
        self.assertEqual(
            discover_tools.infer_category(
                {"name": "Formatter", "description": "Automatically fixes PHP style", "topics": []},
                "Bugs finders",
            ),
            "Fixers",
        )
        self.assertEqual(
            discover_tools.infer_category(
                {"name": "Metrics", "description": "Reports complexity metrics", "topics": []},
                "Bugs finders",
            ),
            "Metrics",
        )

    def test_exakat_import_parses_supported_categories_and_github_entries(self) -> None:
        source = """
### Bugs finders
* [Active Analyzer](https://github.com/example/active) - Finds bugs.
### Visualization
* [Code City](https://github.com/example/city) - Shows code as a city.
## Misc
* [Website Only](https://example.com/tool) - Not verifiable through GitHub.
"""
        self.assertEqual(
            import_exakat_catalog.parse_source_readme(source),
            [
                {
                    "name": "Active Analyzer",
                    "repository": "https://github.com/example/active",
                    "description": "Finds bugs.",
                    "category": "Bugs finders",
                },
                {
                    "name": "Code City",
                    "repository": "https://github.com/example/city",
                    "description": "Shows code as a city.",
                    "category": "Misc",
                },
            ],
        )

    def test_github_release_name_accepts_arbitrary_author_text(self) -> None:
        examples = [
            ("Release v5.0.14", "v5.0.14"),
            ("PHP 7.1 Support", "v1.1.0"),
            ("Released ECS 13.2.15", "13.2.15"),
        ]
        for name, tag in examples:
            with self.subTest(name=name):
                tool = {"slug": "sample"}
                release = {
                    "name": name,
                    "tag_name": tag,
                    "html_url": f"https://github.com/example/sample/releases/tag/{tag}",
                    "published_at": "2026-07-20T00:00:00Z",
                }
                with patch("update_catalog.http_json", return_value=release):
                    result = update_catalog.update_github_release(tool, "example/sample", None)
                self.assertTrue(result.checked)
                self.assertTrue(result.changed)
                self.assertEqual(tool["latest_release_name"], name)
                self.assertEqual(tool["latest_release_tag"], tag)

    def test_github_release_uses_tag_when_author_title_is_blank(self) -> None:
        tool = {"slug": "sample"}
        release = {
            "name": "",
            "tag_name": "v2.0.0",
            "html_url": "https://github.com/example/sample/releases/tag/v2.0.0",
            "published_at": "2026-07-20T00:00:00Z",
        }
        with patch("update_catalog.http_json", return_value=release):
            update_catalog.update_github_release(tool, "example/sample", None)
        self.assertEqual(tool["latest_release_name"], "v2.0.0")

    def test_rate_limited_github_release_check_is_not_marked_fresh(self) -> None:
        tool = {"slug": "sample"}
        error = urllib.error.HTTPError(
            "https://api.github.com/repos/example/sample/releases/latest",
            403,
            "rate limit exceeded",
            Message(),
            None,
        )
        self.addCleanup(error.close)
        with patch("update_catalog.http_json", side_effect=error):
            result = update_catalog.update_github_release(tool, "example/sample", None)

        self.assertFalse(result.checked)
        self.assertFalse(result.changed)

    def test_mismatched_packagist_package_is_removed(self) -> None:
        tool = {
            "slug": "expected-tool",
            "repository": "https://github.com/acme/expected-tool",
            "packagist": "https://packagist.org/packages/other/wrong-package",
            "latest_version": "9.9.9",
            "latest_version_released_at": "2026-01-01T00:00:00Z",
        }
        package = {
            "packages": {
                "other/wrong-package": [
                    {
                        "version": "9.9.9",
                        "source": {"url": "https://github.com/other/wrong-package.git"},
                    }
                ]
            }
        }
        with (
            patch("update_catalog.http_json", return_value=package),
            patch("update_catalog.github_repositories_match", return_value=False),
        ):
            result = update_catalog.update_packagist_version(tool)
        self.assertTrue(result.changed)
        self.assertTrue(result.checked)
        self.assertFalse(result.package_valid)
        self.assertIsNone(tool["packagist"])
        self.assertEqual(tool["latest_version"], "")

    def test_packagist_package_without_verifiable_releases_is_removed(self) -> None:
        tool = {
            "slug": "expected-tool",
            "repository": "https://github.com/acme/expected-tool",
            "packagist": "https://packagist.org/packages/other/empty-package",
        }
        with patch("update_catalog.http_json", return_value={"packages": {"other/empty-package": []}}):
            result = update_catalog.update_packagist_version(tool)
        self.assertTrue(result.changed)
        self.assertTrue(result.checked)
        self.assertFalse(result.package_valid)
        self.assertIsNone(tool["packagist"])

    def test_packagist_metadata_can_validate_a_distribution_source_repository(self) -> None:
        tool = {
            "slug": "php-stan",
            "repository": "https://github.com/phpstan/phpstan",
            "packagist": "https://packagist.org/packages/phpstan/phpstan",
        }
        versions = {
            "packages": {
                "phpstan/phpstan": [
                    {
                        "version": "2.2.5",
                        "version_normalized": "2.2.5.0",
                        "time": "2026-07-05T06:31:06+00:00",
                        "source": {"url": "https://github.com/phpstan/phpstan-phar-composer-source.git"},
                    }
                ]
            }
        }
        metadata = {"package": {"repository": "https://github.com/phpstan/phpstan"}}
        with (
            patch("update_catalog.http_json", side_effect=[versions, metadata]),
            patch(
                "update_catalog.github_repositories_match",
                side_effect=lambda expected, candidate, token: expected.casefold() == (candidate or "").casefold(),
            ),
        ):
            result = update_catalog.update_packagist_version(tool)
        self.assertTrue(result.changed)
        self.assertTrue(result.checked)
        self.assertTrue(result.package_valid)
        self.assertEqual(tool["latest_version"], "2.2.5")

    def test_packagist_search_does_not_fall_back_to_first_result(self) -> None:
        tool = {
            "slug": "expected-tool",
            "name": "Expected Tool",
            "repository": "https://github.com/acme/expected-tool",
            "packagist": None,
        }
        search = {
            "results": [
                {
                    "url": "https://packagist.org/packages/other/wrong-package",
                    "repository": "https://github.com/other/wrong-package",
                }
            ]
        }
        with (
            patch("update_catalog.http_json", return_value=search),
            patch("update_catalog.github_repositories_match", return_value=False),
        ):
            result = update_catalog.update_from_packagist(tool)
        self.assertFalse(result.changed)
        self.assertTrue(result.checked)
        self.assertIsNone(tool["packagist"])

    def test_refresh_plan_skips_all_fresh_sources_with_explicit_source_timestamps(self) -> None:
        tool = {
            "slug": "sample",
            "repository": "https://github.com/example/sample",
            "packagist": "https://packagist.org/packages/example/sample",
            "public_url": "https://example.com",
            "metadata_updated_at": "2026-08-06T00:00:00Z",
            "packagist_checked_at": "2026-08-06T00:00:00Z",
            "website_checked_at": "2026-08-06T00:00:00Z",
        }
        args = Namespace(
            force=False,
            max_age_hours=20,
            packagist_max_age_hours=20,
            website_max_age_hours=20,
            skip_packagist=False,
            skip_website=False,
        )

        plan = update_catalog.refresh_plan(tool, args, self.REFERENCE_TIME)

        self.assertFalse(plan.has_work)
        self.assertFalse(plan.packagist)

    def test_github_sources_become_stale_at_twenty_four_hours(self) -> None:
        tool = {
            "slug": "sample",
            "repository": "https://github.com/example/sample",
            "metadata_updated_at": "2026-08-05T00:00:00Z",
            "latest_release_checked_at": "2026-08-05T00:00:00Z",
        }
        args = Namespace(
            force=False,
            max_age_hours=update_catalog.DEFAULT_GITHUB_MAX_AGE_HOURS,
            packagist_max_age_hours=20,
            website_max_age_hours=20,
            skip_packagist=True,
            skip_website=True,
        )

        fresh_plan = update_catalog.refresh_plan(
            tool,
            args,
            self.REFERENCE_TIME - timedelta(hours=1),
        )
        stale_plan = update_catalog.refresh_plan(tool, args, self.REFERENCE_TIME)

        self.assertEqual(update_catalog.DEFAULT_GITHUB_MAX_AGE_HOURS, 24)
        self.assertFalse(fresh_plan.github)
        self.assertFalse(fresh_plan.github_release)
        self.assertTrue(stale_plan.github)
        self.assertTrue(stale_plan.github_release)

    def test_failed_release_is_retried_without_refreshing_fresh_repository_metadata(self) -> None:
        tool = {
            "slug": "sample",
            "repository": "https://github.com/example/sample",
            "metadata_updated_at": "2026-07-01T00:00:00Z",
        }
        plan = update_catalog.RefreshPlan(
            github=True,
            github_release=True,
            packagist=False,
            website=False,
        )
        checked_at = "2026-08-06T00:00:00Z"
        with (
            patch("update_catalog.update_from_github", return_value=update_catalog.SourceResult(False, True)),
            patch("update_catalog.update_github_release", return_value=update_catalog.SourceResult(False, False)),
        ):
            result = update_catalog.refresh_tool(tool, plan, None, checked_at)

        args = Namespace(
            force=False,
            max_age_hours=24,
            packagist_max_age_hours=20,
            website_max_age_hours=20,
            skip_packagist=True,
            skip_website=True,
        )
        next_plan = update_catalog.refresh_plan(
            result.tool,
            args,
            self.REFERENCE_TIME + timedelta(hours=1),
        )

        self.assertEqual(result.tool["metadata_updated_at"], checked_at)
        self.assertIsNone(result.tool["latest_release_checked_at"])
        self.assertFalse(next_plan.github)
        self.assertTrue(next_plan.github_release)

    def test_successful_release_retry_updates_only_its_own_timestamp(self) -> None:
        tool = {
            "slug": "sample",
            "repository": "https://github.com/example/sample",
            "metadata_updated_at": "2026-08-06T00:00:00Z",
            "latest_release_checked_at": None,
        }
        plan = update_catalog.RefreshPlan(
            github=False,
            github_release=True,
            packagist=False,
            website=False,
        )
        checked_at = "2026-08-06T01:00:00Z"
        with (
            patch("update_catalog.update_from_github") as repo_update,
            patch("update_catalog.update_github_release", return_value=update_catalog.SourceResult(True, True)),
        ):
            result = update_catalog.refresh_tool(tool, plan, None, checked_at)

        repo_update.assert_not_called()
        self.assertEqual(result.tool["metadata_updated_at"], "2026-08-06T00:00:00Z")
        self.assertEqual(result.tool["latest_release_checked_at"], checked_at)
        self.assertTrue(result.github_release_checked)

    def test_refresh_tool_records_timestamps_only_for_successful_sources(self) -> None:
        tool = {
            "slug": "sample",
            "repository": "https://github.com/example/sample",
            "packagist": "https://packagist.org/packages/example/sample",
            "metadata_updated_at": "2026-07-01T00:00:00Z",
        }
        plan = update_catalog.RefreshPlan(github=True, packagist=True, website=False)
        checked_at = "2026-08-06T00:00:00Z"
        with (
            patch("update_catalog.update_from_github", return_value=update_catalog.SourceResult(False, False)),
            patch("update_catalog.update_from_packagist", return_value=update_catalog.SourceResult(False, True)),
        ):
            result = update_catalog.refresh_tool(tool, plan, None, checked_at)

        self.assertEqual(result.tool["metadata_updated_at"], "2026-07-01T00:00:00Z")
        self.assertEqual(result.tool["packagist_checked_at"], checked_at)
        self.assertFalse(result.github_checked)
        self.assertTrue(result.packagist_checked)
        self.assertTrue(result.save_needed)

    def test_failed_packagist_check_remains_stale_after_github_success(self) -> None:
        tool = {
            "slug": "sample",
            "repository": "https://github.com/example/sample",
            "packagist": "https://packagist.org/packages/example/sample",
            "metadata_updated_at": "2026-07-01T00:00:00Z",
        }
        plan = update_catalog.RefreshPlan(github=True, packagist=True, website=False)
        checked_at = "2026-08-06T00:00:00Z"
        with (
            patch("update_catalog.update_from_github", return_value=update_catalog.SourceResult(False, True)),
            patch("update_catalog.update_from_packagist", return_value=update_catalog.SourceResult(False, False)),
        ):
            result = update_catalog.refresh_tool(tool, plan, None, checked_at)

        next_run = self.REFERENCE_TIME + timedelta(hours=12)
        args = Namespace(
            force=False,
            max_age_hours=20,
            packagist_max_age_hours=20,
            website_max_age_hours=20,
            skip_packagist=False,
            skip_website=False,
        )
        next_plan = update_catalog.refresh_plan(result.tool, args, next_run)

        self.assertEqual(result.tool["metadata_updated_at"], checked_at)
        self.assertNotIn("packagist_checked_at", result.tool)
        self.assertFalse(next_plan.github)
        self.assertTrue(next_plan.packagist)

    def test_website_check_persists_the_supplied_freshness_time(self) -> None:
        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

        tool = {"slug": "sample", "public_url": "https://example.com"}
        checked_at = "2026-08-06T00:00:00Z"
        with patch("update_catalog.urllib.request.urlopen", return_value=Response()):
            result = update_catalog.check_website(tool, checked_at=checked_at)

        self.assertTrue(result.checked)
        self.assertTrue(result.changed)
        self.assertEqual(tool["website_checked_at"], checked_at)
        self.assertEqual(tool["website_status"], "available")

    def test_refresh_tools_runs_concurrently_and_preserves_catalog_order(self) -> None:
        barrier = threading.Barrier(2)
        lock = threading.Lock()
        active = 0
        maximum_active = 0

        def fake_refresh(tool, plan, token, checked_at):
            nonlocal active, maximum_active
            with lock:
                active += 1
                maximum_active = max(maximum_active, active)
            barrier.wait(timeout=2)
            time.sleep(0.01 if tool["slug"] == "first" else 0)
            with lock:
                active -= 1
            return update_catalog.ToolRefreshResult(tool, False, False, False, False, False)

        work_items = [
            ({"slug": slug}, update_catalog.RefreshPlan(True, False, False))
            for slug in ["first", "second", "third", "fourth"]
        ]
        with patch("update_catalog.refresh_tool", side_effect=fake_refresh):
            results = update_catalog.refresh_tools(work_items, None, "2026-08-06T00:00:00Z", workers=2)

        self.assertEqual(maximum_active, 2)
        self.assertEqual([result.tool["slug"] for result in results], ["first", "second", "third", "fourth"])

    def test_update_limit_caps_checked_tools_instead_of_changed_tools(self) -> None:
        captured: list[tuple[dict, update_catalog.RefreshPlan]] = []
        tools = [{"slug": slug} for slug in ["first", "second", "third"]]
        plan = update_catalog.RefreshPlan(github=True, packagist=False, website=False)

        def fake_refresh_tools(work_items, token, checked_at, workers):
            captured.extend(work_items)
            return [
                update_catalog.ToolRefreshResult(tool, False, False, False, False, False)
                for tool, _ in work_items
            ]

        with (
            patch("update_catalog.load_catalog", return_value=tools),
            patch("update_catalog.refresh_plan", return_value=plan),
            patch("update_catalog.refresh_tools", side_effect=fake_refresh_tools),
            patch("update_catalog.save_tool"),
            patch("builtins.print"),
            patch.object(sys, "argv", ["update_catalog.py", "--limit", "2"]),
        ):
            update_catalog.main()

        self.assertEqual([tool["slug"] for tool, _ in captured], ["first", "second"])

    def test_http_retry_delay_honors_short_retry_after_and_rejects_long_waits(self) -> None:
        short_headers = Message()
        short_headers["Retry-After"] = "7"
        short_error = urllib.error.HTTPError("https://example.com", 429, "rate limited", short_headers, None)
        self.addCleanup(short_error.close)
        self.assertEqual(catalog_lib.http_retry_delay(short_error, 0), 7)

        long_headers = Message()
        long_headers["Retry-After"] = "120"
        long_error = urllib.error.HTTPError("https://example.com", 429, "rate limited", long_headers, None)
        self.addCleanup(long_error.close)
        self.assertIsNone(catalog_lib.http_retry_delay(long_error, 0))

    def test_candidate_slug_uses_owner_when_catalog_slug_is_occupied(self) -> None:
        repo = {"name": "phpqa", "full_name": "jakzal/phpqa"}
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            (output_dir / "phpqa.yaml").write_text(
                dump_yaml({"slug": "phpqa", "name": "PHPQA", "repository": None}),
                encoding="utf-8",
            )
            slug, already_exists = discover_tools.choose_output_slug(repo, output_dir, set())
        self.assertEqual(slug, "jakzal-phpqa")
        self.assertFalse(already_exists)

    def test_candidate_slug_preserves_existing_repository_file(self) -> None:
        repo = {"name": "phpqa", "full_name": "jakzal/phpqa"}
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            (output_dir / "phpqa.yaml").write_text(
                dump_yaml({"slug": "phpqa", "name": "phpqa", "repository": "https://github.com/jakzal/phpqa"}),
                encoding="utf-8",
            )
            slug, already_exists = discover_tools.choose_output_slug(repo, output_dir, set())
        self.assertEqual(slug, "phpqa")
        self.assertTrue(already_exists)

    def test_existing_candidates_are_known_to_discovery(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate_dir = root / "common" / "candidates"
            candidate_dir.mkdir(parents=True)
            (candidate_dir / "phpqa.yaml").write_text(
                dump_yaml({"slug": "phpqa", "repository": "https://github.com/jakzal/phpqa"}),
                encoding="utf-8",
            )
            with patch.object(discover_tools, "ROOT", root):
                keys = discover_tools.candidate_repository_keys()
        self.assertEqual(keys, {"jakzal/phpqa"})

    def test_discovery_does_not_requeue_rejected_candidates_or_reuse_their_slugs(self) -> None:
        rejected = {
            "slug": "blocked",
            "name": "Blocked",
            "repository": "https://github.com/blocked/blocked",
            "reason": "Outside the catalog scope.",
            "rejected_at": "2026-08-08",
            "reconsider_after": None,
        }
        rejected_repo = {
            "name": "blocked",
            "full_name": "blocked/blocked",
            "html_url": "https://github.com/blocked/blocked",
            "description": "Rejected candidate",
            "stargazers_count": 100,
            "topics": ["php"],
        }
        allowed_repo = {
            "name": "blocked",
            "full_name": "other/blocked",
            "html_url": "https://github.com/other/blocked",
            "description": "Different candidate with the same repository name",
            "stargazers_count": 50,
            "topics": ["php", "static-analysis"],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate_dir = root / "common" / "candidates"
            candidate_dir.mkdir(parents=True)
            (root / "common" / "rejected-candidates.yaml").write_text(
                dump_yaml({"reviewed_at": "2026-08-08", "rejections": [rejected]}),
                encoding="utf-8",
            )
            with (
                patch.object(discover_tools, "ROOT", root),
                patch("discover_tools.load_catalog", return_value=[]),
                patch("discover_tools.cli_token", return_value=None),
                patch("discover_tools.search_repositories", return_value=iter([rejected_repo, allowed_repo])),
                patch("builtins.print"),
                patch.object(
                    sys,
                    "argv",
                    [
                        "discover_tools.py",
                        "--write",
                        "--limit",
                        "1",
                        "--pages",
                        "1",
                        "--per-page",
                        "2",
                        "--skip-packagist-discovery",
                        "--skip-refresh-existing",
                        "--as-of",
                        "2026-08-09",
                    ],
                ),
            ):
                discover_tools.main()

            candidate_files = list(candidate_dir.glob("*.yaml"))
            self.assertEqual([path.name for path in candidate_files], ["other-blocked.yaml"])
            self.assertEqual(load_yaml(candidate_files[0])["repository"], allowed_repo["html_url"])

    def test_candidate_refresh_preserves_editorial_review_state(self) -> None:
        existing = {
            "slug": "sample",
            "repository": "https://github.com/example/sample",
            "website": "https://example.com/manual",
            "public_url": "https://example.com/manual",
            "category": "Coding standards",
            "review_status": "needs-info",
            "review_notes": "Waiting for maintenance evidence.",
            "discovered_at": "2026-01-01T00:00:00Z",
            "last_reviewed_at": "2026-07-01",
            "quality_tags": ["php"],
        }
        repo = {
            "html_url": "https://github.com/example/sample",
            "homepage": "https://example.com/upstream",
            "stargazers_count": 42,
            "pushed_at": "2026-08-01T00:00:00Z",
            "topics": ["static-analysis"],
        }
        refreshed = discover_tools.merge_candidate_metadata(existing, repo, "2026-08-08T00:00:00Z")
        self.assertEqual(refreshed["category"], "Coding standards")
        self.assertEqual(refreshed["review_status"], "needs-info")
        self.assertEqual(refreshed["review_notes"], "Waiting for maintenance evidence.")
        self.assertEqual(refreshed["discovered_at"], "2026-01-01T00:00:00Z")
        self.assertEqual(refreshed["stars"], 42)

    def test_recent_candidate_metadata_is_not_refetched(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate_dir = root / "common" / "candidates"
            candidate_dir.mkdir(parents=True)
            (candidate_dir / "sample.yaml").write_text(
                dump_yaml(
                    {
                        "slug": "sample",
                        "repository": "https://github.com/example/sample",
                        "metadata_updated_at": "2026-08-08T06:00:00Z",
                    }
                ),
                encoding="utf-8",
            )
            with (
                patch.object(discover_tools, "ROOT", root),
                patch("discover_tools.http_json") as request,
            ):
                refreshed, failed = discover_tools.refresh_existing_candidates(
                    None,
                    "2026-08-08T12:00:00Z",
                    write=True,
                    max_age_hours=24,
                )
        self.assertEqual((refreshed, failed), (0, 0))
        request.assert_not_called()

    def test_discovery_search_paginates(self) -> None:
        responses = [
            {"total_count": 3, "items": [{"full_name": "a/one"}, {"full_name": "b/two"}]},
            {"total_count": 3, "items": [{"full_name": "c/three"}]},
        ]
        with patch("discover_tools.http_json", side_effect=responses) as request:
            items = list(discover_tools.search_repositories("PHP analyzer", None, pages=3, per_page=2))
        self.assertEqual([item["full_name"] for item in items], ["a/one", "b/two", "c/three"])
        self.assertEqual(request.call_count, 2)
        self.assertIn("page=2", request.call_args_list[1].args[0])

    def test_packagist_discovery_search_paginates_using_next_link(self) -> None:
        responses = [
            {"total": 2, "results": [{"name": "a/one"}], "next": "page-2"},
            {"total": 2, "results": [{"name": "b/two"}], "next": None},
        ]
        with patch("discover_tools.http_json", side_effect=responses) as request:
            items = list(discover_tools.search_packagist("phpstan extension", pages=3, per_page=25))
        self.assertEqual([item["name"] for item in items], ["a/one", "b/two"])
        self.assertEqual(request.call_count, 2)
        self.assertIn("q=phpstan+extension", request.call_args_list[0].args[0])
        self.assertIn("page=2", request.call_args_list[1].args[0])

    def test_latest_release_uses_compact_tag_link(self) -> None:
        tool = {
            "latest_release_name": "PHP 7.1 Support",
            "latest_release_tag": "v1.1.0",
            "latest_release_url": "https://github.com/cwi-swat/php-analysis/releases/tag/v1.1.0",
        }
        self.assertEqual(
            latest_release_value(tool),
            "[v1.1.0](https://github.com/cwi-swat/php-analysis/releases/tag/v1.1.0)",
        )

    def test_lifecycle_uses_readable_activity_labels(self) -> None:
        self.assertEqual(lifecycle({"repo_updated_at": "2026-07-01T00:00:00Z"}, self.REFERENCE_TIME)[1], "Active")
        self.assertEqual(lifecycle({"repo_updated_at": "2026-03-01T00:00:00Z"}, self.REFERENCE_TIME)[1], "Quiet")
        self.assertEqual(lifecycle({"repo_updated_at": "2025-12-01T00:00:00Z"}, self.REFERENCE_TIME)[1], "Inactive")
        self.assertEqual(lifecycle({"repo_updated_at": "2024-01-01T00:00:00Z"}, self.REFERENCE_TIME)[1], "Unmaintained")
        self.assertEqual(lifecycle({}, self.REFERENCE_TIME)[1], "Unknown")

    def test_memorial_requires_an_explicit_historical_signal(self) -> None:
        self.assertFalse(is_dead({"repo_updated_at": "2024-01-01T00:00:00Z"}, self.REFERENCE_TIME))
        self.assertTrue(
            is_dead(
                {
                    "repo_updated_at": "2026-07-01T00:00:00Z",
                    "catalog_status": "historical",
                },
                self.REFERENCE_TIME,
            )
        )
        self.assertTrue(
            is_dead(
                {"repo_updated_at": "2026-07-01T00:00:00Z", "quality_tags": ["archived"]},
                self.REFERENCE_TIME,
            )
        )
        self.assertFalse(is_dead({"repo_updated_at": "2026-07-01T00:00:00Z"}, self.REFERENCE_TIME))

    def test_memorial_is_one_respectful_table(self) -> None:
        output = memorial_section(
            [
                {
                    "name": "Historic Analyzer",
                    "description": "Introduced foundational PHP analysis ideas.",
                    "category": "Bugs finders",
                    "public_url": "https://example.com/historic",
                    "repo_updated_at": "2018-01-01T00:00:00Z",
                }
            ]
        )
        self.assertIn("In Memoriam", output)
        self.assertIn("lasting contribution", output)
        self.assertEqual(output.count("| Project | Contribution | Category | Last activity | Legacy resources |"), 1)

    def test_table_sorting_groups_status_before_stars(self) -> None:
        tools = [
            {"name": "Dead High Stars", "stars": 100000, "repo_updated_at": "2024-01-01T00:00:00Z"},
            {"name": "Alive Low Stars", "stars": 1, "repo_updated_at": "2026-07-01T00:00:00Z"},
            {"name": "Alive High Stars", "stars": 10, "repo_updated_at": "2026-07-01T00:00:00Z"},
        ]
        self.assertEqual(
            [tool["name"] for tool in sorted_for_table(tools, self.REFERENCE_TIME)],
            ["Alive High Stars", "Alive Low Stars", "Dead High Stars"],
        )

    def test_editor_choice_allows_only_alive_projects(self) -> None:
        self.assertTrue(generate_editor_choice.is_alive({"repo_updated_at": "2026-07-01T00:00:00Z"}, self.REFERENCE_TIME))
        self.assertFalse(generate_editor_choice.is_alive({"repo_updated_at": "2026-03-01T00:00:00Z"}, self.REFERENCE_TIME))
        self.assertFalse(generate_editor_choice.is_alive({"repo_updated_at": "2024-01-01T00:00:00Z"}, self.REFERENCE_TIME))
        self.assertFalse(
            generate_editor_choice.is_alive(
                {"repo_updated_at": "2026-07-01T00:00:00Z", "quality_tags": ["archived"]},
                self.REFERENCE_TIME,
            )
        )
        self.assertFalse(generate_editor_choice.is_alive({}, self.REFERENCE_TIME))

    def test_editor_choice_requires_five_hundred_stars_for_repositories(self) -> None:
        active = {"repo_updated_at": "2026-07-01T00:00:00Z"}

        self.assertFalse(
            generate_editor_choice.is_editor_choice_candidate(
                {**active, "repository": "https://github.com/example/tool", "stars": 499},
                self.REFERENCE_TIME,
            )
        )
        self.assertTrue(
            generate_editor_choice.is_editor_choice_candidate(
                {**active, "repository": "https://github.com/example/tool", "stars": 500},
                self.REFERENCE_TIME,
            )
        )
        self.assertTrue(
            generate_editor_choice.is_editor_choice_candidate(
                {**active, "repository": None, "stars": 0},
                self.REFERENCE_TIME,
            )
        )
        self.assertFalse(
            generate_editor_choice.is_editor_choice_candidate(
                {
                    **active,
                    "repository": "https://github.com/example/historical",
                    "stars": 10000,
                    "quality_tags": ["historical-analysis-only"],
                },
                self.REFERENCE_TIME,
            )
        )

    def test_tool_row_combines_activity_release_and_uses_four_columns(self) -> None:
        row = tool_row(
            {
                "name": "PHP Stan",
                "description": "Static analysis",
                "public_url": "https://phpstan.org",
                "repository": "https://github.com/phpstan/phpstan",
                "packagist": "https://packagist.org/packages/phpstan/phpstan",
                "stars": 14042,
                "repo_updated_at": "2026-07-25T00:00:00Z",
                "latest_version": "2.2.5",
                "latest_version_released_at": "2026-07-20T00:00:00Z",
            },
            self.REFERENCE_TIME,
        )
        self.assertIn("![Last commit Jul 25, 2026]", row)
        self.assertIn("last%20commit-Jul%2025%2C%202026-brightgreen", row)
        self.assertNotIn("Active", row)
        self.assertIn("![Last release Jul 20, 2026]", row)
        self.assertIn("last%20release-Jul%2020%2C%202026-blue", row)
        self.assertIn("<br>2.2.5", row)
        self.assertIn("⭐ 14,042", row)
        self.assertNotIn("🥇", row)
        self.assertIn('](https://github.com/phpstan/phpstan "GitHub source")', row)
        self.assertIn('](https://packagist.org/packages/phpstan/phpstan "Packagist package")', row)
        self.assertIn("badge/-%F0%9F%93%A6-181717", row)
        self.assertNotIn("logo=packagist", row)
        self.assertIn('](https://phpstan.org "Official website")', row)
        self.assertLess(row.index('"GitHub source"'), row.index('"Packagist package"'))
        self.assertLess(row.index('"Packagist package"'), row.index('"Official website"'))
        self.assertEqual(row.count("|"), 5)

    def test_editor_choice_row_uses_curated_copy_without_position_medal(self) -> None:
        tool = {
            "slug": "sample",
            "name": "Sample",
            "public_url": "https://example.com",
            "stars": 14042,
            "best_for": "Applications that need a focused analysis workflow",
            "editor_reason": "It detects a distinctive class of defects with project-aware rules.",
        }
        row = editor_row(tool)
        self.assertIn("⭐ 14,042", row)
        self.assertNotIn("🥈", row)
        self.assertIn("Applications that need a focused analysis workflow", row)
        self.assertIn("distinctive class of defects", row)

    def test_editor_choice_section_has_no_medals(self) -> None:
        tools = [
            {
                "slug": f"sample-{position}",
                "name": f"Sample {position}",
                "public_url": "https://example.com",
                "stars": 100 - position,
                "repo_updated_at": "2026-07-01T00:00:00Z",
                "best_for": f"Use case {position}",
                "editor_reason": f"Distinct reason {position}",
            }
            for position in range(1, 5)
        ]
        output = editor_section("Bugs finders", tools, reference_time=self.REFERENCE_TIME)
        self.assertNotIn("🥇", output)
        self.assertNotIn("🥈", output)
        self.assertNotIn("🥉", output)
        self.assertIn("⭐ 96", output)

    def test_complete_catalog_section_ranks_first_three_repositories(self) -> None:
        tools = [
            {
                "name": f"Sample {position}",
                "public_url": "https://example.com",
                "description": f"Description {position}",
                "stars": 100 - position,
                "repo_updated_at": "2026-07-01T00:00:00Z",
            }
            for position in range(1, 5)
        ]
        output = section("Bugs finders", tools, reference_time=self.REFERENCE_TIME)
        self.assertEqual(output.count("🥇"), 1)
        self.assertEqual(output.count("🥈"), 1)
        self.assertEqual(output.count("🥉"), 1)
        self.assertIn("<sub>⭐ 96</sub>", output)

    def test_editor_choice_copy_is_required_for_every_selected_tool(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing-copy"):
            apply_editor_choice_copy(
                [{"slug": "missing-copy", "name": "Missing Copy"}],
                {},
            )

    def test_generated_metadata_fallback_is_rejected_as_editorial_copy(self) -> None:
        with self.assertRaisesRegex(ValueError, "generated metadata fallback"):
            apply_editor_choice_copy(
                [{"slug": "generic-copy", "name": "Generic Copy"}],
                {
                    "generic-copy": {
                        "recommended_for": "Projects that need routine static analysis checks",
                        "why_it_stands_out": "High adoption and recent maintenance: 10,000 stars; updated today.",
                    }
                },
            )

    def test_recommended_for_rejects_repeated_tool_name(self) -> None:
        with self.assertRaisesRegex(ValueError, "repeats the tool name"):
            apply_editor_choice_copy(
                [{"slug": "sample", "name": "Sample Analyzer"}],
                {
                    "sample": {
                        "recommended_for": "Teams adopting Sample Analyzer for application checks",
                        "why_it_stands_out": "Custom data-flow rules identify defects across application boundaries and framework conventions.",
                    }
                },
            )

    def test_current_editor_choice_is_fully_covered_by_curated_copy(self) -> None:
        copy = read_editor_choice_copy()
        missing = {
            slug
            for slug in read_editor_choice_slugs()
            if not copy.get(slug, {}).get("recommended_for") or not copy.get(slug, {}).get("why_it_stands_out")
        }
        self.assertEqual(missing, set())

    def test_current_editor_choice_is_a_small_diverse_current_shortlist(self) -> None:
        tools_by_slug = {tool["slug"]: tool for tool in catalog_lib.load_catalog()}
        selected = read_editor_choice_slugs()
        selected_tools = [tools_by_slug[slug] for slug in selected]
        self.assertGreaterEqual(len(selected_tools), 5)
        self.assertLessEqual(len(selected_tools), 12)
        self.assertTrue(
            all(tool.get("catalog_status") == "current" for tool in selected_tools)
        )
        self.assertGreaterEqual(len({tool.get("category") for tool in selected_tools}), 5)
        self.assertGreaterEqual(
            len({use_case for tool in selected_tools for use_case in tool.get("use_cases", [])}),
            6,
        )

    def test_editor_choice_has_no_forced_per_category_quota(self) -> None:
        tools_by_slug = {tool["slug"]: tool for tool in catalog_lib.load_catalog()}
        selected = read_editor_choice_slugs()
        counts = [
            sum(tools_by_slug[slug].get("category") == category for slug in selected)
            for category in CATEGORY_ORDER
            if category != "SaaS"
        ]
        self.assertIn(0, counts)
        self.assertGreater(max(counts), 1)

    def test_every_current_tool_has_manually_curated_pros_cons_and_sources(self) -> None:
        entries = read_pros_cons()
        current = [
            tool for tool in catalog_lib.load_catalog()
            if not is_dead(tool, self.REFERENCE_TIME)
        ]
        missing = {
            tool["slug"] for tool in current
            if not entries.get(tool["slug"], {}).get("pro")
            or not entries.get(tool["slug"], {}).get("con")
            or not entries.get(tool["slug"], {}).get("sources")
        }
        self.assertEqual(missing, set())

    def test_saas_row_uses_service_specific_fields(self) -> None:
        row = saas_row(
            {
                "name": "Hosted Analyzer",
                "public_url": "https://example.com",
                "best_for": "Hosted PHP security analysis",
                "delivery": "Cloud dashboard and CI integration",
                "website_status": "available",
            }
        )
        self.assertIn("Hosted PHP security analysis", row)
        self.assertIn("Cloud dashboard and CI integration", row)
        self.assertIn('](https://example.com "Official website")', row)
        self.assertNotIn("Stars", row)
        self.assertEqual(row.count("|"), 5)

    def test_saas_row_marks_an_unavailable_site_with_na_badge(self) -> None:
        row = saas_row(
            {
                "name": "Retired Hosted Analyzer",
                "public_url": "https://example.com",
                "best_for": "Hosted PHP security analysis",
                "delivery": "Hosted service",
                "website_status": "unavailable",
            }
        )
        self.assertIn("website-N%2FA-lightgrey", row)
        self.assertNotIn('](https://example.com "Official website")', row)

    def test_resources_do_not_duplicate_a_github_public_url_as_a_website(self) -> None:
        links = resources_value(
            {
                "repository": "https://github.com/example/analyzer",
                "public_url": "https://github.com/legacy/analyzer.git",
                "website_status": "available",
            }
        )
        self.assertIn("GitHub source", links)
        self.assertNotIn("Official website", links)

    def test_diy_section_is_renamed_and_explained(self) -> None:
        output = section(
            "DIY",
            [{"name": "Parser", "description": "A parser", "repo_updated_at": "2026-07-01T00:00:00Z"}],
            reference_time=self.REFERENCE_TIME,
            anchor_prefix="all",
        )
        self.assertIn('<a id="all-libraries-and-building-blocks"></a>', output)
        self.assertIn("### Libraries and building blocks", output)
        self.assertIn("developers building custom analysis rules", output)

    def test_catalog_fields_survive_save_tool(self) -> None:
        tool = {
            "slug": "hosted-analyzer",
            "name": "Hosted Analyzer",
            "category": "SaaS",
            "description": "Hosted analysis.",
            "upstream_description": "Upstream marketing copy.",
            "artifact_type": "hosted-service",
            "use_cases": ["security"],
            "ecosystems": ["generic-php"],
            "catalog_status": "current",
            "installation": "Connect a repository",
            "supported_php": "8.1+",
            "license": "Commercial",
            "pricing": "Paid",
            "reviewed_at": "2026-08-08",
            "best_for": "PHP security analysis",
            "delivery": "Hosted dashboard",
            "editor_reason": "Strong PHP support",
            "title_icon": "assets/tool-icons/service.png",
            "title_icon_label": "Hosted service",
            "latest_release_checked_at": "2026-08-06T00:00:00Z",
            "packagist_checked_at": "2026-08-06T00:00:00Z",
        }
        with tempfile.TemporaryDirectory() as directory, patch.object(catalog_lib, "CATALOG_DIR", Path(directory)):
            save_tool(tool)
            saved = load_yaml(Path(directory) / "hosted-analyzer.yaml")
        self.assertEqual(saved["best_for"], "PHP security analysis")
        self.assertEqual(saved["delivery"], "Hosted dashboard")
        self.assertEqual(saved["upstream_description"], "Upstream marketing copy.")
        self.assertEqual(saved["artifact_type"], "hosted-service")
        self.assertEqual(saved["use_cases"], ["security"])
        self.assertEqual(saved["catalog_status"], "current")
        self.assertEqual(saved["installation"], "Connect a repository")
        self.assertEqual(saved["editor_reason"], "Strong PHP support")
        self.assertEqual(saved["title_icon"], "assets/tool-icons/service.png")
        self.assertEqual(saved["title_icon_label"], "Hosted service")
        self.assertEqual(saved["latest_release_checked_at"], "2026-08-06T00:00:00Z")
        self.assertEqual(saved["packagist_checked_at"], "2026-08-06T00:00:00Z")

    def test_save_tool_rejects_unknown_fields_instead_of_losing_them(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.object(catalog_lib, "CATALOG_DIR", Path(directory)):
            with self.assertRaisesRegex(ValueError, "unknown fields would be lost: typo_field"):
                save_tool({"slug": "sample", "typo_field": "would otherwise disappear"})

    def test_every_category_has_a_unique_reader_facing_title(self) -> None:
        self.assertEqual(set(CATEGORY_TITLES), set(CATEGORY_ORDER))

    def test_every_category_has_a_unique_stable_id(self) -> None:
        self.assertEqual(set(CATEGORY_IDS), set(CATEGORY_ORDER))
        self.assertEqual(len(set(CATEGORY_IDS.values())), len(CATEGORY_IDS))

    def test_hosted_services_are_the_last_catalog_category(self) -> None:
        self.assertEqual(CATEGORY_ORDER[-1], "SaaS")

    def test_memorial_section_orders_projects_by_name(self) -> None:
        output = memorial_section(
            [
                {"name": "Zulu Analyzer", "category": "Misc", "repo_updated_at": "2026-01-01"},
                {"name": "alpha Analyzer", "category": "Misc", "repo_updated_at": "2020-01-01"},
            ]
        )

        self.assertLess(output.index("alpha Analyzer"), output.index("Zulu Analyzer"))
        self.assertNotIn("🕯️ alpha Analyzer", output)
        self.assertNotIn("🕯️ Zulu Analyzer", output)
        self.assertEqual(len(set(CATEGORY_TITLES.values())), len(CATEGORY_TITLES))


if __name__ == "__main__":
    unittest.main()
