from __future__ import annotations

import re
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from catalog_lib import load_catalog  # noqa: E402
from generate_readme import is_dead  # noqa: E402
from generate_site import (  # noqa: E402
    BUILD_MARKER,
    INITIAL_CATALOG_CARD_COUNT,
    SITE_JS_VERSION,
    build_site,
    category_id,
    category_options,
    editor_choice_order,
    editor_more_markup,
    facet_options,
    metadata_freshness,
    normalize_base_path,
    primary_url,
    recommended_tools,
    safe_url,
    tool_card,
)


class DocumentParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.hrefs: list[str] = []
        self.scripts: list[str] = []
        self.script_attributes: list[dict[str, str | None]] = []
        self.h1_count = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("id"):
            self.ids.add(str(values["id"]))
        if tag == "a" and values.get("href"):
            self.hrefs.append(str(values["href"]))
        if tag == "script" and values.get("src"):
            self.scripts.append(str(values["src"]))
            self.script_attributes.append(values)
        if tag == "h1":
            self.h1_count += 1


class ActiveElementCounter(HTMLParser):
    """Approximate the live DOM created when scripting is enabled."""

    def __init__(self) -> None:
        super().__init__()
        self.active_count = 0
        self.source_count = 0
        self.inert_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.source_count += 1
        if self.inert_depth == 0:
            self.active_count += 1
        if tag in {"template", "noscript"}:
            self.inert_depth += 1

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.source_count += 1
        if self.inert_depth == 0:
            self.active_count += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"template", "noscript"}:
            self.inert_depth -= 1


class GenerateSiteTests(unittest.TestCase):
    REFERENCE_TIME = datetime(2026, 8, 6, tzinfo=timezone.utc)

    def build_in_temp(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        directory = tempfile.TemporaryDirectory()
        output = Path(directory.name) / "site"
        build_site(output, reference_time=self.REFERENCE_TIME)
        return directory, output

    def test_build_contains_every_catalog_entry_and_required_assets(self) -> None:
        directory, output = self.build_in_temp()
        self.addCleanup(directory.cleanup)
        index = (output / "index.html").read_text(encoding="utf-8")

        for tool in load_catalog():
            self.assertIn(f'id="tool-{tool["slug"]}"', index)

        for relative_path in (
            "404.html",
            "assets/site.css",
            "assets/site.js",
            "assets/favicon.svg",
            "assets/social-preview.svg",
            ".nojekyll",
            BUILD_MARKER,
        ):
            self.assertTrue((output / relative_path).is_file(), relative_path)
        for export_name in ("catalog.json", "catalog.csv", "build-manifest.json"):
            if (ROOT / "exports" / export_name).is_file():
                self.assertTrue((output / "exports" / export_name).is_file(), export_name)

    def test_home_page_has_valid_internal_anchors_and_one_h1(self) -> None:
        directory, output = self.build_in_temp()
        self.addCleanup(directory.cleanup)
        parser = DocumentParser()
        parser.feed((output / "index.html").read_text(encoding="utf-8"))

        self.assertEqual(parser.h1_count, 1)
        for href in parser.hrefs:
            if href.startswith("#"):
                self.assertIn(href[1:], parser.ids, href)
        self.assertEqual(
            parser.scripts,
            [
                f"assets/site.js?v={SITE_JS_VERSION}",
                "https://static.cloudflareinsights.com/beacon.min.js",
            ],
        )
        self.assertEqual(parser.script_attributes[1].get("type"), "module")
        self.assertEqual(
            parser.script_attributes[1].get("data-cf-beacon"),
            '{"token":"1bc156f61a6c4baab33e1f9a082f72d4"}',
        )

    def test_home_page_surfaces_search_governance_downloads_and_privacy(self) -> None:
        directory, output = self.build_in_temp()
        self.addCleanup(directory.cleanup)
        index = (output / "index.html").read_text(encoding="utf-8")

        self.assertLess(index.index('id="catalog-search"'), index.index('id="editors-choice"'))
        self.assertIn('id="catalog-filter-toggle"', index)
        self.assertIn('name="twitter:card" content="summary_large_image"', index)
        self.assertIn('property="og:image"', index)
        self.assertIn('name="twitter:image"', index)
        self.assertIn("EDITORIAL-POLICY.md", index)
        self.assertIn("DATA-LICENSE.md", index)
        self.assertIn('href="exports/catalog.json" download', index)
        self.assertIn('href="exports/catalog.csv" download', index)
        self.assertIn("Cloudflare Web Analytics</a> for aggregate traffic measurement", index)
        self.assertRegex(index, r'<time datetime="\d{4}-\d{2}-\d{2}">\d{4}-\d{2}-\d{2}</time>')
        installable_count = sum(
            not is_dead(tool, self.REFERENCE_TIME) and tool.get("category") != "SaaS"
            for tool in load_catalog()
        )
        self.assertEqual(index.count("data-compare-toggle"), installable_count)
        self.assertIn('id="compare-tray"', index)
        self.assertIn('id="compare-dialog"', index)
        self.assertIn('id="compare-content"', index)

    def test_client_filters_persist_all_facets_and_support_a_mobile_panel(self) -> None:
        script = (ROOT / "site" / "assets" / "site.js").read_text(encoding="utf-8")
        styles = (ROOT / "site" / "assets" / "site.css").read_text(encoding="utf-8")

        for facet in (
            "category",
            "status",
            "use_case",
            "ecosystem",
            "artifact_type",
            "license",
            "capability",
        ):
            self.assertIn(f'{facet}: form.elements.namedItem("{facet}")', script)
        self.assertIn('params.set("q", search.value.trim())', script)
        self.assertIn("for (const [key, select] of Object.entries(facets))", script)
        self.assertIn('params.set(key, select.value)', script)
        self.assertIn('params.get(key)', script)
        self.assertIn('window.matchMedia("(max-width: 720px)")', script)
        self.assertIn('filterToggle.setAttribute("aria-expanded", String(open))', script)
        self.assertIn('.js .catalog-filter-panel:not(.is-open)', styles)
        self.assertIn('position: sticky;', styles)

    def test_catalog_uses_a_bounded_initial_batch_and_progressive_hydration(self) -> None:
        directory, output = self.build_in_temp()
        self.addCleanup(directory.cleanup)
        index = (output / "index.html").read_text(encoding="utf-8")
        script = (output / "assets" / "site.js").read_text(encoding="utf-8")

        catalog = index[index.index('id="catalog"'):index.index('id="hosted-services"')]
        initial_markup, deferred_markup = catalog.split(
            '<template id="catalog-card-template">', maxsplit=1
        )
        initial_cards = initial_markup.count('<article class="tool-card"')
        deferred_cards = deferred_markup.split("</template>", maxsplit=1)[0].count(
            '<article class="tool-card"'
        )
        expected_total = sum(
            not is_dead(tool, self.REFERENCE_TIME) and tool.get("category") != "SaaS"
            for tool in load_catalog()
        )

        self.assertEqual(initial_cards, INITIAL_CATALOG_CARD_COUNT)
        self.assertEqual(initial_cards + deferred_cards, expected_total)
        self.assertLess(initial_cards, expected_total // 2)
        self.assertIn('id="catalog-show-more"', deferred_markup)
        self.assertIn(f"Show {deferred_cards} more tools", deferred_markup)
        self.assertIn("const hydrateCatalog = () =>", script)
        self.assertIn("deferredCatalog.replaceWith(deferredCatalog.content)", script)
        self.assertIn('showMore.addEventListener("click"', script)
        self.assertIn("hydrateCatalog();\n    applyFilters();", script)
        self.assertIn('sort.value !== "recommended"', script)

        counter = ActiveElementCounter()
        counter.feed(index)
        self.assertLess(counter.active_count, counter.source_count // 2)

    def test_memorial_cards_are_inert_until_opened_or_deep_linked(self) -> None:
        directory, output = self.build_in_temp()
        self.addCleanup(directory.cleanup)
        index = (output / "index.html").read_text(encoding="utf-8")
        script = (output / "assets" / "site.js").read_text(encoding="utf-8")

        memorial = index[index.index('id="in-memoriam"'):index.index("</main>")]
        before_template, deferred_markup = memorial.split(
            '<template id="memorial-card-template">', maxsplit=1
        )
        deferred_cards = deferred_markup.split("</template>", maxsplit=1)[0].count(
            '<article class="tool-card"'
        )
        expected_memorial = sum(is_dead(tool, self.REFERENCE_TIME) for tool in load_catalog())

        self.assertNotIn('<article class="tool-card"', before_template)
        self.assertEqual(deferred_cards, expected_memorial)
        self.assertIn("const hydrateMemorial = () =>", script)
        self.assertIn('memorialDetails.addEventListener("toggle"', script)
        self.assertIn("deferredMemorial.content.getElementById(id)", script)
        self.assertIn("hydrateMemorial();", script)
        self.assertIn("const revealHashTarget = (fragment = window.location.hash)", script)
        self.assertIn('window.addEventListener("hashchange", () => revealHashTarget())', script)
        self.assertIn("if (target.hidden)", script)
        self.assertIn("form.reset();", script)
        self.assertIn('target.scrollIntoView({ block: "start" })', script)

    def test_no_javascript_fallback_links_to_complete_canonical_catalog(self) -> None:
        directory, output = self.build_in_temp()
        self.addCleanup(directory.cleanup)
        index = (output / "index.html").read_text(encoding="utf-8")

        self.assertNotIn("Every catalog entry remains available below", index)
        self.assertIn("The first recommendations remain available below", index)
        self.assertIn(
            'href="https://github.com/ValentinNikolaev/php-analysis-tools-catalog#complete-catalog"',
            index,
        )
        self.assertIn('href="exports/catalog.json">catalog JSON</a>', index)

    def test_client_comparison_enforces_limits_and_builds_an_accessible_table(self) -> None:
        script = (ROOT / "site" / "assets" / "site.js").read_text(encoding="utf-8")

        self.assertIn("selectedForComparison.size >= 4", script)
        self.assertIn('button.setAttribute("aria-pressed", String(isSelected))', script)
        self.assertIn('fieldHeading.scope = "col"', script)
        self.assertIn('heading.scope = "row"', script)
        self.assertIn('["Supported PHP", "supportedPhp"]', script)
        self.assertIn('["Pro", "pro"]', script)
        self.assertIn('["Con", "con"]', script)
        self.assertIn("compareDialog.showModal()", script)

    def test_generated_counts_distinguish_current_and_memorial_tools(self) -> None:
        directory, output = self.build_in_temp()
        self.addCleanup(directory.cleanup)
        index = (output / "index.html").read_text(encoding="utf-8")
        tools = load_catalog()
        current = sum(not is_dead(tool, self.REFERENCE_TIME) for tool in tools)
        memorial = sum(is_dead(tool, self.REFERENCE_TIME) for tool in tools)

        self.assertIn(f"<dt>{current}</dt><dd>current tools</dd>", index)
        self.assertIn(f"View {memorial} preserved projects", index)

    def test_memorial_cards_are_ordered_by_project_name(self) -> None:
        directory, output = self.build_in_temp()
        self.addCleanup(directory.cleanup)
        index = (output / "index.html").read_text(encoding="utf-8")
        memorial_tools = sorted(
            (tool for tool in load_catalog() if is_dead(tool, self.REFERENCE_TIME)),
            key=lambda tool: tool.get("name", "").casefold(),
        )
        positions = [index.index(f'id="tool-{tool["slug"]}"') for tool in memorial_tools]

        self.assertEqual(positions, sorted(positions))

    def test_hosted_services_are_separate_from_the_primary_catalog(self) -> None:
        directory, output = self.build_in_temp()
        self.addCleanup(directory.cleanup)
        index = (output / "index.html").read_text(encoding="utf-8")
        current_tools = [tool for tool in load_catalog() if not is_dead(tool, self.REFERENCE_TIME)]
        catalog_tools = [tool for tool in current_tools if tool.get("category") != "SaaS"]
        hosted_tools = [tool for tool in current_tools if tool.get("category") == "SaaS"]
        catalog_start = index.index('id="catalog"')
        hosted_start = index.index('id="hosted-services"')
        methodology_start = index.index('id="methodology"')
        catalog_markup = index[catalog_start:hosted_start]

        self.assertLess(catalog_start, hosted_start)
        self.assertLess(hosted_start, methodology_start)
        self.assertIn(f"Showing {len(catalog_tools)} tools", catalog_markup)
        self.assertNotIn('<option value="hosted-services">', catalog_markup)
        self.assertNotIn('data-category="hosted-services"', catalog_markup)
        for tool in catalog_tools:
            self.assertLess(index.index(f'id="tool-{tool["slug"]}"'), hosted_start)
        for tool in hosted_tools:
            position = index.index(f'id="tool-{tool["slug"]}"')
            self.assertGreater(position, hosted_start)
            self.assertLess(position, methodology_start)

    def test_default_catalog_order_is_recommended_and_activity_is_separate(self) -> None:
        directory, output = self.build_in_temp()
        self.addCleanup(directory.cleanup)
        index = (output / "index.html").read_text(encoding="utf-8")
        catalog_markup = index[index.index('id="catalog"'):index.index('id="hosted-services"')]
        cards = re.findall(
            r'<article class="tool-card" id="tool-([^"]+)"[^>]+data-rank="(\d+)">',
            catalog_markup,
        )
        current_tools = [
            tool
            for tool in load_catalog()
            if not is_dead(tool, self.REFERENCE_TIME) and tool.get("category") != "SaaS"
        ]
        expected_order = [
            tool["slug"]
            for tool in recommended_tools(current_tools, self.REFERENCE_TIME, editor_choice_order())
        ]

        self.assertTrue(cards)
        self.assertIn('<option value="recommended">Recommended (default)</option>', catalog_markup)
        self.assertIn('<option value="activity">Activity status</option>', catalog_markup)
        self.assertEqual([slug for slug, _ in cards], expected_order)
        self.assertEqual([int(rank) for _, rank in cards], list(range(1, len(cards) + 1)))

    def test_custom_base_path_is_applied_to_not_found_assets_and_home_link(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "site"
            build_site(output, reference_time=self.REFERENCE_TIME, base_path="/preview")
            not_found = (output / "404.html").read_text(encoding="utf-8")

        self.assertIn('href="/preview/assets/site.css?v=5"', not_found)
        self.assertIn('href="/preview/"', not_found)
        self.assertEqual(normalize_base_path("/preview"), "/preview/")
        with self.assertRaisesRegex(ValueError, "absolute URL path"):
            normalize_base_path("https://example.com/preview")

    def test_tool_content_is_escaped_and_unsafe_urls_are_rejected(self) -> None:
        card = tool_card(
            {
                "slug": "unsafe",
                "name": '<script>alert("name")</script>',
                "description": '<img src=x onerror=alert("description")>',
                "public_url": "javascript:alert(1)",
                "category": "Misc",
            },
            self.REFERENCE_TIME,
            1,
        )

        self.assertNotIn("<script>", card)
        self.assertNotIn("<img", card)
        self.assertNotIn("javascript:", card)
        self.assertIn("&lt;script&gt;", card)
        self.assertIsNone(safe_url("javascript:alert(1)"))
        self.assertIsNone(safe_url("https://user:secret@example.com"))
        self.assertIsNone(safe_url("http://127.0.0.1/private"))

    def test_unavailable_website_is_not_published_as_a_primary_or_resource_link(self) -> None:
        tool = {
            "slug": "offline",
            "name": "Offline tool",
            "description": "A tool with an unavailable website",
            "public_url": "https://offline.example.com",
            "website_status": "unavailable",
            "repository": "https://github.com/example/offline",
            "category": "Misc",
        }
        card = tool_card(tool, self.REFERENCE_TIME, 1)

        self.assertEqual(primary_url(tool), "https://github.com/example/offline")
        self.assertNotIn("https://offline.example.com", card)
        self.assertIn("Official website currently unavailable", card)

    def test_primary_link_priority_depends_on_category(self) -> None:
        links = {
            "website_status": "available",
            "website": "https://example.com/tool",
            "repository": "https://github.com/example/tool",
        }
        self.assertEqual(
            primary_url({**links, "category": "SaaS"}),
            "https://example.com/tool",
        )
        self.assertEqual(
            primary_url({**links, "category": "Misc"}),
            "https://github.com/example/tool",
        )

    def test_hosted_tool_without_repository_does_not_show_unknown_badge(self) -> None:
        card = tool_card(
            {
                "slug": "hosted",
                "name": "Hosted tool",
                "description": "A hosted tool without a repository",
                "website": "https://example.com/hosted",
                "category": "SaaS",
            },
            self.REFERENCE_TIME,
            1,
        )

        self.assertNotIn('class="status status--unknown"', card)
        self.assertNotIn('class="tool-meta"', card)
        self.assertEqual(
            primary_url({
                "website": "https://example.com/hosted",
                "category": "SaaS",
            }),
            "https://example.com/hosted",
        )

    def test_tool_title_can_include_a_local_type_icon(self) -> None:
        card = tool_card(
            {
                "slug": "plugin",
                "name": "IDE plugin",
                "description": "An IDE plugin",
                "repository": "https://github.com/example/plugin",
                "category": "Misc",
                "title_icon": "assets/tool-icons/plugin.png",
                "title_icon_label": "IDE plugin",
            },
            self.REFERENCE_TIME,
            1,
        )

        self.assertIn(
            '<img class="tool-title-icon" src="assets/tool-icons/plugin.png" '
            'alt="IDE plugin" title="IDE plugin">',
            card,
        )

    def test_tool_card_formats_latest_release_and_resource_links(self) -> None:
        card = tool_card(
            {
                "slug": "released",
                "name": "Released tool",
                "description": "A tool with a long release name",
                "repository": "https://github.com/example/released",
                "latest_release_tag": "2026.07.17-beta-release-with-a-long-name",
                "latest_release_url": "https://github.com/example/released/releases/tag/2026.07.17-beta",
                "category": "Misc",
            },
            self.REFERENCE_TIME,
            1,
        )

        self.assertIn('<dt><span aria-hidden="true">⭐</span> Stars</dt>', card)
        self.assertIn(
            '<dd title="2026.07.17-beta-release-with-a-long-name">'
            "2026.07.17-beta-release-with-a-long-name</dd>",
            card,
        )
        self.assertIn(">Source<span", card)
        self.assertNotIn(">Release<span", card)

    def test_release_link_remains_available_without_a_source_repository(self) -> None:
        card = tool_card(
            {
                "slug": "release-only",
                "name": "Release-only tool",
                "description": "A tool whose release is its only resource",
                "latest_release_url": "https://example.com/releases/1.0.0",
                "category": "Misc",
            },
            self.REFERENCE_TIME,
            1,
        )

        self.assertIn(">Release<span", card)

    def test_missing_latest_release_uses_a_dash(self) -> None:
        card = tool_card(
            {
                "slug": "unreleased",
                "name": "Unreleased tool",
                "description": "A tool without release data",
                "category": "Misc",
            },
            self.REFERENCE_TIME,
            1,
        )

        self.assertIn('<dt>Latest</dt><dd title="-">-</dd>', card)

    def test_tool_card_labels_commit_and_release_dates_explicitly(self) -> None:
        card = tool_card(
            {
                "slug": "dated",
                "name": "Dated tool",
                "description": "A tool with activity metadata",
                "repository": "https://github.com/example/dated",
                "category": "Misc",
                "repo_updated_at": "2026-08-05T12:00:00Z",
                "latest_release_tag": "v1.2.3",
                "latest_release_published_at": "2026-07-20T12:00:00Z",
            },
            self.REFERENCE_TIME,
            1,
        )

        self.assertIn(
            '<dt>Last commit</dt><dd><time datetime="2026-08-05">2026-08-05</time></dd>',
            card,
        )
        self.assertIn(
            '<dt>Last release</dt><dd><time datetime="2026-07-20">2026-07-20</time></dd>',
            card,
        )

    def test_tool_card_exposes_facets_tags_evidence_and_review_date(self) -> None:
        card = tool_card(
            {
                "slug": "faceted",
                "name": "Faceted tool",
                "description": "Curated description",
                "repository": "https://github.com/example/faceted",
                "category": "Bugs finders",
                "artifact_type": "analyzer",
                "use_cases": ["type-analysis", "security"],
                "ecosystems": ["phpstan"],
                "capabilities": ["ci", "baseline"],
                "license": "MIT",
                "supported_php": ">=8.2",
                "quality_tags": ["static-analysis", "security"],
                "reviewed_at": "2026-08-01",
                "pro": "Focused and fast.",
                "con": "Narrow ecosystem.",
                "pros_cons_sources": ["https://example.com/evidence"],
            },
            self.REFERENCE_TIME,
            1,
            compare_enabled=True,
        )

        self.assertIn('data-category="bug-finders"', card)
        self.assertIn('data-artifact-types="|analyzer|"', card)
        self.assertIn('data-use-cases="|type-analysis|security|"', card)
        self.assertIn('data-ecosystems="|phpstan|"', card)
        self.assertIn('data-capabilities="|ci|baseline|"', card)
        self.assertIn('data-licenses="|mit|"', card)
        self.assertIn('class="tag-list"', card)
        self.assertIn('class="tool-facts"', card)
        self.assertIn('aria-label="Evidence source 1 for Faceted tool"', card)
        self.assertIn('<time datetime="2026-08-01">2026-08-01</time>', card)
        self.assertIn('data-display-name="Faceted tool"', card)
        self.assertIn('data-compare-toggle', card)
        self.assertIn('aria-label="Add Faceted tool to comparison"', card)

    def test_upstream_description_is_an_explicit_last_resort(self) -> None:
        card = tool_card(
            {
                "slug": "upstream-copy",
                "name": "Upstream copy",
                "upstream_description": "Text supplied upstream",
                "category": "Misc",
            },
            self.REFERENCE_TIME,
            1,
        )

        self.assertIn("Text supplied upstream", card)
        self.assertIn("Description supplied by the upstream project.", card)

    def test_tool_cards_do_not_repeat_matching_relevance_and_activity_badges(self) -> None:
        historical_card = tool_card(
            {
                "slug": "historical",
                "name": "Historical tool",
                "catalog_status": "historical",
                "category": "Misc",
            },
            self.REFERENCE_TIME,
            1,
        )
        adjacent_card = tool_card(
            {
                "slug": "adjacent",
                "name": "Adjacent tool",
                "catalog_status": "adjacent",
                "category": "Misc",
                "repo_updated_at": "2026-08-05T00:00:00Z",
            },
            self.REFERENCE_TIME,
            1,
        )

        self.assertNotIn('class="relevance relevance--historical"', historical_card)
        self.assertEqual(historical_card.count(">Historical</span>"), 1)
        self.assertIn('class="status status--historical"', historical_card)
        self.assertIn('class="relevance relevance--adjacent"', adjacent_card)
        self.assertIn('class="status status--active"', adjacent_card)

    def test_recommended_order_prioritizes_relevance_before_activity(self) -> None:
        tools = [
            {
                "slug": "historical-active",
                "name": "Historical active",
                "catalog_status": "historical",
                "repo_updated_at": "2026-08-05T00:00:00Z",
            },
            {
                "slug": "current-quiet",
                "name": "Current quiet",
                "catalog_status": "current",
                "repo_updated_at": "2026-04-01T00:00:00Z",
            },
            {
                "slug": "adjacent-active",
                "name": "Adjacent active",
                "catalog_status": "adjacent",
                "repo_updated_at": "2026-08-05T00:00:00Z",
            },
        ]

        ordered = recommended_tools(tools, self.REFERENCE_TIME, [])

        self.assertEqual(
            [tool["slug"] for tool in ordered],
            ["current-quiet", "adjacent-active", "historical-active"],
        )

    def test_generated_filters_have_url_addressable_facet_values(self) -> None:
        tools = [
            {"use_cases": ["type-analysis", "security"]},
            {"use_cases": ["security"]},
        ]
        options = facet_options(tools, "use_cases")

        self.assertIn('<option value="security">Security (2)</option>', options)
        self.assertIn('<option value="type-analysis">Type analysis (1)</option>', options)

    def test_freshness_reports_coverage_not_only_the_latest_record(self) -> None:
        tools = [
            {"metadata_updated_at": "2026-08-05T00:00:00Z"},
            {"metadata_updated_at": "2026-07-01T00:00:00Z"},
            {},
        ]

        self.assertEqual(metadata_freshness(tools, self.REFERENCE_TIME), (1, 3))

    def test_category_options_are_sorted_by_reader_facing_name(self) -> None:
        tools = [
            {"category": category}
            for category in ("Misc", "DIY", "Bugs finders", "Architecture rules")
        ]
        labels = re.findall(r">([^<]+) \(\d+\)</option>", category_options(tools))

        self.assertEqual(labels, sorted(labels, key=str.casefold))
        self.assertIn('value="bug-finders"', category_options(tools))
        self.assertEqual(category_id("DIY"), "libraries-building-blocks")

    def test_editor_cards_show_stars_and_inline_pros_cons(self) -> None:
        directory, output = self.build_in_temp()
        self.addCleanup(directory.cleanup)
        index = (output / "index.html").read_text(encoding="utf-8")
        editor_markup = index[index.index('id="editors-choice"'):index.index('id="hosted-services"')]
        editor_slugs = set(editor_choice_order())
        editor_tools = [
            tool
            for tool in load_catalog()
            if tool.get("slug") in editor_slugs
            and tool.get("category") != "SaaS"
            and not is_dead(tool, self.REFERENCE_TIME)
        ]
        expected_total = len(editor_tools)
        expected_featured = len({tool.get("category") for tool in editor_tools})
        expected_remaining = expected_total - expected_featured
        featured_markup = editor_markup[
            editor_markup.index('class="editor-grid editor-grid--featured"'):
            editor_markup.index('class="catalog-list-heading"')
        ]
        if expected_remaining:
            featured_markup = featured_markup[:featured_markup.index('class="editor-more"')]
        self.assertEqual(featured_markup.count('class="editor-card"'), expected_featured)
        self.assertEqual(editor_markup.count('class="editor-card"'), expected_total)
        self.assertEqual(editor_markup.count('class="star-count"'), expected_total)
        self.assertEqual(editor_markup.count('class="tradeoffs tradeoffs--inline"'), expected_total)
        if expected_remaining:
            self.assertIn(f"Show {expected_remaining} more editor picks", editor_markup)
        else:
            self.assertNotIn('class="editor-more"', editor_markup)
        self.assertIn('class="tradeoff tradeoff--pro"', editor_markup)
        self.assertIn('class="tradeoff tradeoff--con"', editor_markup)

    def test_empty_editor_overflow_does_not_render_details(self) -> None:
        self.assertEqual(editor_more_markup([], self.REFERENCE_TIME), "")

    def test_current_catalog_uses_accessible_tradeoff_popovers_only(self) -> None:
        directory, output = self.build_in_temp()
        self.addCleanup(directory.cleanup)
        index = (output / "index.html").read_text(encoding="utf-8")
        catalog_and_hosted = index[index.index('id="catalog"'):index.index('id="methodology"')]
        memorial = index[index.index('id="in-memoriam"'):index.index('</main>')]
        current_count = sum(not is_dead(tool, self.REFERENCE_TIME) for tool in load_catalog())

        self.assertEqual(catalog_and_hosted.count('<details class="tradeoffs">'), current_count)
        self.assertIn('<summary>Quick pros &amp; cons<span', catalog_and_hosted)
        self.assertNotIn('<details class="tradeoffs">', memorial)

    def test_generator_only_replaces_its_own_non_empty_output_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "site"
            output.mkdir()
            (output / "user-file.txt").write_text("keep", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Refusing to replace"):
                build_site(output, reference_time=self.REFERENCE_TIME)
            self.assertEqual((output / "user-file.txt").read_text(encoding="utf-8"), "keep")

            (output / BUILD_MARKER).write_text("generated", encoding="utf-8")
            build_site(output, reference_time=self.REFERENCE_TIME)
            self.assertFalse((output / "user-file.txt").exists())
            self.assertTrue((output / "index.html").is_file())


if __name__ == "__main__":
    unittest.main()
