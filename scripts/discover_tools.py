from __future__ import annotations

import argparse
import hashlib
import urllib.error
import urllib.parse
from pathlib import Path
from typing import Any, Iterator

from catalog_lib import (
    ROOT,
    cli_token,
    dump_yaml,
    github_api_repo_url,
    github_repo_key,
    http_json,
    load_catalog,
    load_yaml,
    now_iso,
    positive_int,
    parse_reference_time,
    slugify,
)


# Query hints are only a starting point for editorial review.  They prevent all
# discoveries from being mislabeled as bug finders while keeping the published
# category vocabulary backwards compatible.
SEARCH_QUERIES = [
    ("topic:php topic:static-analysis stars:>20", "Bugs finders"),
    ("topic:php topic:code-quality stars:>20", "Misc"),
    ("PHP static analyzer stars:>20", "Bugs finders"),
    ("PHP security analyzer stars:>10", "Bugs finders"),
    ("PHPStan extension stars:>10", "Bugs finders"),
    ("Psalm plugin static analysis stars:>10", "Bugs finders"),
    ("PHPCS coding standard stars:>10", "Coding standards"),
    ("PHP Rector rules stars:>10", "Fixers"),
    ("PHP code formatter fixer stars:>20", "Fixers"),
    ("PHP architecture dependency analyzer stars:>10", "Architecture rules"),
    ("PHP code metrics complexity stars:>10", "Metrics"),
    ("PHP AST parser analysis stars:>20", "DIY"),
]
PACKAGIST_QUERIES = [
    ("phpstan extension", "Bugs finders"),
    ("static analysis", "Bugs finders"),
    ("phpcs standard", "Coding standards"),
    ("rector rules", "Fixers"),
]
QUERIES = [query for query, _ in SEARCH_QUERIES]
RELEVANT_TOPICS = {
    "php",
    "static-analysis",
    "code-quality",
    "security",
    "phpstan",
    "psalm",
    "phpcs",
    "rector",
    "linter",
}


def candidate_paths_by_repository(root: Path | None = None) -> dict[str, Path]:
    root = root or ROOT
    paths: dict[str, Path] = {}
    for path in (root / "common" / "candidates").glob("*.yaml"):
        repo_key = github_repo_key(load_yaml(path).get("repository"))
        if repo_key:
            paths[repo_key.casefold()] = path
    return paths


def candidate_repository_keys() -> set[str]:
    return set(candidate_paths_by_repository().keys())


def rejected_candidate_identities(root: Path | None = None) -> tuple[set[str], set[str]]:
    root = root or ROOT
    path = root / "common" / "rejected-candidates.yaml"
    if not path.exists():
        return set(), set()
    rejections = load_yaml(path).get("rejections") or []
    slugs = {
        str(rejection["slug"]).casefold()
        for rejection in rejections
        if isinstance(rejection, dict) and rejection.get("slug")
    }
    repositories = {
        repo_key.casefold()
        for rejection in rejections
        if isinstance(rejection, dict)
        and (repo_key := github_repo_key(rejection.get("repository")))
    }
    return slugs, repositories


def choose_output_slug(repo: dict, output_dir: Path, reserved_slugs: set[str]) -> tuple[str, bool]:
    repo_key = str(repo["full_name"])
    digest = hashlib.sha256(repo_key.casefold().encode("utf-8")).hexdigest()[:8]
    choices = [slugify(repo["name"]), slugify(repo_key), f"{slugify(repo_key)}-{digest}"]
    for slug in choices:
        path = output_dir / f"{slug}.yaml"
        if slug in reserved_slugs:
            continue
        if not path.exists():
            reserved_slugs.add(slug)
            return slug, False
        existing_key = github_repo_key(load_yaml(path).get("repository"))
        if existing_key and existing_key.casefold() == repo_key.casefold():
            reserved_slugs.add(slug)
            return slug, True
    raise RuntimeError(f"Unable to allocate a unique catalog slug for {repo_key}")


def infer_category(repo: dict[str, Any], query_hint: str) -> str:
    text = " ".join(
        [
            str(repo.get("name") or ""),
            str(repo.get("description") or ""),
            " ".join(repo.get("topics") or []),
        ]
    ).casefold()
    if any(term in text for term in ("formatter", "fixer", "rector", "refactor", "codemod")):
        return "Fixers"
    if any(term in text for term in ("coding standard", "code style", "phpcs", "sniff")):
        return "Coding standards"
    if any(term in text for term in ("architecture", "dependency rule", "layer boundary", "deptrac")):
        return "Architecture rules"
    if any(term in text for term in ("metric", "complexity", "maintainability index")):
        return "Metrics"
    if any(term in text for term in ("parser", "abstract syntax tree", " ast ", "toolkit", "sdk")):
        return "DIY"
    if any(term in text for term in ("hosted", "saas", "cloud platform")):
        return "SaaS"
    return query_hint


def infer_artifact_type(repo: dict[str, Any], category: str) -> str:
    text = " ".join(
        [str(repo.get("name") or ""), str(repo.get("description") or ""), " ".join(repo.get("topics") or [])]
    ).casefold()
    if category == "SaaS":
        return "hosted-service"
    if category == "Fixers":
        return "fixer"
    if category == "Metrics":
        return "metrics"
    if category == "DIY":
        return "library"
    if any(term in text for term in ("ruleset", "rules", "coding standard", "sniff")):
        return "ruleset"
    if any(term in text for term in ("extension", "plugin")):
        return "extension"
    return "analyzer"


def merge_candidate_metadata(
    existing: dict[str, Any], repo: dict[str, Any], checked_at: str, query: str | None = None
) -> dict[str, Any]:
    updated = dict(existing)
    original_metadata_updated_at = updated.get("metadata_updated_at")
    original_repository = updated.get("repository")
    repo_url = str(repo.get("html_url") or updated.get("repository") or "")
    homepage = str(repo.get("homepage") or "").strip()
    updated["repository"] = repo_url
    updated["stars"] = int(repo.get("stargazers_count") or 0)
    updated["repo_updated_at"] = repo.get("pushed_at") or repo.get("updated_at")
    updated["metadata_updated_at"] = checked_at
    updated["last_discovered_at"] = checked_at
    if homepage and (not updated.get("website") or updated.get("website") == original_repository):
        updated["website"] = homepage
        updated["public_url"] = homepage
    topics = set(updated.get("quality_tags") or [])
    topics.update(set(repo.get("topics") or []) & RELEVANT_TOPICS)
    updated["quality_tags"] = sorted(topics)
    updated.setdefault("review_status", "pending")
    updated.setdefault("review_notes", "Requires editorial relevance, category, and maintenance review.")
    updated.setdefault("discovered_at", original_metadata_updated_at or checked_at)
    updated.setdefault("last_reviewed_at", None)
    if query:
        queries = list(updated.get("discovery_queries") or [])
        if query not in queries:
            queries.append(query)
        updated["discovery_queries"] = queries
    return updated


def new_candidate(repo: dict[str, Any], slug: str, category: str, checked_at: str, query: str) -> dict[str, Any]:
    repository = str(repo["html_url"])
    website = str(repo.get("homepage") or repository)
    return {
        "slug": slug,
        "name": str(repo["name"]),
        "category": category,
        "artifact_type": infer_artifact_type(repo, category),
        "description": repo.get("description") or "Discovered PHP analysis candidate.",
        "website": website,
        "public_url": website,
        "website_status": "unknown",
        "website_status_code": 0,
        "website_checked_at": None,
        "website_error": "",
        "repository": repository,
        "packagist": None,
        "stars": int(repo.get("stargazers_count") or 0),
        "repo_updated_at": repo.get("pushed_at") or repo.get("updated_at"),
        "metadata_updated_at": checked_at,
        "quality_tags": sorted(set(repo.get("topics") or []) & RELEVANT_TOPICS),
        "source": "github-search",
        "notes": "Review category and description before promoting through a normal catalog pull request.",
        "review_status": "pending",
        "review_notes": "Requires editorial relevance, category, and maintenance review.",
        "discovered_at": checked_at,
        "last_reviewed_at": None,
        "last_discovered_at": checked_at,
        "discovery_queries": [query],
    }


def search_repositories(
    query: str, token: str | None, pages: int, per_page: int
) -> Iterator[dict[str, Any]]:
    for page in range(1, pages + 1):
        url = "https://api.github.com/search/repositories?" + urllib.parse.urlencode(
            {
                "q": query,
                "sort": "stars",
                "order": "desc",
                "per_page": per_page,
                "page": page,
            }
        )
        search = http_json(url, token=token)
        items = search.get("items") or []
        if page == 1:
            print(f"  GitHub reported {search.get('total_count', 0)} matches")
        print(f"  page {page}: inspecting {len(items)} repositories")
        yield from items
        if len(items) < per_page:
            break


def search_packagist(query: str, pages: int, per_page: int) -> Iterator[dict[str, Any]]:
    for page in range(1, pages + 1):
        url = "https://packagist.org/search.json?" + urllib.parse.urlencode(
            {"q": query, "page": page, "per_page": per_page}
        )
        search = http_json(url)
        items = search.get("results") or []
        if page == 1:
            print(f"  Packagist reported {search.get('total', 0)} matches")
        print(f"  page {page}: inspecting {len(items)} packages")
        yield from items
        if not search.get("next"):
            break


def refresh_existing_candidates(
    token: str | None,
    checked_at: str,
    *,
    write: bool,
    max_age_hours: int = 24,
) -> tuple[int, int]:
    refreshed = 0
    failed = 0
    reference_time = parse_reference_time(checked_at)
    for repo_key, path in sorted(candidate_paths_by_repository().items()):
        original = load_yaml(path)
        last_checked = original.get("metadata_updated_at")
        if last_checked and max_age_hours:
            try:
                checked = parse_reference_time(str(last_checked))
            except ValueError:
                checked = None
            if checked and (reference_time - checked).total_seconds() < max_age_hours * 3600:
                print(f"Recent candidate: {repo_key} | metadata_updated_at={last_checked}")
                continue
        try:
            repo = http_json(github_api_repo_url(repo_key), token=token)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            failed += 1
            print(f"Candidate refresh skipped: {repo_key} | {exc}")
            continue
        updated = merge_candidate_metadata(original, repo, checked_at)
        if updated != original:
            refreshed += 1
            if write:
                path.write_text(dump_yaml(updated), encoding="utf-8")
            print(f"{'refreshed' if write else 'would refresh'}: {repo_key} | file={path}")
        else:
            print(f"unchanged candidate: {repo_key}")
    return refreshed, failed


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Discover PHP analysis candidates from public GitHub search for human review."
    )
    parser.add_argument("--write", action="store_true", help="Write candidates into common/candidates for review.")
    parser.add_argument("--limit", type=positive_int, default=20, help="Maximum number of new candidates; 0 means none.")
    parser.add_argument("--pages", type=positive_int, default=3, help="Maximum pages to inspect per query.")
    parser.add_argument("--per-page", type=positive_int, default=50, help="GitHub results per page (maximum 100).")
    parser.add_argument(
        "--packagist-limit",
        type=positive_int,
        default=5,
        help="Maximum Packagist-sourced candidates within the overall --limit.",
    )
    parser.add_argument(
        "--skip-packagist-discovery",
        action="store_true",
        help="Discover only through GitHub search.",
    )
    parser.add_argument("--skip-refresh-existing", action="store_true", help="Do not refresh current candidate metadata.")
    parser.add_argument(
        "--refresh-max-age-hours",
        type=positive_int,
        default=24,
        help="Skip candidate repository refreshes newer than this; 0 refreshes every candidate.",
    )
    parser.add_argument(
        "--max-refresh-failures",
        type=positive_int,
        default=5,
        help="Fail when refreshing existing candidates produces more than this many errors.",
    )
    parser.add_argument("--as-of", help="ISO date/timestamp used for deterministic discovery metadata.")
    args = parser.parse_args()
    if args.pages < 1:
        parser.error("--pages must be at least 1")
    if not 1 <= args.per_page <= 100:
        parser.error("--per-page must be between 1 and 100")
    try:
        checked_at = now_iso(args.as_of)
    except ValueError as exc:
        parser.error(str(exc))

    token = cli_token()
    refreshed = failed_refreshes = 0
    if not args.skip_refresh_existing:
        refreshed, failed_refreshes = refresh_existing_candidates(
            token,
            checked_at,
            write=args.write,
            max_age_hours=args.refresh_max_age_hours,
        )

    tools = load_catalog()
    known_catalog = {
        key.casefold() for tool in tools if (key := github_repo_key(tool.get("repository")))
    }
    known_candidates = candidate_repository_keys()
    rejected_slugs, rejected_repositories = rejected_candidate_identities()
    seen_search: set[str] = set()
    output_dir = ROOT / "common" / "candidates"
    if args.write:
        output_dir.mkdir(parents=True, exist_ok=True)
    reserved_slugs = {
        str(tool.get("slug")).casefold() for tool in tools if tool.get("slug")
    } | rejected_slugs
    discovered = 0
    skipped_catalog = 0
    skipped_candidate = 0
    skipped_rejected = 0
    packagist_discovered = 0

    if args.limit and args.packagist_limit and not args.skip_packagist_discovery:
        packagist_target = min(args.limit, args.packagist_limit)
        for query, category_hint in PACKAGIST_QUERIES:
            print(f"Searching Packagist: {query}")
            for package in search_packagist(query, args.pages, args.per_page):
                repo_key_value = github_repo_key(package.get("repository"))
                repo_key = (repo_key_value or "").casefold()
                if not repo_key or repo_key in seen_search:
                    continue
                seen_search.add(repo_key)
                if repo_key in known_catalog:
                    skipped_catalog += 1
                    continue
                if repo_key in known_candidates:
                    skipped_candidate += 1
                    continue
                if repo_key in rejected_repositories:
                    skipped_rejected += 1
                    continue
                try:
                    repo = http_json(github_api_repo_url(repo_key_value), token=token)
                except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
                    failed_refreshes += 1
                    print(f"Packagist candidate skipped: {repo_key_value} | {exc}")
                    continue
                if not repo.get("description") and package.get("description"):
                    repo["description"] = package["description"]
                canonical_repo_key = str(repo.get("full_name") or "").casefold()
                if canonical_repo_key in rejected_repositories:
                    skipped_rejected += 1
                    continue
                category = infer_category(repo, category_hint)
                slug, already_exists = choose_output_slug(repo, output_dir, reserved_slugs)
                if already_exists:
                    skipped_candidate += 1
                    known_candidates.add(repo_key)
                    continue
                candidate = new_candidate(repo, slug, category, checked_at, f"packagist:{query}")
                package_url = package.get("url")
                if package_url:
                    candidate["packagist"] = package_url
                candidate["source"] = "packagist-search"
                if args.write:
                    (output_dir / f"{slug}.yaml").write_text(dump_yaml(candidate), encoding="utf-8")
                print(
                    f"{'wrote' if args.write else 'candidate'}: {candidate['name']} | "
                    f"category={category} | package={package.get('name')} | {candidate['repository']}"
                )
                discovered += 1
                packagist_discovered += 1
                known_candidates.add(repo_key)
                if packagist_discovered >= packagist_target:
                    break
            if packagist_discovered >= packagist_target:
                break

    if discovered < args.limit:
        for query, category_hint in SEARCH_QUERIES:
            print(f"Searching GitHub: {query}")
            for repo in search_repositories(query, token, args.pages, args.per_page):
                repo_key = str(repo.get("full_name") or "").casefold()
                if not repo_key or repo_key in seen_search:
                    continue
                seen_search.add(repo_key)
                if repo_key in known_catalog:
                    skipped_catalog += 1
                    continue
                if repo_key in known_candidates:
                    skipped_candidate += 1
                    continue
                if repo_key in rejected_repositories:
                    skipped_rejected += 1
                    continue
                category = infer_category(repo, category_hint)
                slug, already_exists = choose_output_slug(repo, output_dir, reserved_slugs)
                if already_exists:
                    skipped_candidate += 1
                    known_candidates.add(repo_key)
                    continue
                candidate = new_candidate(repo, slug, category, checked_at, query)
                if args.write:
                    (output_dir / f"{slug}.yaml").write_text(dump_yaml(candidate), encoding="utf-8")
                print(
                    f"{'wrote' if args.write else 'candidate'}: {candidate['name']} | "
                    f"category={category} | {candidate['repository']} | stars={candidate['stars']}"
                )
                discovered += 1
                known_candidates.add(repo_key)
                if discovered >= args.limit:
                    break
            if discovered >= args.limit:
                break

    print(
        "Discovery summary: "
        f"new={discovered}, packagist_new={packagist_discovered}, refreshed={refreshed}, "
        f"provider_failures={failed_refreshes}, "
        f"known_catalog={skipped_catalog}, known_candidates={skipped_candidate}, "
        f"rejected={skipped_rejected}"
    )
    if failed_refreshes > args.max_refresh_failures:
        raise SystemExit(
            f"Discovery providers failed for {failed_refreshes} repositories "
            f"(allowed: {args.max_refresh_failures})"
        )


if __name__ == "__main__":
    main()
