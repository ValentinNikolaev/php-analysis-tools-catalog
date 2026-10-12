# GitHub Pages UX audit and improvements

Audit date: 2026-10-12. Target: the production-equivalent local build of the PHP Analysis Tools Catalog, served at `http://127.0.0.1:4173/php-analysis-tools-catalog/`. This is a local verification report, not a claim about the deployed site.

The audit used `audit-github-pages-ux` and its rendered checklist. Implementation also applied `create-github-pages`, `github-pages-content-architecture`, and `github-pages-visual-system` from the installed ValentinNikolaev agent-plugins package.

## Scope and evidence

- Initial build and screenshots: `python scripts/generate_site.py --output site-dist`, using catalog data from `9ad70f2c` and the updated working-tree site sources.
- Browser: Chrome 154.0.8037.98, controlled by Playwright 1.64.0; accessibility engine: axe-core 4.14.0. Browser tooling was installed outside the repository.
- Viewports: 1440 × 900 and 390 × 844 in light and dark themes; 768 × 1024 and 320 × 700 in light theme. Additional keyboard journeys used widths 1440, 390, and 320.
- Journeys: home → search → category/filter → project resources; editor picks → tool anchor; hosted-service search; zero results → reset; comparison; archive disclosure; nested missing route → 404 → home.
- Additional checks: 200% text size at 720 × 450, reduced motion, Windows forced-color emulation, disabled JavaScript, and restricted browser storage.
- The public site contains a single catalog page and a 404 page. There are no nested documentation pages to audit; nested missing routes were tested instead. The card grid and comparison table represent its reference-heavy content.

## Confirmed findings and corrections

| ID / severity | Rendered evidence | Reader impact | Correction | Verification |
| --- | --- | --- | --- | --- |
| UX-01 · major | At 1440 × 900 in both themes, the sticky filter form occupied 330 px below the header and covered cards while scrolling. See [before catalog](ux-audit/before-catalog.png). | Readers lost a substantial part of the viewport while comparing entries. | Keep the form in document flow; show search and a labelled filter disclosure first. | Scroll through cards with filters both closed and open; confirm that the form does not cover results. The closed form now occupies 107 px. |
| UX-02 · major | At 390 × 844 in both themes, search started at document Y=1680 and the tool grid at Y=5218. The hero stacked four large statistics, and expanded editor cards preceded all results. | Finding a tool required several screens of scrolling before reaching the catalog. | Shorten the introduction, compact statistics, add category shortcuts, and place recommendations in a native disclosure. Keep the editor anchor and open it when explicitly followed. | Search now starts at Y=842 and results at Y=1402. Keyboard, URL-filter, and editor deep-link journeys pass. |
| UX-03 · minor | At desktop and tablet widths, 24 initially rendered date fields exceeded their available width and displayed ellipses. | Commit and release dates could not be read directly when comparing activity. | Use two columns for metadata and allow long values to wrap. | No initially rendered metadata field exceeds its width at any of the six audited viewport/theme combinations; dates are visible in [after catalog](ux-audit/after-catalog.png). |
| UX-04 · minor | When the archive was expanded at width 390 during verification, a historical-status badge extended to X=395. | Archived entries introduced horizontal page scrolling. | Allow headings and status groups to wrap; allow long tool names to break. | Open the archive at widths 390 and 320; document width stays within the viewport. |
| UX-05 · major | Expanded-state accessibility checks identified `aria-label` on generic containers; the zero-results state produced an `aria-prohibited-attr` violation for the empty results container. | Named result and resource groups did not have reliable accessibility semantics. | Give results a named region and give shortcuts, resources, trade-offs, and footer links group roles. | Repeat axe checks on all six interaction states in both themes and at desktop/mobile widths: no violations in 24 state checks. Screen-reader behavior itself remains untested. |

## Visual direction and preserved contracts

**Keep:** the lightweight Python/HTML/CSS/JavaScript stack, PHP wordmark, project icons, single-page catalog, repository-backed facts, public anchors, local search, URL-addressable facets, progressive loading, comparison, archive, exports, policy links, and existing analytics configuration.

**Improve:** a warm off-white light theme with a teal accent and a blue-green dark theme; smaller headings and section spacing; readable metadata; restrained shadows; 44 px targets for category, comparison, resource, and trade-off controls. A system/light/dark theme button persists the reader's choice and also applies it to the 404 page. Restricted browser storage does not prevent theme changes.

**Opportunity implemented:** category shortcuts make common tasks discoverable without opening eight selectors. Pros and cons expand in the card's reading flow. These are usability enhancements, separate from the confirmed defects above. The palette choice is an editorial design preference, not an accessibility finding.

No production dependencies, external fonts, external services, deployment workflows, or catalog records were added or changed for this work. Existing unrelated working-tree edits were preserved.

## Before and after

| View | Before | After |
| --- | --- | --- |
| Desktop introduction | [Original](ux-audit/before-desktop.png) | [Light theme](ux-audit/after-desktop-light.png) · [Dark theme](ux-audit/after-desktop-dark.png) |
| Mobile introduction | [Original](ux-audit/before-mobile.png) | [Updated](ux-audit/after-mobile.png) |
| Catalog | [Obscured by filters](ux-audit/before-catalog.png) | [Readable cards](ux-audit/after-catalog.png) |
| Missing route | — | [Updated 404](ux-audit/after-404.png) |

The mobile result grid moved approximately 73% closer to the top of the document. Desktop search moved from Y=1109 to Y=743; desktop results moved from Y=2878 to Y=1098. Positions describe the default state and the audited data snapshot, not a universal performance metric.

## Verification results and limits

- Initial working-tree validation passed: 111 entries and 235 review candidates; all 162 tests passed, including pre-existing unrelated local tests.
- The isolated PR checkout applies only the Pages changes to `e48f0efb` (latest `master` at PR preparation). Catalog validation passed with 111 entries and 573 review candidates; all 127 tests passed, and the production build and JavaScript syntax checks passed. Existing site assertions were updated for the theme asset, new palette, and preserved deep-link handling.
- 124 browser assertions passed: keyboard navigation and focus, search, reload persistence, facets and sorting, category shortcuts, zero results, hosted results, trade-offs, four-tool comparison limits, keyboard table scrolling, modal focus restoration, theme persistence, 404 recovery, archive hydration, overflow, JavaScript fallback, enlarged text, and reduced motion.
- axe reported no WCAG A/AA violations across the six initial viewport/theme combinations, 24 expanded interaction states, and tested 404 routes.
- The isolated PR checkout repeated all 124 browser assertions, six viewport/theme checks, and 24 expanded-state accessibility checks against the latest catalog; all passed with no axe violations. Its preview used the same base path on local port 4174.
- axe left some contrast checks for review because decorative arrow characters contain no text and parts of scrollable comparison tables were obscured. The table's actual computed foreground/background pairs were checked separately: minimum 5.61:1 in light theme and 7.52:1 in dark theme. Decorative arrows inherit their parent link color and convey no additional information.
- No page-level horizontal overflow was observed in the checked states. Enlarged text and forced colors preserved access to the controls.
- JavaScript syntax checks and `git diff --check` passed. The production build validates generated assets and unresolved placeholders; repository tests check internal anchors and custom-base-path 404 links.

This is not accessibility certification. Assistive-technology announcements, Firefox, Safari, physical touch devices, actual browser zoom, deployed GitHub Pages behavior, and external project-link availability were not tested. The enlarged-text check does not substitute for actual browser zoom. The existing analytics beacon was blocked during local browser checks to avoid sending audit traffic.

## Build and delivery

```powershell
python scripts/validate_catalog.py
python -m unittest discover -s tests
python scripts/generate_site.py --output site-dist
node --check site/assets/site.js
node --check site/assets/theme.js
git diff --check
```

The preview must mount `site-dist` beneath `/php-analysis-tools-catalog/`, including the 404 handler, rather than assuming a domain-root deployment. The changes are prepared on the `codex/improve-pages-ux` review branch. The existing Pages workflow still owns publication after merge; deployment configuration and repository settings are unchanged.

Tool methodology: [Playwright BrowserType documentation](https://playwright.dev/docs/api/class-browsertype), [axe-core documentation](https://github.com/dequelabs/axe-core).
