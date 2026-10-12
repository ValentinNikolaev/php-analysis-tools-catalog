from __future__ import annotations

import html
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from catalog_lib import load_catalog, read_pros_cons
from generate_readme import is_dead
from generate_site import (
    SITE_URL, build_site, category_id, checked_slug, guide_content, load_guides,
    render_page, search_verification_tags, validate_output,
)


class CrawlDocument(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.inert = 0
        self.links: list[str] = []
        self.canonical = ""
        self.metadata: dict[str, str] = {}
        self.headings: list[str] = []
        self.h1_count = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag in {"template", "noscript", "script"}:
            self.inert += 1
        if self.inert:
            return
        if tag == "a" and values.get("href"):
            self.links.append(str(values["href"]))
        if tag == "link" and values.get("rel") == "canonical":
            self.canonical = str(values["href"])
        if tag == "meta":
            self.metadata[str(values.get("name") or values.get("property"))] = str(values.get("content") or "")
        if tag in {"h1", "h2", "h3"}:
            self.headings.append(tag)
        if tag == "h1":
            self.h1_count += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"template", "noscript", "script"}:
            self.inert -= 1


class SiteIndexingTests(unittest.TestCase):
    REFERENCE_TIME = datetime(2026, 10, 13, tzinfo=timezone.utc)

    @classmethod
    def setUpClass(cls) -> None:
        cls.directory = tempfile.TemporaryDirectory()
        cls.output = Path(cls.directory.name) / "site"
        build_site(cls.output, reference_time=cls.REFERENCE_TIME)
        cls.current = [tool for tool in load_catalog() if not is_dead(tool, cls.REFERENCE_TIME)]

    @classmethod
    def tearDownClass(cls) -> None:
        cls.directory.cleanup()

    def document(self, route: str) -> CrawlDocument:
        document = CrawlDocument()
        document.feed((self.output / route / "index.html").read_text(encoding="utf-8"))
        return document

    def test_every_current_tool_is_reachable_by_following_plain_html_links(self) -> None:
        pending = [SITE_URL]
        visited: set[str] = set()
        while pending:
            url = pending.pop()
            if url in visited:
                continue
            route = url.removeprefix(SITE_URL)
            document = self.document(route)
            visited.add(url)
            for href in document.links:
                parsed = urlparse(urljoin(url, href))
                target = parsed._replace(query="", fragment="").geturl()
                if target.startswith(SITE_URL) and target.endswith("/") and target not in visited:
                    pending.append(target)
        expected = {SITE_URL}
        expected.update(SITE_URL + str(path.parent.relative_to(self.output)).replace("\\", "/") + "/"
                        for path in self.output.rglob("index.html") if path.parent != self.output)
        self.assertEqual(visited, expected)
        for tool in self.current:
            self.assertIn(SITE_URL + f'tools/{tool["slug"]}/', visited)

    def test_categories_contain_all_their_tools_without_templates_or_scripts(self) -> None:
        for category in {tool["category"] for tool in self.current}:
            route = f"categories/{category_id(category)}/"
            document = self.document(route)
            markup = (self.output / route / "index.html").read_text(encoding="utf-8")
            self.assertNotIn("<template", markup)
            for tool in self.current:
                if tool["category"] == category:
                    self.assertIn(f'../../tools/{tool["slug"]}/', document.links)
                    self.assertIn(f'id="tool-{tool["slug"]}"', markup)

    def test_pages_have_unique_canonicals_descriptions_and_one_primary_heading(self) -> None:
        canonicals = set()
        for path in self.output.rglob("index.html"):
            route = "" if path.parent == self.output else path.parent.relative_to(self.output).as_posix() + "/"
            document = self.document(route)
            self.assertEqual(document.h1_count, 1, route)
            self.assertEqual(document.canonical, SITE_URL + route)
            self.assertEqual(document.metadata["og:url"], document.canonical)
            self.assertTrue(document.metadata["description"], route)
            self.assertNotIn("noindex", document.metadata.get("robots", ""))
            self.assertNotIn(document.canonical, canonicals)
            canonicals.add(document.canonical)
            self.assertEqual(document.metadata["og:image"], SITE_URL + "assets/social-preview.png")
            self.assertFalse(any(left == "h1" and right == "h3"
                                 for left, right in zip(document.headings, document.headings[1:])), route)

    def test_sitemap_contains_exactly_the_generated_public_pages(self) -> None:
        tree = ElementTree.parse(self.output / "sitemap.xml")
        locations = [element.text for element in tree.findall("{*}url/{*}loc")]
        expected = {SITE_URL}
        expected.update(SITE_URL + path.parent.relative_to(self.output).as_posix() + "/"
                        for path in self.output.rglob("index.html") if path.parent != self.output)
        self.assertEqual(set(locations), expected)
        self.assertEqual(len(locations), len(expected))
        self.assertFalse(any("#" in url or "?" in url or "404" in url for url in locations))
        self.assertFalse(tree.findall("{*}url/{*}lastmod"))

    def test_tool_pages_use_curated_tradeoffs_and_catalog_installation(self) -> None:
        pros_cons = read_pros_cons()
        for tool in self.current:
            markup = (self.output / "tools" / tool["slug"] / "index.html").read_text(encoding="utf-8")
            text = html.unescape(markup)
            self.assertIn(pros_cons[tool["slug"]]["pro"], text)
            self.assertIn(pros_cons[tool["slug"]]["con"], text)
            if tool.get("installation"):
                self.assertIn(tool["installation"], text)
        memorial = [tool for tool in load_catalog() if is_dead(tool, self.REFERENCE_TIME)]
        for tool in memorial:
            self.assertFalse((self.output / "tools" / tool["slug"]).exists())

    def test_guides_link_to_current_records_and_official_evidence(self) -> None:
        for guide in load_guides():
            document = self.document(f'guides/{guide["slug"]}/')
            for section in guide["sections"]:
                for slug in section["tools"]:
                    self.assertIn(f"../../tools/{slug}/", document.links)
                for source in section.get("sources", []):
                    self.assertIn(source, document.links)

    def test_stale_guide_tool_reference_fails_the_build(self) -> None:
        guide = {"slug": "invalid", "sections": [{"tools": ["retired-tool"]}]}
        with self.assertRaisesRegex(ValueError, "unavailable tool"):
            guide_content(guide, {})

    def test_invalid_route_cannot_write_outside_the_build(self) -> None:
        for slug in ("../escape", "/absolute", "a/b", "UPPER", "", "a?b"):
            with self.subTest(slug=slug), self.assertRaisesRegex(ValueError, "route slug"):
                checked_slug(slug)

    def test_verification_tags_are_optional_validated_and_escaped(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "verification.json"
            path.write_text(json.dumps({"google-site-verification": "", "msvalidate.01": ""}), encoding="utf-8")
            self.assertEqual(search_verification_tags(path), "")
            path.write_text(json.dumps({"google-site-verification": 'g"<token>', "msvalidate.01": "bing-token"}), encoding="utf-8")
            tags = search_verification_tags(path)
            self.assertIn('content="g&quot;&lt;token&gt;"', tags)
            self.assertIn('name="msvalidate.01" content="bing-token"', tags)
            page = render_page("tools/example/", "Example", "Example description", "<h2>Details</h2>",
                               kicker="Tool", site_url=SITE_URL, verification_tags=tags)
            self.assertIn(tags, page)
            path.write_text(json.dumps({"unknown": "value"}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Unsupported"):
                search_verification_tags(path)
            path.write_text(json.dumps({"google-site-verification": 123}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "strings"):
                search_verification_tags(path)

    def test_custom_base_path_matches_canonicals_and_sitemap(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "site"
            build_site(output, reference_time=self.REFERENCE_TIME, base_path="/preview")
            expected_url = "https://valentinnikolaev.github.io/preview/"
            tree = ElementTree.parse(output / "sitemap.xml")
            for element in tree.findall("{*}url/{*}loc"):
                self.assertTrue(element.text.startswith(expected_url))
            page = (output / "tools/php-stan/index.html").read_text(encoding="utf-8")
            self.assertIn(f'href="{expected_url}tools/php-stan/"', page)
            self.assertIn('src="../../assets/theme.js?v=1"', page)

    def test_build_validation_detects_a_broken_nested_link(self) -> None:
        path = self.output / "tools/php-stan/index.html"
        original = path.read_text(encoding="utf-8")
        try:
            path.write_text(original.replace("</main>", '<a href="../../missing/">Missing</a></main>'), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Broken local link"):
                validate_output(self.output)
        finally:
            path.write_text(original, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
