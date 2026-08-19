from __future__ import annotations

import argparse
import html
import ipaddress
import shutil
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from catalog_lib import (
    CATEGORY_IDS,
    CATEGORY_ORDER,
    EDITOR_CHOICE_FILE,
    ROOT,
    category_rank,
    load_catalog,
    load_yaml,
    reference_time as resolve_reference_time,
    read_editor_choice_copy,
    read_editor_choice_slugs,
    read_pros_cons,
)
from generate_readme import (
    apply_editor_choice_copy,
    category_title,
    is_dead,
    lifecycle,
    parse_date,
    stars_value,
)


SITE_SOURCE = ROOT / "site"
EXPORT_SOURCE = ROOT / "exports"
EXPORT_FILENAMES = ("catalog.json", "catalog.csv", "build-manifest.json")
INITIAL_CATALOG_CARD_COUNT = 12
SITE_JS_VERSION = 4
DEFAULT_OUTPUT = ROOT / "site-dist"
BUILD_MARKER = ".php-analysis-tools-site-build"
REPOSITORY_URL = "https://github.com/ValentinNikolaev/php-analysis-tools-catalog"
SITE_URL = "https://valentinnikolaev.github.io/php-analysis-tools-catalog/"
DEFAULT_BASE_PATH = "/php-analysis-tools-catalog/"
TOOL_PROPOSAL_URL = f"{REPOSITORY_URL}/issues/new?template=tool-proposal.yml"
CORRECTION_URL = f"{REPOSITORY_URL}/issues/new?template=catalog-correction.yml"


def escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def safe_url(value: object) -> str | None:
    if not value:
        return None
    url = str(value).strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
        return None
    hostname = parsed.hostname
    if not hostname or hostname.casefold() == "localhost":
        return None
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        if not address.is_global:
            return None
    if any(part.casefold() == "localhost" for part in hostname.split(".")):
        return None
    return url


def primary_url(tool: dict) -> str:
    website_available = tool.get("website_status") != "unavailable"
    if tool.get("category") == "SaaS":
        keys = (
            ("public_url", "website", "repository", "packagist")
            if website_available
            else ("repository", "packagist")
        )
    else:
        keys = (
            ("repository", "public_url", "website", "packagist")
            if website_available
            else ("repository", "packagist")
        )
    for key in keys:
        url = safe_url(tool.get(key))
        if url:
            return url
    return REPOSITORY_URL


def resource_links(tool: dict, name: str) -> str:
    links: list[tuple[str, str]] = []
    repository = safe_url(tool.get("repository"))
    package = safe_url(tool.get("packagist"))
    website = (
        safe_url(tool.get("public_url") or tool.get("website"))
        if tool.get("website_status") != "unavailable"
        else None
    )
    release = safe_url(tool.get("latest_release_url"))

    if repository:
        links.append(("Source", repository))
    if package:
        links.append(("Package", package))
    if website and website.rstrip("/") != (repository or "").rstrip("/"):
        links.append(("Website", website))
    if release and not repository:
        links.append(("Release", release))

    if not links:
        return '<span class="resource-empty">No public link</span>'

    return "".join(
        f'<a class="resource-link" href="{escape(url)}" '
        f'aria-label="{escape(label)} for {escape(name)}">'
        f'{escape(label)}<span aria-hidden="true"> ↗</span></a>'
        for label, url in links
    )


def latest_version(tool: dict) -> str:
    value = tool.get("latest_release_tag") or tool.get("latest_version") or tool.get("latest_release_name")
    return str(value or "-")


def normalized_iso_date(value: object) -> str:
    if not value:
        return ""
    return str(value).replace("Z", "+00:00")


def date_markup(value: str | None, fallback: str = "Unknown") -> str:
    parsed = parse_date(value)
    if not parsed:
        return escape(fallback)
    value_iso = parsed.date().isoformat()
    return f'<time datetime="{value_iso}">{value_iso}</time>'


def string_values(tool: dict, *keys: str) -> list[str]:
    """Return normalized, de-duplicated values from optional scalar/list fields."""
    values: list[str] = []
    for key in keys:
        raw = tool.get(key)
        items = raw if isinstance(raw, (list, tuple, set)) else [raw]
        for item in items:
            value = str(item or "").strip()
            if value and value not in values:
                values.append(value)
    return values


def facet_label(value: str) -> str:
    aliases = {
        "api-compatibility": "API compatibility",
        "ci": "CI",
        "ide": "IDE",
        "php": "PHP",
        "phpcs": "PHPCS",
        "phpstan": "PHPStan",
        "sql-analysis": "SQL analysis",
        "type-analysis": "Type analysis",
    }
    normalized = value.strip().casefold()
    return aliases.get(normalized, value.replace("_", " ").replace("-", " ").strip().title())


def category_id(category: str) -> str:
    return CATEGORY_IDS.get(category, category.casefold().replace(" ", "-"))


def artifact_types(tool: dict) -> list[str]:
    return string_values(tool, "artifact_type", "tool_type")


def encoded_facet(values: list[str]) -> str:
    return "|" + "|".join(value.casefold() for value in values) + "|" if values else ""


def facet_options(tools: list[dict], *keys: str) -> str:
    counts: dict[str, int] = {}
    display_values: dict[str, str] = {}
    for tool in tools:
        values = artifact_types(tool) if keys == ("artifact_type",) else string_values(tool, *keys)
        for value in values:
            normalized = value.casefold()
            counts[normalized] = counts.get(normalized, 0) + 1
            display_values.setdefault(normalized, value)
    return "\n".join(
        f'<option value="{escape(value)}">{escape(facet_label(display_values[value]))} ({counts[value]})</option>'
        for value in sorted(counts, key=lambda item: facet_label(display_values[item]).casefold())
    )


def quality_tags(tool: dict, name: str) -> str:
    tags = string_values(tool, "quality_tags")
    if not tags:
        return ""
    items = "".join(f"<li>{escape(facet_label(tag))}</li>" for tag in tags)
    return f'<ul class="tag-list" aria-label="Catalog tags for {escape(name)}">{items}</ul>'


def comparable_facts(tool: dict, name: str) -> str:
    fields = (
        ("Type", artifact_types(tool), True),
        ("PHP", string_values(tool, "supported_php"), False),
        ("License", string_values(tool, "license"), False),
        ("Delivery", string_values(tool, "delivery"), False),
        ("Pricing", string_values(tool, "pricing"), False),
        ("Install", string_values(tool, "installation", "install"), False),
    )
    facts = [
        f'<div><dt>{escape(label)}</dt><dd>{escape(", ".join(facet_label(value) if normalize else value for value in values))}</dd></div>'
        for label, values, normalize in fields
        if values
    ]
    if not facts:
        return ""
    return f'<dl class="tool-facts" aria-label="Comparable facts for {escape(name)}">{"".join(facts)}</dl>'


def review_note(tool: dict) -> str:
    reviewed_at = str(tool.get("reviewed_at") or "").strip()
    if not reviewed_at:
        return ""
    return f'<p class="review-note">Editorially reviewed {date_markup(reviewed_at)}</p>'


def relevance_badge(tool: dict, activity_status: str = "") -> str:
    status = str(tool.get("catalog_status") or "current").strip().casefold()
    if status == "current" or facet_label(status).casefold() == activity_status.strip().casefold():
        return ""
    return f'<span class="relevance relevance--{escape(status)}">{escape(facet_label(status))}</span>'


def relevance_rank(tool: dict) -> int:
    status = str(tool.get("catalog_status") or "current").strip().casefold()
    tags = {tag.casefold() for tag in string_values(tool, "quality_tags")}
    if "historical-analysis-only" in tags:
        return 3
    return {
        "current": 0,
        "recommended": 0,
        "adjacent": 1,
        "historical": 3,
        "legacy": 3,
        "superseded": 3,
        "retired": 3,
    }.get(status, 2)


def editor_choice_order() -> list[str]:
    if not EDITOR_CHOICE_FILE.exists():
        return []
    data = load_yaml(EDITOR_CHOICE_FILE)
    return [str(slug) for slug in data.get("slugs") or [] if str(slug).strip()]


def recommended_tools(
    tools: list[dict], reference_time: datetime, editor_order: list[str]
) -> list[dict]:
    order = {slug: rank for rank, slug in enumerate(editor_order)}

    def explicit_rank(tool: dict) -> int:
        value = tool.get("recommendation_rank") or tool.get("editorial_rank")
        try:
            return int(value)
        except (TypeError, ValueError):
            return order.get(str(tool.get("slug") or ""), len(order) + 10_000)

    return sorted(
        tools,
        key=lambda tool: (
            relevance_rank(tool),
            0 if str(tool.get("slug") or "") in order else 1,
            explicit_rank(tool),
            lifecycle(tool, reference_time)[0],
            -stars_value(tool),
            str(tool.get("name") or "").casefold(),
        ),
    )


def title_icon(tool: dict) -> str:
    icon = str(tool.get("title_icon") or "").strip()
    label = str(tool.get("title_icon_label") or "Tool type").strip()
    if not icon.startswith("assets/tool-icons/") or "/../" in f"/{icon}/":
        return ""
    return (
        f'<img class="tool-title-icon" src="{escape(icon)}" '
        f'alt="{escape(label)}" title="{escape(label)}">'
    )


def status_badge(tool: dict, status: str) -> str:
    if tool.get("category") == "SaaS" and status == "Unknown":
        return ""
    return f'<span class="status status--{escape(status.casefold())}">{escape(status)}</span>'


def apply_pros_cons(tools: list[dict], entries: dict[str, dict]) -> list[dict]:
    enriched: list[dict] = []
    missing: list[str] = []
    for tool in tools:
        slug = str(tool.get("slug") or "")
        entry = entries.get(slug) or {}
        pro = str(entry.get("pro") or "").strip()
        con = str(entry.get("con") or "").strip()
        sources = [url for value in entry.get("sources") or [] if (url := safe_url(value))]
        if not pro or not con or not sources:
            missing.append(slug or str(tool.get("name") or "unnamed-tool"))
            continue
        enriched.append({**tool, "pro": pro, "con": con, "pros_cons_sources": sources})
    if missing:
        raise ValueError("Missing manually curated pros, cons, or sources for: " + ", ".join(sorted(missing)))
    return enriched


def evidence_links(tool: dict, name: str) -> str:
    sources = [url for value in tool.get("pros_cons_sources") or [] if (url := safe_url(value))]
    if not sources:
        return ""
    links = "".join(
        f'<a href="{escape(url)}" aria-label="Evidence source {index} for {escape(name)}">'
        f'Source {index}<span aria-hidden="true"> ↗</span></a>'
        for index, url in enumerate(sources, start=1)
    )
    return f'<p class="evidence-links"><span>Evidence:</span> {links}</p>'


def tradeoffs(tool: dict, name: str, *, inline: bool = False) -> str:
    pro = str(tool.get("pro") or "").strip()
    con = str(tool.get("con") or "").strip()
    if not pro or not con:
        return ""
    content = f"""
  <p class="tradeoff tradeoff--pro"><strong>Pro</strong><span>{escape(pro)}</span></p>
  <p class="tradeoff tradeoff--con"><strong>Con</strong><span>{escape(con)}</span></p>
  {evidence_links(tool, name)}""".strip()
    if inline:
        return f'<div class="tradeoffs tradeoffs--inline" aria-label="Pros and cons for {escape(name)}">{content}</div>'
    return f"""
<details class="tradeoffs">
  <summary>Quick pros &amp; cons<span class="visually-hidden"> for {escape(name)}</span></summary>
  <div class="tradeoffs__popover">{content}</div>
</details>""".strip()


def tool_card(
    tool: dict, reference_time: datetime, rank: int, *, compare_enabled: bool = False
) -> str:
    activity_rank, status = lifecycle(tool, reference_time)
    name = str(tool.get("name") or "Unnamed tool")
    slug = str(tool.get("slug") or "tool")
    category = str(tool.get("category") or "Misc")
    curated_description = tool.get("best_for") or tool.get("description")
    description = str(curated_description or tool.get("upstream_description") or "No description available.")
    upstream_description_only = not curated_description and bool(tool.get("upstream_description"))
    stars = stars_value(tool)
    updated = date_markup(tool.get("repo_updated_at"))
    released = date_markup(
        tool.get("latest_release_published_at") or tool.get("latest_version_released_at")
    )
    updated_iso = normalized_iso_date(tool.get("repo_updated_at"))
    tags = string_values(tool, "quality_tags")
    use_cases = string_values(tool, "use_cases")
    ecosystems = string_values(tool, "ecosystems")
    types = artifact_types(tool)
    licenses = string_values(tool, "license")
    capabilities = string_values(tool, "capabilities")
    supported_php = string_values(tool, "supported_php")
    catalog_status = str(tool.get("catalog_status") or "current").strip().casefold()
    search_text = " ".join(
        (
            name,
            category_title(category),
            description,
            " ".join(tags + use_cases + ecosystems + types + licenses + capabilities),
            str(tool.get("pro") or ""),
            str(tool.get("con") or ""),
            str(tool.get("delivery") or ""),
            str(tool.get("installation") or ""),
            str(tool.get("supported_php") or ""),
        )
    ).casefold()
    version = latest_version(tool)
    website_unavailable = tool.get("website_status") == "unavailable"
    show_repository_metadata = category != "SaaS" or safe_url(tool.get("repository")) is not None
    metadata = (
        f"""
  <dl class="tool-meta">
    <div><dt><span aria-hidden="true">⭐</span> Stars</dt><dd>{stars:,}</dd></div>
    <div><dt>Latest</dt><dd title="{escape(version)}">{escape(version)}</dd></div>
    <div><dt>Last commit</dt><dd>{updated}</dd></div>
    <div><dt>Last release</dt><dd>{released}</dd></div>
  </dl>"""
        if show_repository_metadata
        else ""
    )
    compare_button = (
        f'<button class="compare-toggle" type="button" data-compare-toggle '
        f'aria-pressed="false" aria-label="Add {escape(name)} to comparison">Compare</button>'
        if compare_enabled
        else ""
    )

    return f"""
<article class="tool-card" id="tool-{escape(slug)}"
  data-display-name="{escape(name)}"
  data-primary-url="{escape(primary_url(tool))}"
  data-description-text="{escape(description)}"
  data-name="{escape(name.casefold())}"
  data-search="{escape(search_text)}"
  data-category="{escape(category_id(category))}"
  data-status="{escape(status)}"
  data-catalog-status="{escape(catalog_status)}"
  data-artifact-types="{escape(encoded_facet(types))}"
  data-use-cases="{escape(encoded_facet(use_cases))}"
  data-ecosystems="{escape(encoded_facet(ecosystems))}"
  data-licenses="{escape(encoded_facet(licenses))}"
  data-capabilities="{escape(encoded_facet(capabilities))}"
  data-artifact-labels="{escape(', '.join(facet_label(value) for value in types))}"
  data-use-case-labels="{escape(', '.join(facet_label(value) for value in use_cases))}"
  data-ecosystem-labels="{escape(', '.join(facet_label(value) for value in ecosystems))}"
  data-license-labels="{escape(', '.join(licenses))}"
  data-supported-php="{escape(', '.join(supported_php))}"
  data-pro="{escape(str(tool.get('pro') or ''))}"
  data-con="{escape(str(tool.get('con') or ''))}"
  data-stars="{stars}"
  data-updated="{escape(updated_iso)}"
  data-activity-rank="{activity_rank}"
  data-rank="{rank}">
  <div class="tool-card__heading">
    <div>
      <span class="eyebrow">{escape(category_title(category))}</span>
      <h3><a href="{escape(primary_url(tool))}" aria-label="Open the {escape(name)} project page">{escape(name)}</a>{title_icon(tool)}</h3>
    </div>
    <div class="badge-group">{relevance_badge(tool, status)}{status_badge(tool, status)}</div>
  </div>
  <p class="tool-description">{escape(description)}</p>
  {f'<p class="description-source">Description supplied by the upstream project.</p>' if upstream_description_only else ''}
  {quality_tags(tool, name)}
  {comparable_facts(tool, name)}
  {metadata}
  {tradeoffs(tool, name)}
  {review_note(tool)}
  {f'<p class="availability-note">Official website currently unavailable</p>' if website_unavailable else ''}
  <div class="tool-card__footer">
    <div class="resource-links" aria-label="Resources for {escape(name)}">{resource_links(tool, name)}</div>
    {compare_button}
  </div>
</article>""".strip()


def editor_card(tool: dict, reference_time: datetime) -> str:
    name = str(tool.get("name") or "Unnamed tool")
    category = str(tool.get("category") or "Misc")
    recommended_for = str(tool.get("best_for") or "")
    reason = str(tool.get("editor_reason") or "")
    status = lifecycle(tool, reference_time)[1]
    stars = stars_value(tool)

    return f"""
<article class="editor-card">
  <div class="editor-card__meta">
    <span class="eyebrow">{escape(category_title(category))}</span>
    {status_badge(tool, status)}
  </div>
  <div class="editor-card__title">
    <h3><a href="{escape(primary_url(tool))}" aria-label="Open the {escape(name)} project page">{escape(name)}</a>{title_icon(tool)}</h3>
    <span class="star-count" title="{stars:,} GitHub stars"><span aria-hidden="true">⭐</span> {stars:,}<span class="visually-hidden"> GitHub stars</span></span>
  </div>
  <p class="editor-card__audience">{escape(recommended_for)}</p>
  <p>{escape(reason)}</p>
  {tradeoffs(tool, name, inline=True)}
  <a class="text-link" href="#tool-{escape(tool.get('slug') or 'tool')}" aria-label="View catalog details for {escape(name)}">View catalog details<span aria-hidden="true"> ↓</span></a>
</article>""".strip()


def editor_more_markup(tools: list[dict], reference_time: datetime) -> str:
    if not tools:
        return ""
    cards = "\n".join(editor_card(tool, reference_time) for tool in tools)
    return f"""
<details class="editor-more">
  <summary>Show {len(tools)} more editor picks</summary>
  <div class="editor-grid">
    {cards}
  </div>
</details>""".strip()


def category_options(tools: list[dict]) -> str:
    counts = {
        category: sum(1 for tool in tools if tool.get("category") == category)
        for category in sorted(CATEGORY_ORDER, key=lambda value: category_title(value).casefold())
    }
    return "\n".join(
        f'<option value="{escape(category_id(category))}">{escape(category_title(category))} ({counts[category]})</option>'
        for category in sorted(CATEGORY_ORDER, key=lambda value: category_title(value).casefold())
        if counts[category]
    )


def status_options(tools: list[dict], reference_time: datetime) -> str:
    status_order = ("Active", "Quiet", "Inactive", "Unmaintained", "Unknown", "Historical")
    counts = {
        status: sum(1 for tool in tools if lifecycle(tool, reference_time)[1] == status)
        for status in status_order
    }
    return "\n".join(
        f'<option value="{escape(status)}">{escape(status)} ({counts[status]})</option>'
        for status in status_order
        if counts[status]
    )


def metadata_freshness(
    tools: list[dict], reference_time: datetime, window_days: int = 7
) -> tuple[int, int]:
    fresh = 0
    for tool in tools:
        updated = parse_date(tool.get("metadata_updated_at"))
        if not updated:
            continue
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        age_days = max((reference_time - updated).days, 0)
        if age_days <= window_days:
            fresh += 1
    return fresh, len(tools)


def render_index(tools: list[dict], reference_time: datetime) -> str:
    template = (SITE_SOURCE / "index.html").read_text(encoding="utf-8")
    current_tools = apply_pros_cons(
        [tool for tool in tools if not is_dead(tool, reference_time)],
        read_pros_cons(),
    )
    memorial_tools = [tool for tool in tools if is_dead(tool, reference_time)]
    catalog_tools = [tool for tool in current_tools if tool.get("category") != "SaaS"]
    hosted_tools = [tool for tool in current_tools if tool.get("category") == "SaaS"]
    ordered_editor_slugs = editor_choice_order()
    ordered_tools = recommended_tools(catalog_tools, reference_time, ordered_editor_slugs)

    editor_slugs = read_editor_choice_slugs()
    editor_order = {slug: rank for rank, slug in enumerate(ordered_editor_slugs)}
    editor_tools = apply_editor_choice_copy(
        sorted(
            [
                tool
                for tool in catalog_tools
                if tool.get("slug") in editor_slugs
            ],
            key=lambda item: (
                editor_order.get(str(item.get("slug") or ""), len(editor_order)),
                category_rank(item.get("category")),
                item.get("name", "").casefold(),
            ),
        ),
        read_editor_choice_copy(),
    )
    featured_editor_tools: list[dict] = []
    featured_categories: set[str] = set()
    for tool in editor_tools:
        category = str(tool.get("category") or "Misc")
        if category not in featured_categories:
            featured_editor_tools.append(tool)
            featured_categories.add(category)
    remaining_editor_tools = [tool for tool in editor_tools if tool not in featured_editor_tools]
    editor_more_section = editor_more_markup(remaining_editor_tools, reference_time)
    fresh_count, freshness_total = metadata_freshness(tools, reference_time)
    catalog_cards = [
        tool_card(tool, reference_time, rank, compare_enabled=True)
        for rank, tool in enumerate(ordered_tools, start=1)
    ]
    initial_catalog_cards = catalog_cards[:INITIAL_CATALOG_CARD_COUNT]
    deferred_catalog_cards = catalog_cards[INITIAL_CATALOG_CARD_COUNT:]
    catalog_card_markup = "\n".join(initial_catalog_cards)
    if deferred_catalog_cards:
        deferred_catalog_markup = "\n".join(deferred_catalog_cards)
        catalog_card_markup += f"""
<template id="catalog-card-template">
  {deferred_catalog_markup}
</template>
<button class="button button--secondary catalog-show-more" id="catalog-show-more" type="button" aria-controls="tool-grid">
  Show {len(deferred_catalog_cards)} more tools
</button>"""

    memorial_cards = "\n".join(
        tool_card(tool, reference_time, rank)
        for rank, tool in enumerate(
            sorted(
                memorial_tools,
                key=lambda item: item.get("name", "").casefold(),
            ),
            start=1,
        )
    )
    memorial_card_markup = (
        f'<template id="memorial-card-template">\n{memorial_cards}\n</template>'
        if memorial_cards
        else ""
    )

    replacements = {
        "{{CANONICAL_URL}}": SITE_URL,
        "{{REPOSITORY_URL}}": REPOSITORY_URL,
        "{{CURRENT_COUNT}}": str(len(current_tools)),
        "{{TOOL_COUNT}}": str(len(catalog_tools)),
        "{{HOSTED_COUNT}}": str(len(hosted_tools)),
        "{{MEMORIAL_COUNT}}": str(len(memorial_tools)),
        "{{EDITOR_COUNT}}": str(len(editor_tools)),
        "{{CATEGORY_COUNT}}": str(len({tool.get("category") for tool in catalog_tools})),
        "{{FRESH_COUNT}}": str(fresh_count),
        "{{FRESH_TOTAL}}": str(freshness_total),
        "{{AS_OF_DATE}}": reference_time.date().isoformat(),
        "{{TOOL_PROPOSAL_URL}}": escape(TOOL_PROPOSAL_URL),
        "{{CORRECTION_URL}}": escape(CORRECTION_URL),
        "{{CATEGORY_OPTIONS}}": category_options(catalog_tools),
        "{{STATUS_OPTIONS}}": status_options(catalog_tools, reference_time),
        "{{USE_CASE_OPTIONS}}": facet_options(catalog_tools, "use_cases"),
        "{{ECOSYSTEM_OPTIONS}}": facet_options(catalog_tools, "ecosystems"),
        "{{ARTIFACT_TYPE_OPTIONS}}": facet_options(catalog_tools, "artifact_type"),
        "{{LICENSE_OPTIONS}}": facet_options(catalog_tools, "license"),
        "{{CAPABILITY_OPTIONS}}": facet_options(catalog_tools, "capabilities"),
        "{{EDITOR_FEATURED_CARDS}}": "\n".join(
            editor_card(tool, reference_time) for tool in featured_editor_tools
        ),
        "{{EDITOR_MORE_SECTION}}": editor_more_section,
        "{{TOOL_CARDS}}": catalog_card_markup,
        "{{HOSTED_CARDS}}": "\n".join(
            tool_card(tool, reference_time, rank)
            for rank, tool in enumerate(
                sorted(hosted_tools, key=lambda item: item.get("name", "").casefold()),
                start=1,
            )
        ),
        "{{MEMORIAL_CARDS}}": memorial_card_markup,
    }
    for token, value in replacements.items():
        template = template.replace(token, value)
    template = template.replace(
        "Every catalog entry remains available below, but search, filtering, and sorting require JavaScript.",
        'The first recommendations remain available below. For the complete catalog, use the '
        f'<a href="{escape(REPOSITORY_URL)}#complete-catalog">canonical README</a> or '
        '<a href="exports/catalog.json">catalog JSON</a>. Search, filtering, sorting, and comparison require JavaScript.',
    )
    template = template.replace("assets/site.js?v=3", f"assets/site.js?v={SITE_JS_VERSION}")
    if "{{" in template or "}}" in template:
        raise ValueError("Unresolved placeholder remains in site/index.html")
    return template


def normalize_base_path(value: str) -> str:
    value = value.strip()
    if not value.startswith("/") or "://" in value or "?" in value or "#" in value:
        raise ValueError("Base path must be an absolute URL path")
    parts = [part for part in value.split("/") if part]
    if any(part in {".", ".."} for part in parts):
        raise ValueError("Base path cannot contain dot segments")
    return "/" + "/".join(parts) + "/" if parts else "/"


def render_not_found(base_path: str) -> str:
    template = (SITE_SOURCE / "404.html").read_text(encoding="utf-8")
    return template.replace("{{BASE_PATH}}", escape(base_path)).replace("{{REPOSITORY_URL}}", REPOSITORY_URL)


def validate_output(output: Path) -> None:
    required = (
        output / "index.html",
        output / "404.html",
        output / "assets" / "site.css",
        output / "assets" / "site.js",
        output / "assets" / "favicon.svg",
        output / "assets" / "social-preview.svg",
    )
    missing = [str(path.relative_to(output)) for path in required if not path.is_file()]
    missing.extend(
        f"exports/{path.name}"
        for path in (EXPORT_SOURCE / name for name in EXPORT_FILENAMES)
        if path.is_file() and not (output / "exports" / path.name).is_file()
    )
    if missing:
        raise ValueError("Missing generated site files: " + ", ".join(missing))

    index = (output / "index.html").read_text(encoding="utf-8")
    if index.count("<h1") != 1:
        raise ValueError("Generated home page must contain exactly one H1")
    if "{{" in index or "}}" in index:
        raise ValueError("Generated home page contains unresolved template placeholders")


def prepare_output(output: Path) -> None:
    if output.exists() and not output.is_dir():
        raise ValueError(f"Output path is not a directory: {output}")
    if output.exists() and any(output.iterdir()):
        marker = output / BUILD_MARKER
        if not marker.is_file():
            raise ValueError(
                f"Refusing to replace a non-empty directory not created by this generator: {output}"
            )
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / BUILD_MARKER).write_text("Generated by scripts/generate_site.py\n", encoding="utf-8")


def build_site(
    output: Path = DEFAULT_OUTPUT,
    reference_time: datetime | None = None,
    base_path: str = DEFAULT_BASE_PATH,
) -> Path:
    reference_time = reference_time or datetime.now(timezone.utc)
    base_path = normalize_base_path(base_path)
    prepare_output(output)

    tools = load_catalog()
    (output / "index.html").write_text(render_index(tools, reference_time), encoding="utf-8")
    (output / "404.html").write_text(render_not_found(base_path), encoding="utf-8")
    shutil.copytree(SITE_SOURCE / "assets", output / "assets")
    export_files = [EXPORT_SOURCE / name for name in EXPORT_FILENAMES]
    if any(path.is_file() for path in export_files):
        export_output = output / "exports"
        export_output.mkdir(exist_ok=True)
        for path in export_files:
            if path.is_file():
                shutil.copy2(path, export_output / path.name)
    (output / ".nojekyll").write_text("", encoding="utf-8")
    validate_output(output)
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate the GitHub Pages catalog site")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Generated site directory")
    parser.add_argument(
        "--base-path",
        default=DEFAULT_BASE_PATH,
        help="Absolute URL path where the generated site will be served",
    )
    parser.add_argument(
        "--as-of",
        help="Reproducible ISO-8601 date/timestamp (defaults to SOURCE_DATE_EPOCH or now)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output = build_site(
        args.output.resolve(),
        reference_time=resolve_reference_time(args.as_of),
        base_path=args.base_path,
    )
    print(f"Generated GitHub Pages site in {output}")


if __name__ == "__main__":
    main()
