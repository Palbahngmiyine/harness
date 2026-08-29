# Material 3 report contract

Use this reference whenever Hwahap renders or reviews `report.html`.

## Evidence boundary

The visual and interaction contract comes from Google's current official
Material 3 documentation. The snapshot date is 2026-08-29.

Primary index:

- https://m3.material.io/foundations
- https://m3.material.io/sitemap.xml

The sitemap contained 68 Foundations URLs. They were all opened and inspected:

- Root 1; overview 2; building-for-all 2; content-design 8
- customization 1; design-tokens 2; designing 5; glossary 1
- interaction 6; layout 21; usability 2; watches 4
- writing 3; XR 10

Implementation supplements:

- https://m3.material.io/styles/color/roles
- https://m3.material.io/styles/color/static/baseline
- https://m3.material.io/styles/typography/type-scale-tokens
- https://m3.material.io/styles/shape/corner-radius-scale
- https://m3.material.io/styles/elevation/overview
- https://m3.material.io/styles/motion/overview/how-it-works
- https://m3.material.io/components/cards/overview
- https://m3.material.io/components/cards/guidelines
- https://m3.material.io/components/cards/specs
- https://m3.material.io/components/dialogs/specs
- https://m3.material.io/components/bottom-sheets/specs
- https://m3.material.io/components/lists/guidelines
- https://m3.material.io/foundations/layout/canonical-examples/supporting-pane
- https://coolors.co/tailwind/c2e7ff
- https://www.w3.org/TR/WCAG22/

Watch and XR pages were reviewed but their round-screen and spatial layout
rules do not apply to a flat local web report. General accessibility, content,
token, interaction, and layout rules still apply.

## Human reading order

Before exposing the ledger, answer:

1. Did the goal complete?
2. What was wrong?
3. Why did it happen?
4. What changed and what improvement is expected?
5. What remains unverified or needs a decision?

Keep canonical evidence in one collapsed native disclosure after the summary.
Do not place raw rows between the title and decision sections.

## Token and color roles

Use named `--md-sys-*` tokens. Component rules must not contain scattered raw
colors, spacing, radii, font stacks, or shadows.

- Primary is reserved for the strongest action and emphasis.
- Secondary is used for less prominent controls and proposal emphasis.
- Error and error-container communicate errors and unverified risk.
- Surface is the page background. The five surface-container roles establish
  hierarchy and remain mapped to the same regions at every breakpoint.
- On-colors are used only on their paired container.
- Outline marks strong interactive boundaries. Outline-variant is used for
  dividers or the boundary of an intentionally selected outlined card.
- Success and warning are explicit Hwahap add-on roles with paired on-colors,
  literal Korean status text, and an icon. Color is never the only cue.

The role model remains Material 3; the custom hue source is Coolors' Icy Blue
scale generated from seed `#C2E7FF`. Coolors reports: 50 `#E5F5FF`, 100
`#CCEBFF`, 200 `#99D6FF`, 300 `#66C2FF`, 400 `#33ADFF`, 500 `#0099FF`, 600
`#007ACC`, 700 `#005C99`, 800 `#003D66`, 900 `#001F33`, 950 `#001524`.

Light mode uses 600–800 for actions, 50–100 for containers, and blue-tinted
near-white surfaces. Dark mode uses 950–800 surfaces and 300–100 emphasis.
Error, success, and warning retain distinct semantic hues instead of becoming
blue. Every custom role must keep its paired on-color across themes.

Every body-size text pair must meet 4.5:1. Large text and meaningful graphical
boundaries must meet 3:1. Decorative outline-variant dividers are exempt from
the target-boundary requirement.

## Component surfaces

Choose the component before choosing decoration. Do not apply one generic
border rule to every region.

- Elevated card: `surface-container-low`, level 1 elevation, no border.
- Filled card: `surface-container-highest`, level 0 elevation, no border.
- Outlined card: `surface`, level 0 elevation, and outline-variant border.
- Hwahap uses filled cards for ordinary records and one elevated card for the
  outcome summary. It does not render outlined report cards.
- Cards contain one subject. If spacing, a heading, or a divider gives a simpler
  hierarchy, do not force that content into another card.
- Card shape is the official 12px medium corner with 16px minimum content
  padding. Dividers may separate regions inside a card.
- The remaining-risk supporting pane is a secondary layout area, not a card.
  It uses a tonal surface and moves below the focus pane under 840px.
- The evidence disclosure follows the bottom-sheet surface role:
  `surface-container-low`, 28px top-level shape, and no outer border.
- Non-interactive audit lists use filled items and gaps. Do not add decorative
  leading borders; reserve dividers for complex or uncontained lists.

## Type, shape, elevation, and spacing

- Declare all 15 baseline type-scale roles. Use only the subset needed for a
  clear title, section heading, title, body, and label hierarchy.
- Use `rem` for text. Korean needs sufficient line height and must survive a
  200% text increase without clipping, overlap, or hidden information.
- Keep critical prose at no more than 60 characters per line.
- Declare the ten-step shape scale: 0, 4, 8, 12, 16, 20, 28, 32, 48, and full.
- Avoid very round shapes on information-dense cards. Use full corners for
  chips and compact targets only.
- Prefer tonal surface hierarchy. Only the outcome's elevated card uses level 1;
  all filled cards and layout panes use level 0.
- Use 4px-based spacing. Group related facts by proximity and separate major
  decisions with negative space.

## Adaptive scaffold

Use the official web breakpoints:

- Compact: under 600px, one pane, 16px margin.
- Medium: 600–839px, one high-density pane, 24px margin.
- Expanded: 840–1199px, primary and supporting panes, 24px margin.
- Large: 1200–1599px, two panes with more spacing, 32px margin.
- Extra-large: 1600px and above, two panes with 48px margin.

The report has no third independent task, so extra-large remains two panes.
The primary pane explains the outcome and changes; the supporting `aside`
contains remaining risk. Do not stretch the same card layout wider.

Use logical properties such as `inline`, `block`, `start`, and `end` so layout
structure remains bidirectional. Page-level horizontal overflow is forbidden.
Wide audit tables scroll only inside `.table-wrap`.

## Interaction and accessibility

- Use one `h1`, sequential headings, `header`, labeled `nav`, `main`, supporting
  `aside`, and `footer` landmarks.
- Native links and disclosures remain keyboard-operable.
- Interactive targets use at least 48px block size.
- Hover uses an 8% content-colored state layer; focus and press use 10%.
  Only one pseudo-element layer represents the current state.
- Focus also uses a visible 3px primary outline, so color fill is not the only
  indicator.
- Honor `prefers-reduced-motion`, `prefers-contrast`, dark mode, and print.
- Wrap long text. Do not use ellipsis, fixed text height, or silent truncation.
- Preserve vertical reflow at 200% zoom; tables are the only horizontal scroll
  region.

## Required composition

- Full-width tonal top app bar with brand and explicit status.
- Scrollable pill navigation with enabled, hover, focus, and pressed states.
- Hero with a restrained headline and one elevated outcome card.
- Outcome metrics on surface-container-lowest.
- Problem, cause, and fix grouped in one filled card with internal dividers, not
  nested cards or an outer outline.
- Expected change uses the paired success container and states its limitation.
- Remaining risk is a supporting pane; proposals use secondary emphasis.
- Evidence uses one disclosure, tonal containers, semantic tables, and the
  complete canonical ledger.

## Mechanical acceptance

- Metadata identifies official Material guidance, the 68-page Foundations
  audit, source URL, and snapshot date exactly once.
- No OpenDesign, Astryx, Google Blue `#1a73e8`, React, script, import map, CDN
  stylesheet, external font, or runtime network dependency remains.
- All color, type, shape, elevation, motion, and state token groups exist.
- Filled and elevated card variants use their official surface and elevation
  roles; report cards, supporting pane, and evidence surface have no outer
  outline.
- Breakpoint rules exist at 600, 840, 1200, and 1600px.
- Status has text and icon; focus and state layers are mechanically present.
- Outcome precedes deviations, proposals, validation, and evidence.
- Evidence starts collapsed; the canonical ledger appears exactly once.
- Long sanitized text and all records remain available without a count cap.
- Major light and dark text/container pairs pass contrast tests.
- The complete HTML validates against the canonical payload.
