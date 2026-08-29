# Material report theme contract

Use this reference whenever Hwahap renders or reviews `report.html`.

## Source boundary

Primary visual reference:

- https://github.com/nexu-io/open-design/tree/a554d017c8fa12d8913354ba6cf792d26d0c3b54/design-systems/material
- Snapshot: `a554d017c8fa12d8913354ba6cf792d26d0c3b54`
- License: Apache-2.0
- Material directory last changed at `f1a0b60c6cd1c9f5c735ae5645e47244b468e71c`

Read `USAGE.md`, `DESIGN.md`, `tokens.css`,
`components.manifest.json`, `components.html`, and the three `preview/`
pages before changing the renderer.

The package explicitly says it is a curated fixture “inspired by Material”; it
is not fresh evidence of Google's official Material 3 implementation. Describe
the result as a Hwahap Material 3 theme informed by this fixture, not as an
official Google component library.

Official Material references remain the semantic and accessibility baseline:

- https://m3.material.io/styles/color/system/overview
- https://m3.material.io/styles/typography/overview
- https://m3.material.io/styles/shape/overview
- https://m3.material.io/styles/elevation/overview
- https://m3.material.io/foundations/interaction/states/overview
- https://m3.material.io/foundations/layout/understanding-layout/overview
- https://m3.material.io/styles/motion/overview
- https://www.w3.org/TR/WCAG22/

## Human reading order

The page must answer these questions before exposing the ledger:

1. Did the goal complete?
2. What was wrong?
3. Why did it happen?
4. What changed and what improvement is expected?
5. What remains unverified or needs a decision?

Keep all canonical evidence in one collapsed native disclosure after this
summary. Do not put raw rows between the title and the decision sections.

## Fixture token contract

Copy the fixture's visual language, with semantic aliases where Hwahap needs
Material roles:

- Background: `--bg: #f8fafd`
- Surface: `--surface: #ffffff`
- Warm/selected surface: `--surface-warm: #e8f0fe`
- Text: `--fg: #202124`, `--fg-2: #3c4043`, `--muted: #5f6368`
- Action: `--accent: #1a73e8`, white on-accent, hover and active mixtures
- Boundaries: `--border: #dadce0`, `--border-soft: #edf0f2`
- State: `--success: #188038`, `--warn: #f9ab00`, `--danger: #d93025`
- Display/body/mono: Google Sans, Roboto, Roboto Mono with local fallbacks
- Type sizes: 12, 14, 16, 18, 24, 32, 48, 64px
- Spacing: 4, 8, 12, 16, 20, 24, 32, 48px
- Section spacing: 96px desktop, 68px tablet, 48px phone
- Shape: 4px, 12px, 24px, pill
- Elevation: flat, one-pixel ring, 3px/8px raised shadow
- Focus: four-pixel translucent blue ring
- Motion: 150ms and 250ms with `cubic-bezier(.2,0,0,1)`
- Container: 1200px with 36/24/16px responsive gutters

Do not scatter raw colors, radii, spacing, font stacks, or shadows outside the
token declarations.

## Required composition

- Page: light gray background with one restrained blue ambient gradient.
- App bar: white surface, thin bottom boundary, brand and explicit status.
- Navigation: secondary button/chip treatment with border and blue focus ring.
- Hero: 1.1fr explanation and 0.9fr raised outcome panel on desktop.
- Outcome panel: panel header, status, and a divided metric grid.
- Change record: raised or ringed panel with three warm mini-cards for problem,
  cause, and applied improvement.
- Remaining risk and proposal: neutral tiles with a state-colored edge or label,
  not full saturated cards.
- Evidence vault: one raised panel; inner cards stay flat or ringed.
- Table: white surface, soft row boundaries, internal horizontal scrolling.
- Footer: muted metadata and exact source disclosure.

Use blue for interaction and one focal element. Use whitespace and surface
layers before borders or shadows. Do not tint every section, use multiple
unrelated accent colors, or make all headings the same size.

## Interaction and state

- Native links and disclosures have enabled, hover, focus-visible, and pressed
  states where applicable.
- Focus uses both the blue ring and a boundary/color change.
- Every success, warning, and error color has literal Korean state text.
- Targets are at least 44px high; Hwahap navigation and disclosures use 48px.
- Honor `prefers-reduced-motion: reduce`.
- Preserve keyboard order and semantic landmarks.

## Dark, contrast, and adaptive behavior

The dark extension follows `system/kit.dark.html`: `#0f1115` background,
`#171a21` surface, `#f8fafc` text, `#a7adba` muted text, and `#2a2f3a`
boundaries. Adjust the blue interaction color only as needed for contrast.

- Phone below 640px: one column and 16px gutter.
- Tablet below 1024px: one column where panels would become cramped, 24px gutter.
- Desktop: 1200px container and 36px gutter.
- Page-level horizontal overflow is forbidden.
- Wide tables scroll only inside `.table-wrap`.
- Increased-contrast and print modes remain usable.

## Mechanical acceptance

- OpenDesign source metadata and commit are present exactly once.
- All fixture token groups are declared; key semantic roles are used through aliases.
- Hero, panel, panel-head, metric-grid, mini-card/tile, status, and state
  selectors exist.
- Light, dark, increased-contrast, reduced-motion, phone, tablet, desktop, and
  print rules exist.
- Outcome content precedes deviations, proposals, validation, and evidence.
- Evidence is collapsed initially and the exact canonical ledger appears once.
- No Astryx, React, script, import map, CDN stylesheet, or external font load.
- Major text/surface pairs meet WCAG 2.2 contrast.
- The complete HTML validates against the canonical payload.
