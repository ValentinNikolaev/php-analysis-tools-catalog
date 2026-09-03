from __future__ import annotations

import io
import sys
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import discover_tools


@dataclass
class DiscoveryResult:
    code: int
    stdout: str
    stderr: str
    files: dict[str, str]
    requested_urls: list[str]


class DiscoveryFailureTests(unittest.TestCase):
    def http_error(self, status: int) -> urllib.error.HTTPError:
        error = urllib.error.HTTPError("https://api.github.com/repos/example/missing", status, "failed", {}, None)
        self.addCleanup(error.close)
        return error

    def run_discovery(
        self,
        repositories: dict[str, dict | BaseException],
        *,
        package_repositories: list[str] | None = None,
        arguments: tuple[str, ...] = (),
        existing_candidate: str | None = None,
    ) -> DiscoveryResult:
        packages = [
            {"name": key, "repository": f"https://github.com/{key}", "url": f"https://packagist.org/packages/{key}"}
            for key in (list(repositories) if package_repositories is None else package_repositories)
        ]
        stdout = io.StringIO()
        stderr = io.StringIO()
        requested_urls: list[str] = []

        def inspect_repository(url: str, **kwargs: object) -> dict:
            requested_urls.append(url)
            key = url.removeprefix("https://api.github.com/repos/")
            result = repositories[key]
            if isinstance(result, BaseException):
                raise result
            return dict(result)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "common").mkdir()
            candidate_dir = root / "common" / "candidates"
            if existing_candidate is not None:
                candidate_dir.mkdir()
                (candidate_dir / "existing.yaml").write_text(existing_candidate, encoding="utf-8")
            with (
                patch.object(discover_tools, "ROOT", root),
                patch.object(discover_tools, "PACKAGIST_QUERIES", [("static analysis", "Bugs finders")]),
                patch.object(discover_tools, "SEARCH_QUERIES", [("PHP analyzer", "Bugs finders")]),
                patch("discover_tools.load_catalog", return_value=[]),
                patch("discover_tools.cli_token", return_value=None),
                patch("discover_tools.search_packagist", return_value=iter(packages)),
                patch("discover_tools.search_repositories", return_value=iter([])),
                patch("discover_tools.http_json", side_effect=inspect_repository),
                redirect_stdout(stdout),
                redirect_stderr(stderr),
            ):
                args = ["--limit", "20", "--packagist-limit", "20", "--as-of", "2026-09-03"]
                if existing_candidate is None:
                    args.append("--skip-refresh-existing")
                else:
                    args.extend(["--refresh-max-age-hours", "0"])
                with patch.object(sys, "argv", ["discover_tools.py", *args, *arguments]):
                    try:
                        code = discover_tools.main() or 0
                    except SystemExit as exc:
                        if exc.code is None:
                            code = 0
                        elif isinstance(exc.code, int):
                            code = exc.code
                        else:
                            code = 1
                            print(exc.code, file=sys.stderr)
            files = {path.name: path.read_text(encoding="utf-8") for path in candidate_dir.glob("*.yaml")}
        return DiscoveryResult(code, stdout.getvalue(), stderr.getvalue(), files, requested_urls)

    def test_unavailable_packagist_repositories_do_not_consume_failure_budget(self) -> None:
        for write in (False, True):
            for budget in ((), ("--max-refresh-failures", "0")):
                with self.subTest(write=write, budget=budget):
                    repositories = {f"example/missing-{index}": self.http_error(404 if index % 2 else 410) for index in range(6)}
                    repositories["example/available"] = {
                        "name": "available",
                        "full_name": "example/available",
                        "html_url": "https://github.com/example/available",
                        "description": "PHP static analysis candidate",
                        "stargazers_count": 42,
                        "topics": ["php", "static-analysis"],
                    }
                    result = self.run_discovery(repositories, arguments=(*budget, *(("--write",) if write else ())))

                    self.assertEqual(result.code, 0, result.stderr)
                    self.assertIn("new=1, packagist_new=1", result.stdout)
                    self.assertIn("provider_failures=0", result.stdout)
                    self.assertIn("unavailable_repositories=6", result.stdout)
                    self.assertNotIn("partial", result.stdout)
                    output = result.stdout + result.stderr
                    self.assertIn("unavailable", output.lower())
                    for index in range(6):
                        self.assertIn(f"example/missing-{index}", output)
                    self.assertEqual(set(result.files), {"available.yaml"} if write else set())
                    if write:
                        self.assertIn("https://github.com/example/available", result.files["available.yaml"])

    def test_all_unavailable_repository_results_are_a_successful_empty_search(self) -> None:
        result = self.run_discovery(
            {"example/missing": self.http_error(404), "example/gone": self.http_error(410)},
            arguments=("--max-refresh-failures", "0", "--write"),
        )
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("new=0, packagist_new=0", result.stdout)
        self.assertIn("provider_failures=0", result.stdout)
        self.assertIn("unavailable_repositories=2", result.stdout)
        self.assertEqual(result.files, {})

    def test_unavailable_repository_is_only_counted_once_for_duplicate_packages(self) -> None:
        result = self.run_discovery(
            {"example/missing": self.http_error(404)},
            package_repositories=["example/missing", "example/missing"],
            arguments=("--max-refresh-failures", "0"),
        )
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("unavailable_repositories=1", result.stdout)
        self.assertEqual(len(result.requested_urls), 1)

    def test_other_repository_errors_still_consume_failure_budget(self) -> None:
        errors = [*(self.http_error(status) for status in (401, 403, 429, 500, 503)), urllib.error.URLError("offline"), TimeoutError("timed out")]
        for error in errors:
            with self.subTest(error=str(error)):
                result = self.run_discovery(
                    {"example/failed": error},
                    arguments=("--max-refresh-failures", "0"),
                )
                self.assertNotEqual(result.code, 0, result.stderr)
                self.assertIn("provider_failures=1", result.stdout)
                self.assertIn("unavailable_repositories=0", result.stdout)
                self.assertEqual(result.files, {})

    def test_packagist_search_404_is_not_swallowed_as_an_unavailable_repository(self) -> None:
        error = self.http_error(404)
        with patch("discover_tools.http_json", side_effect=error):
            with self.assertRaises(urllib.error.HTTPError) as raised:
                list(discover_tools.search_packagist("static analysis", pages=1, per_page=20))
        self.assertIs(raised.exception, error)

    def test_existing_candidate_404_still_fails_and_preserves_metadata(self) -> None:
        existing = (
            "slug: existing\n"
            "repository: https://github.com/example/existing\n"
            "metadata_updated_at: 2026-08-01T00:00:00Z\n"
            "review_status: needs-info\n"
            "review_notes: Keep this editorial decision.\n"
        )
        result = self.run_discovery(
            {"example/existing": self.http_error(404)},
            package_repositories=[],
            existing_candidate=existing,
            arguments=("--max-refresh-failures", "0", "--write"),
        )
        self.assertNotEqual(result.code, 0, result.stderr)
        self.assertIn("provider_failures=1", result.stdout)
        self.assertIn("unavailable_repositories=0", result.stdout)
        self.assertEqual(result.files, {"existing.yaml": existing})


if __name__ == "__main__":
    unittest.main()
