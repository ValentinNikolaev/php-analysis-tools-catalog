# Search indexing and traffic measurement

The site is a static GitHub Pages project at
`https://valentinnikolaev.github.io/php-analysis-tools-catalog/`.
The existing Python generator publishes the homepage, browse index, category
pages, current tool details, selection guides, and `sitemap.xml`. It does not
require search-engine credentials to build or deploy.

## Content and routes

| Reader task | Route | Source of truth |
| --- | --- | --- |
| Search, filter, and compare tools | `/` | `common/catalog/*.yaml`, editorial YAML, `site/index.html` |
| Browse without JavaScript | `/browse/` | Current catalog categories and `site/guides.json` |
| Explore a complete category | `/categories/<category-id>/` | Catalog records and category descriptions in `scripts/generate_readme.py` |
| Check installation, compatibility, and trade-offs | `/tools/<slug>/` | Catalog record, `common/pros-cons.yaml`, `common/editor-choice-copy.yaml` |
| Choose a workflow or compare tools | `/guides/<slug>/` | `site/guides.json`, linked official documentation, current tool records |

Paths in this table are relative to the project URL. Existing homepage anchors,
including `#tool-<slug>`, remain supported. The homepage retains its bounded
initial card batch; every current record is also reachable through ordinary
HTML links to a category page and a detail page. Category pages do not defer
their cards into templates or require a click to reveal tools.

Historical projects remain in the homepage archive. They do not receive new
tool pages or sitemap entries. Query/filter variations, fragment links, exports,
and the `noindex` 404 page are excluded from the sitemap.

Tool pages reuse the maintained catalog facts and curated trade-offs rather
than copying a separate installation or compatibility database. Selection
guides link to current records and official documentation; the build fails if
a guide refers to a tool that is no longer current. Review guide prose when
its linked upstream behavior changes. No new search, font, or tracking service
is added; new pages use the existing Cloudflare Web Analytics beacon.

## Connect Google Search Console after deployment

1. Sign in to [Google Search Console](https://search.google.com/search-console/).
2. Add a **URL-prefix** property with exactly
   `https://valentinnikolaev.github.io/php-analysis-tools-catalog/`, including the
   protocol and final slash. DNS verification of `github.io` is not needed.
3. Choose **HTML tag** verification. Copy only its `content` value into
   `google-site-verification` in `site/search-verification.json`.
4. Commit that public verification identifier, merge, and let the existing
   Pages workflow publish it. Confirm the tag is in the live homepage's source,
   then select **Verify**. Leave the tag in place for future ownership checks.
   This value is deliberately public HTML metadata; never put account passwords,
   OAuth access tokens, API credentials, or private keys in this file.
5. In **Sitemaps**, submit `sitemap.xml` under the property. The complete URL is
   `https://valentinnikolaev.github.io/php-analysis-tools-catalog/sitemap.xml`.
6. Inspect the homepage, a category, a tool, and a guide with **URL Inspection**.
   Check indexing status, Google's selected canonical, last crawl, and rendered
   HTML. Request indexing for representative pages after publication.
7. Review **Page indexing** for exclusions and **Performance** for queries,
   impressions, clicks, and landing pages. Indexing and traffic are separate
   outcomes; a sitemap and an indexing request do not guarantee either.

An empty verification setting emits no meta tag. The repository build can
prepare these pages without access to the owner's Google account; property
creation, verification, and submission are account-side steps.

Official instructions: [property types](https://support.google.com/webmasters/answer/34592),
[HTML tag verification](https://support.google.com/webmasters/answer/9008080),
[URL Inspection](https://support.google.com/webmasters/answer/9012289), and
[sitemap submission](https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap).

## Connect Bing Webmaster Tools

Add the same project URL in [Bing Webmaster Tools](https://www.bing.com/webmasters/).
If the account offers HTML meta-tag verification, copy the supplied `msvalidate.01`
content into `site/search-verification.json`, deploy, and verify. Submit the same
sitemap URL. Use the verification method offered in your account; no Bing account
credentials belong in the repository.

## robots.txt on a project site

Search engines read `https://valentinnikolaev.github.io/robots.txt` at the **host
root**. A file at `/php-analysis-tools-catalog/robots.txt` would not control
crawling, so this project does not generate one. A missing root robots.txt does
not prohibit crawling.

If a root Pages site is maintained in the separate
`ValentinNikolaev.github.io` repository, its owner can add this absolute sitemap
reference to its existing robots.txt without replacing unrelated rules:

```text
Sitemap: https://valentinnikolaev.github.io/php-analysis-tools-catalog/sitemap.xml
```

Direct submission through the verified Search Console property works without
that root-file change. See Google's [robots.txt location rules](https://developers.google.com/crawling/docs/robots-txt/create-robots-txt).

## Verify the traffic counter

Cloudflare Web Analytics is browser-based real user monitoring. A zero count
does not demonstrate that crawlers never requested the HTML. GitHub repository
Traffic measures the repository rather than this Pages website.

For a controlled analytics check after deployment:

1. Open the live site in a browser profile where extensions do not block the
   existing analytics script; use the correct site and time range in Cloudflare.
2. In browser Network tools, confirm `beacon.min.js` loads and a request reaches
   `https://cloudflareinsights.com/cdn-cgi/rum` when navigating away or hiding
   the tab. GitHub Pages is not served through the owner's Cloudflare proxy.
3. Confirm the public beacon identifier matches the configured Web Analytics
   site and that its event appears after processing.
4. If the request is absent, inspect console errors, network blocking, and
   site configuration before changing the tracking code.

Keep local browser audits from inflating production analytics: block
`static.cloudflareinsights.com` and `cloudflareinsights.com` in the test context.
See [Cloudflare data collection](https://developers.cloudflare.com/web-analytics/data-metrics/data-origin-and-collection/)
and [GitHub repository traffic](https://docs.github.com/en/repositories/viewing-activity-and-data-for-your-repository/viewing-traffic-to-a-repository).

## Build and verify

```shell
python scripts/validate_catalog.py
python -m unittest discover -s tests
python scripts/generate_site.py --output site-dist --as-of 2026-10-13
node --check site/assets/page.js
git diff --check
```

The build checks local links, required assets, one H1 per page, and unresolved
template markers. Tests simulate a crawler that follows links without executing
JavaScript or reading templates, require all current pages to be reachable,
compare the sitemap against actual public pages, and check custom-base-path
canonicals and escaped verification identifiers.

Preview the output under `/php-analysis-tools-catalog/`; nested pages use relative
asset and navigation URLs. `--base-path /preview/` changes the canonical path,
sitemap URLs, and not-found links consistently for a separate preview mount.
The existing Pages build/deployment workflows own delivery; no new publishing
or scheduled automation is needed.

## Reach readers and measure outcomes

Use the comparison guides as the entry point for a release announcement or a
useful contribution to PHP communities. Describe the concrete choice a guide
helps with and link to that page. Propose inclusion in relevant maintained PHP
resource lists according to their contribution rules. The repository already
links to the site from its generated README; no outreach messages are sent by
the site build.

Track the steps separately: pages indexed, search impressions, search clicks,
and measured browser visits. Review Search Console regularly as data arrives,
then improve pages for actual queries and reader questions. Do not manufacture
visits or treat crawler counts as an audience metric.
