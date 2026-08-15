# League Caddie — Design Language

**"Pairings Sheet"** · v1.0 · adopted 2026-08-14

This document is the single authority on how League Caddie looks. Every visual value in the app
comes from here. If a value is not in this document, it does not go in the codebase — add the
token here first.

Enforced by the `unslop` skill (`.claude/skills/unslop/`). Run `/unslop audit` before shipping UI.

---

## 1. The reference

Two physical objects, both from the game itself:

**The pairings sheet.** The single printed page handed out at a club championship. Ruled
horizontal lines, no boxes. Names left, tee times right, figures in a column that aligns to the
digit. Dense, unglamorous, and completely legible at arm's length in bright sun. Nothing on it is
decorative, and it is beautiful for exactly that reason.

**The hand-hung leaderboard.** Deep painted-green plywood. White letters for names, red numerals
for under par. Flat color, hard edges, no gloss. When a number changes, someone walks up a ladder
and changes it — so nothing changes that doesn't matter.

The app is a pairings sheet that updates itself, read off a leaderboard.

**Personality:** ruled · tabular · plainspoken · flat · legible-in-sun

**Anti-examples** — things this app is explicitly not: a SaaS dashboard, a crypto exchange, a
fitness tracker, a "modern landing page."

---

## 2. Typography

Three faces, self-hosted via `@fontsource-variable` (no CDN request, no ongoing cost).

| Role | Face | Why this one |
|---|---|---|
| Display | **Archivo** (variable, 500–800) | An American grotesque drawn for high-performance print and UI. It holds its counters at 800 weight and its numerals are unmistakable — the closest free face to hand-painted board lettering. Used for page titles, scores, money, and position numbers. |
| Text | **Spline Sans** (variable, 300–700) | A humanist-tempered grotesque, narrower and warmer than Archivo, comfortable at 16px inside dense tables. Carries all reading text and UI labels. |
| Data | **Spline Sans Mono** (variable, 400–600) | Money and scores must align to the digit down a column. Mono here is functional — it is how a scorecard works — never decorative. |

**Explicitly not used:** Inter, Geist, Roboto, Open Sans, Poppins, Space Grotesk (the no-choice
defaults) or Instrument Serif, Fraunces, Playfair Display (the tasteful-choice defaults).

### Scale

Modular, ×1.25 from a 16px base. Never interpolate between steps.

| Token | Size / line-height | Face | Use |
|---|---|---|---|
| `text-display` | 44px / 1.02, -0.03em, 800 | Archivo | Landing headline only |
| `text-title` | 30px / 1.1, -0.02em, 700 | Archivo | Page title (one per page) |
| `text-heading` | 21px / 1.2, -0.015em, 700 | Archivo | Section heading |
| `text-subhead` | 17px / 1.3, -0.01em, 600 | Archivo | Card / row heading |
| `text-body` | 16px / 1.55, 400 | Spline Sans | Reading text |
| `text-ui` | 15px / 1.4, 500 | Spline Sans | Buttons, labels, nav |
| `text-small` | 13px / 1.45, 400 | Spline Sans | Secondary and meta text |
| `text-micro` | 11px / 1.3, 600, +0.06em | Spline Sans | Column headers, status marks |
| `text-figure` | 28px / 1, 700, tabular | Archivo | Headline numbers (points, money) |
| `text-data` | 15px / 1.4, 500, tabular | Spline Sans Mono | In-table numerals |

**Rules.** Body copy never below 16px. Measure capped at 68 characters (`max-w-prose`). All
numerals `font-variant-numeric: tabular-nums`. Hierarchy comes from weight and size, never from a
third family.

**`text-micro` is the only uppercase-letterspaced style, and it is a column header or a status
mark — not a decorative kicker above every heading.** Before this redesign the app carried 121 of
those; a page may now have at most one true eyebrow, and most pages have none.

---

## 3. Color

Three hues plus one restricted mark color. All ramps are custom, and the stock Tailwind
namespaces are not used at all — `gray`, `slate` and framework `green` are a tell in their own
right. Every surface in the codebase names one of the four ramps below.

### Ink — the neutral (≈60% of any screen)

A near-black with a faint green-grey cast, so the neutrals belong to the brand instead of sitting
next to it.

| Token | Hex | Role |
|---|---|---|
| `ink-950` | `#0F1512` | Headings, primary text |
| `ink-900` | `#171E1A` | Board text on light |
| `ink-800` | `#232B27` | — |
| `ink-700` | `#3A433E` | — |
| `ink-600` | `#4C5551` | Secondary text (7.5:1 on sheet) |
| `ink-500` | `#69726D` | Muted text, smallest readable (4.8:1) |
| `ink-400` | `#878F8A` | Non-text only — icons, disabled glyphs |
| `ink-300` | `#B4BAB6` | — |
| `ink-200` | `#DADEDA` | **Rules and hairlines** |
| `ink-100` | `#E6E9E5` | Subtle fills, table zebra |
| `ink-50` | `#EEF0EC` | — |

### Surfaces

| Token | Hex | Role |
|---|---|---|
| `page` | `#ECEEE9` | Page ground — cool newsprint. **Not cream.** |
| `sheet` | `#FBFCFA` | The raised sheet: panels, cards, table bodies |

Neither is pure `#FFFFFF` or `#000000`. The 4% lightness step between `page` and `sheet` is the
primary means of separation in this app — reach for it before a border.

### Fairway — the brand (≈30%)

Sampled from painted leaderboard plywood: deeper and bluer than Tailwind's green, and
deliberately *not* the sage/emerald that AI design defaults to.

| Token | Hex | Role |
|---|---|---|
| `fairway-950` | `#071A14` | Deepest board |
| `fairway-900` | `#0B2A20` | Nav bar, board bands, footer |
| `fairway-800` | `#123829` | Board hover |
| `fairway-700` | `#1A4B3B` | **Primary action** (9.7:1 with white) |
| `fairway-600` | `#236049` | Primary hover |
| `fairway-500` | `#2F7A5C` | Marks on dark |
| `fairway-400` | `#4E9A79` | Text on board (7:1 on `fairway-900`) |
| `fairway-200` | `#B8D3C7` | — |
| `fairway-100` | `#D9E7E0` | Selection fill |
| `fairway-50` | `#EDF3F0` | Faintest tint |

**Green is chrome and action — it is not a wash.** It appears on the nav, the primary button,
the board bands, and selected state. It does not tint page backgrounds, and it never appears as
a gradient.

### Flag — the accent (≈10%)

Golf's under-par red, taken straight off the leaderboard. This is a domain semantic, not a
decorative accent: on a scorecard red means *below the number*, which is the good direction.

| Token | Hex | Role |
|---|---|---|
| `flag-700` | `#8E2A21` | Pressed |
| `flag-600` | `#B4362B` | Under-par figures, LIVE, destructive actions (5.8:1 on sheet) |
| `flag-500` | `#C9483B` | Hover |
| `flag-100` | `#F6DFDC` | Destructive-confirm fill |

Red carries both "live/under par" and "destructive." Context separates them completely — nobody
mistakes a red `−4` in a score column for a delete button — and that is how a real scorecard
behaves.

### Brass — restricted mark

| Token | Hex | Role |
|---|---|---|
| `brass-700` | `#85601F` | Text on a brass fill |
| `brass-600` | `#A87A2C` | Multipliers above 1×, champion marks, caution states |
| `brass-500` | `#C2913D` | — |
| `brass-100` | `#F2E7CE` | Chip and notice fill |
| `brass-50` | `#FAF4E6` | Faintest notice tint |

Brass means **"this one is out of the ordinary"** — a 2× event, a champion, or a state that
needs the manager's attention (unpaid plan, unresolved draft). It is a mark, not a surface: it
never fills a page region, and a screen carrying brass in more than two or three places has
almost certainly stopped meaning anything by it.

### Never use

- Any gradient. `bg-gradient-*` does not appear in this codebase.
- Any hue outside these four ramps — no indigo, violet, purple, sky, teal, orange, amber, lime.
- Pure `#FFFFFF` page backgrounds or pure `#000000` text.
- Colored left-border strips as decoration.
- Neon glow — no colored `box-shadow`.

---

## 4. Space and shape

### Space

4px base, 8pt rhythm. Permitted values only: **4, 8, 12, 16, 24, 32, 48, 64, 96**. Arbitrary
values (`p-[13px]`, `mt-[37px]`) are a bug.

Proximity carries meaning, so the gaps are ordered: within a component `8–12` · between
components `16–24` · between sections `32–48` · page gutter `16` mobile / `24` desktop.

Section padding varies down a page on purpose. Identical padding on every section is what a
template looks like.

### Radius

The pairings sheet has square corners. The scale is tight and applied **by role**, never
uniformly — before this redesign the app had 532 `rounded-*` utilities across four buckets with
no scale behind them.

| Token | Value | Applies to |
|---|---|---|
| `rounded-none` | `0` | Full-bleed bands, table cells, the board, dividers |
| `rounded-xs` | `2px` | Buttons, inputs, chips, badges |
| `rounded-sm` | `3px` | Panels, sheets, modals |
| `rounded-full` | `50%` | **Circles only** — golfer headshots and avatars. Never a pill. |

`rounded-md`, `rounded-lg`, `rounded-xl`, `rounded-2xl` and `rounded-3xl` do not appear in the
codebase — the four names above are the whole scale.

### Rules

`1px solid ink-200`, drawn **horizontally** to separate rows and sections. This is the app's
signature separator. A rule divides; it does not enclose.

### Separation ladder

To separate two things, take the first rung that works and stop:

1. whitespace
2. the `page` → `sheet` background step
3. a horizontal rule
4. elevation
5. a full border — only for a genuinely enclosed object

---

## 5. Elevation

Three recipes. There is no fourth.

| Token | Value | Use |
|---|---|---|
| `shadow-none` | — | Default. Most surfaces are flat. |
| `shadow-sheet` | `0 1px 2px rgb(15 21 18 / 0.06)` | A sheet lying on the page |
| `shadow-raised` | `0 8px 24px -8px rgb(15 21 18 / 0.18)` | Modals, dropdowns, popovers only |

---

## 6. Components

**Button.** `rounded-xs`, `text-ui`, `py-2.5 px-4`, no shadow.
- Primary — `bg-fairway-700` / hover `bg-fairway-600` / active `bg-fairway-800` / white text
- Secondary — `bg-sheet`, `1px ink-200` border, hover `border-ink-400`
- Ghost — text only, hover `bg-ink-100`
- Destructive — `text-flag-600`, hover `bg-flag-100`
- Disabled — `opacity-40`, `cursor-not-allowed`
- Focus — `outline: 2px solid fairway-600; outline-offset: 2px`

**Panel.** `bg-sheet`, `rounded-sm`, `shadow-sheet`, no border. Section headings sit on a
bottom rule, not inside a nested box.

**Board band.** `bg-fairway-900`, square corners, white display type, `fairway-400` for meta
text. This replaces every former gradient header.

**Table.** No outer box. `text-micro` column headers over a bottom rule; rows separated by
`1px ink-200`; numeric columns right-aligned in `text-data`; the current user's row filled
`fairway-50` with a 2px `fairway-700` left marker (a genuine semantic state — the one permitted
left strip in the app).

**Chip.** `rounded-xs`, `text-micro`, `px-2 py-0.5`. Default is a hairline outline in ink;
filled variants only for LIVE (`flag-600`) and multiplier (`brass`).

**Input.** `bg-sheet`, `1px ink-200`, `rounded-xs`, `text-body`, ≥16px on mobile. Focus mirrors
the button focus ring. Error state gets `flag-600` border plus a message — never color alone.

**Empty state.** A rule, a plain sentence in `ink-500`, and one action. No illustration, no
centered icon in a rounded square.

### Required states

Every interactive element ships **hover, focus-visible, active, disabled**. Every data surface
ships **loading, empty, error**. Missing states are the highest-severity defect in this system —
they are what makes generated UI fall apart on contact with real data.

---

## 7. Layout

- Content column `max-w-5xl`; reading text `max-w-prose` (68ch).
- **Left-aligned by default.** Centering is reserved for a genuinely symmetric object — a
  confirmation, a single empty state.
- Mobile-first: everything works at 390×844 before desktop styles are added. `sm:` (640px)
  introduces desktop, it never rescues mobile.
- Tables hide low-priority columns below `sm`, never scroll horizontally.
- Numbers abbreviate (`1.6M`) in tight cells, full precision on detail views.

### Negative constraints

Explicit, because silence is where the defaults come back:

- **No gradients.** Anywhere.
- **No blurred decorative blobs** (`blur-2xl`/`blur-3xl` on positioned divs).
- **No centered hero** with a pill badge above the headline.
- **No three-up icon-card feature grid.**
- **No numbered `01 · 02 · 03` step row** with a connector line.
- **No uppercase letterspaced kicker above every heading** — one per page maximum.
- **No emoji in UI chrome.**
- **No `hover:scale-*`** on cards.
- **No dark mode.** Deliberately: this is a document you read in daylight, and a half-built dark
  mode is worse than none. Revisit as a real project, not a reflex.

---

## 8. Motion

Motion communicates state or directs attention. Nothing else moves.

- Durations: `120ms` for state (hover, focus), `180ms` for transitions (open, close).
- Easing: `cubic-bezier(0.2, 0, 0, 1)`.
- Animate `color`, `background-color`, `opacity`, `transform` only.
- No scroll-triggered reveals. No entrance animations on page load.
- All of it collapses to `0ms` under `prefers-reduced-motion: reduce`.

---

## 9. Copy

The voice is a league commissioner explaining the rules at the bar: specific, dry, assumes you
know golf.

Say the actual thing — "Picks close at the first tee shot Thursday," not "Seamlessly manage your
league." Use real numbers. Never write *reimagined*, *supercharge*, *effortlessly*, *unleash*,
*transform your*, *everything you need*, or *the modern way to*.

---

## Changelog

- **2026-08-14 — v1.0.** Adopted "Pairings Sheet". Replaced the emerald-gradient default:
  removed all 53 gradients and 22 blur blobs, collapsed 532 unscaled `rounded-*` utilities onto
  a four-step radius scale, reduced 10 colour families to 4 custom ramps, 5 shadow recipes to 3,
  and 121 uppercase kickers to `text-micro` used as a column header. Introduced Archivo /
  Spline Sans / Spline Sans Mono over the untouched framework default.
