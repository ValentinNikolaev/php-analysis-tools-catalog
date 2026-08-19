# Static analysis tools for PHP

This file is generated from the manually approved membership in `common/editor-choice.yaml`, catalog records in `common/catalog/*.yaml`, and editorial copy in `common/editor-choice-copy.yaml`.
Selection considers present-day PHP relevance, maintenance, documentation, adoption, and a distinct practical use case. Stars and repository freshness are supporting evidence, not an automatic ranking or per-category quota.
Generation fails when a selected tool is historical or lacks a specific recommendation and rationale.
⭐ shows GitHub stars.

## Bug finders

Tools that inspect PHP code without running it to identify type errors, defects, dependency problems, and potential vulnerabilities.

| Tool | Recommended for | Why it stands out |
|---|---|---|
| [PHPStan](https://github.com/phpstan/phpstan)<br><sub>⭐ 14,075</sub> | PHP applications that need configurable type-safety checks and a broad extension ecosystem | Rule levels, baselines, and framework extensions support both gradual adoption and deep type analysis. |
| [psalm](https://psalm.dev)<br><sub>⭐ 5,881</sub> | Projects needing advanced type modelling, taint analysis, and security checks | An expressive type system and taint engine cover correctness and application-security problems. |

## Coding standards

Linters and rule-enforcement tools for formatting, naming, documentation, and project-specific coding conventions.

| Tool | Recommended for | Why it stands out |
|---|---|---|
| [PHP_CodeSniffer](https://github.com/PHPCSStandards/PHP_CodeSniffer)<br><sub>⭐ 1,546</sub> | Teams enforcing published PHP standards or detailed project-specific coding rules | Its extensible sniff API supports mature community standards and precise custom rules. |

## Architecture rules

Ready-to-use tools that enforce dependency boundaries and architectural constraints in an application.

| Tool | Recommended for | Why it stands out |
|---|---|---|
| [Deptrac](https://github.com/sensiolabs-de/deptrac.git)<br><sub>⭐ 2,994</sub> | Layered applications and modular monoliths that enforce dependency boundaries in CI | Dependency rules convert intended architecture boundaries into repeatable CI checks. |

## Libraries and building blocks

Parsers, reflection libraries, and control-flow components for developers building custom analysis rules or tools.

| Tool | Recommended for | Why it stands out |
|---|---|---|
| [PHP Parser](https://github.com/nikic/PHP-Parser)<br><sub>⭐ 17,453</sub> | Developers building analyzers, refactoring tools, formatters, or source transformations | A mature AST, traversal API, and code builder underpin many PHP analysis and transformation tools. |

## Fixers and refactoring

Tools that automatically correct coding-standard violations, upgrade PHP syntax, or refactor existing code.

| Tool | Recommended for | Why it stands out |
|---|---|---|
| [PHP CS Fixer](https://github.com/FriendsOfPHP/PHP-CS-Fixer)<br><sub>⭐ 13,546</sub> | Projects that want automatic formatting and coding-standard fixes | A broad fixer catalog and custom rule sets make formatting changes deterministic and automatable. |
| [Rector](https://github.com/rectorphp/rector)<br><sub>⭐ 10,404</sub> | Teams automating PHP upgrades, framework migrations, or repeatable refactoring | AST-based rules turn upgrades and refactoring recipes into reviewable project-wide code changes. |
| [Laravel Pint](https://laravel.com/docs/pint)<br><sub>⭐ 3,151</sub> | Laravel projects that want a low-configuration, framework-oriented formatter | Laravel-maintained presets deliver practical PHP-CS-Fixer defaults with very little setup. |

## Specialized tools

Wrappers, baseliners, multi-language engines, and focused analysis tools that do not fit the primary categories.

| Tool | Recommended for | Why it stands out |
|---|---|---|
| [Semgrep](https://semgrep.dev)<br><sub>⭐ 16,294</sub> | Security teams writing custom checks for PHP and polyglot repositories | Source-like patterns make custom bug and security checks accessible across multiple languages. |
