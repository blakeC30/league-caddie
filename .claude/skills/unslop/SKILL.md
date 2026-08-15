---
name: unslop
description: Detect and remove "AI slop" from frontend code — the generic, nobody-decided-this look that LLMs default to (gradient heroes, uniform rounded-2xl cards, uppercase eyebrow labels everywhere, unbounded color families, decorative blur blobs, three-up feature grids). Use when asked to audit a UI for AI slop, redesign a page or app to feel intentional, establish or enforce a design language, or before writing any new UI in this repo. Also triggers on "generic UI", "looks AI-generated", "design system", "design language", "make this feel designed".
---

# Unslop

## What slop actually is

Slop is not ugliness. Slop is **the absence of a decision**. An LLM asked for "a modern page"
returns the median of its training data, and the median of the modern web is a purple-blue
gradient over three rounded cards under an Inter headline.

The diagnostic question for every visual property on screen is: **who decided this, and why?**
If the honest answer is "it's what the framework does by default" or "it looked fine," it's slop.
A purple gradient chosen for a grape-soda brand is not slop. A green gradient smeared across
every header band because green was mentioned once is.

This has a direct corollary: **you cannot unslop by deleting things alone.** Removing the
gradient leaves a hole. You have to first commit to a specific direction, write it down, and
then re-derive every surface from it. Skip the commitment step and you regress to a different
median.

---

## The four verbs

Pick the verb from what was asked. If unclear, `audit` first — it is read-only and cheap.

| Verb | Use when | Output |
|---|---|---|
| `audit` | "does this look AI-generated?", "review the UI" | Findings list + slop score. **No edits.** |
| `adopt` | "create a design language", "set up a design system" | `DESIGN.md` + token layer. No page edits. |
| `redesign` | "revamp the UI", "fix this page" | Requires a `DESIGN.md`. Rewrites surfaces against it. |
| `build` | "add a new page/component" | Requires a `DESIGN.md`. New UI derived from tokens only. |

`redesign` and `build` **hard-depend** on `adopt` having happened. If there is no `DESIGN.md`
at the frontend root, run `adopt` first and get the direction confirmed before touching pages.
Redesigning without a written language is how you produce a second, differently-flavored slop.

---

## audit

### Step 1 — mechanical census

Run these from the frontend source root. Raw counts matter more than any single hit; slop is a
statistical property of a codebase.

```bash
# Gradient count. Any number above ~2 (a deliberate accent) is a finding.
grep -ro "bg-gradient-to-[a-z]*" --include='*.tsx' --include='*.jsx' --include='*.vue' . | wc -l

# Radius scale. If several buckets are all in the hundreds, there is no scale — just habit.
for r in none sm md lg xl 2xl 3xl full; do
  printf "rounded-%-5s %s\n" "$r" "$(grep -ro "rounded-$r\b" --include='*.tsx' . | wc -l)"
done

# Color families in play. More than ~4 (brand + neutral + 2 semantic) means no palette.
grep -rhoE "\b(bg|text|border|ring|from|via|to|shadow|divide|fill|stroke)-(gray|slate|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-[0-9]{2,3}" \
  --include='*.tsx' . | sed -E 's/^[a-z]+-//; s/-[0-9]+$//' | sort | uniq -c | sort -rn

# Elevation scale. More than 3 recipes on core surfaces is a finding.
grep -rhoE "shadow-(sm|md|lg|xl|2xl|inner)" --include='*.tsx' . | sort | uniq -c | sort -rn

# Decorative blur blobs — pure ornament, near-certain slop.
grep -rn "blur-3xl\|blur-2xl" --include='*.tsx' . | wc -l

# Eyebrow labels. One or two per app is a device; 100+ is a tic.
grep -rc "uppercase tracking" --include='*.tsx' . | grep -v ':0$'

# Font decision. Zero hits = the framework default was never overridden = no decision.
grep -rn "fontFamily\|font-family\|--font-\|@fontsource\|next/font" --include='*.css' --include='*.ts' --include='*.tsx' . | head
```

### Step 2 — the tell table

Check each. Severity is how strongly the tell signals "no human chose this," from the
frequency data in the sources below — not how ugly it is.

| # | Tell | Code signature | Sev |
|---|---|---|---|
| 1 | **Unthemed framework defaults** | `bg-slate-*`/`bg-zinc-*`/`bg-gray-*` on cards; shadcn `components.json` still `baseColor: slate`; the stock trio `rounded-lg border bg-card shadow-sm` | High |
| 2 | **AI purple** | `indigo-*`, `violet-*`, `purple-*` as primary/CTA; `#6366f1`, `#7c3aed`, `#8b5cf6`; `--primary` at HSL hue 255–280 | High |
| 3 | **Gradients everywhere** | `bg-gradient-to-*` on more than one surface; `from-purple-* to-blue-*`; gradient text via `bg-clip-text text-transparent` | High |
| 4 | **The tasteful default** | cream `#faf8f5`/`#f5f1e8`/`bg-stone-50` + Instrument Serif/Fraunces/Playfair + sage or emerald 700–900. The 2026 median. Reads "designed" at a glance and identical to a thousand other pages on the second glance | High |
| 5 | **Uniform rounding** | `rounded-2xl` on every card *and* `rounded-xl` on every button *and* `rounded-full` on every pill, with no stated scale | Med |
| 6 | **No type decision** | Tailwind `font-sans` untouched; or Inter/Geist/Roboto/Poppins/Space Grotesk with no second face | Med |
| 7 | **Centered hero + 3 cards** | `text-center` hero, badge pill above an `text-5xl/6xl` H1, two CTAs, then `grid md:grid-cols-3` of icon cards | Med |
| 8 | **Animation spam** | identical `fade-up` on every section; `hover:scale-105` on every card; `whileInView` everywhere | Med |
| 9 | **Unprompted neon glow** | `shadow-[0_0_*]` with a color; `text-cyan-400`/`text-fuchsia-400` on `bg-slate-950` | Med |
| 10 | **Emoji as icons** | emoji inside `<h1>`–`<h3>`, feature titles, or list bullets (🚀 ✨ ⚡ 🔥 💡) | Low |
| 11 | **Semantic color sprawl** | amber, blue, and purple pills side by side because each new state grabbed a fresh hue | Med |
| 12 | **Missing states** | no designed focus ring, disabled, loading, empty, or error state; hover declared but visually inert | High |
| 13 | **Weightless copy** | "reimagined", "Everything you need", "Transform your…", "Supercharge", "seamlessly", "Up and running in minutes" | Med |
| 14 | **Box-in-box** | a bordered card containing bordered cards containing bordered rows — separation applied reflexively rather than hierarchically | Med |

### Step 3 — report

Emit one line per finding:

```
FILE:LINE | TELL | SEV | signature | fix
```

Then a **slop score**: `Low` / `Medium` / `High`, justified by the census numbers, not vibes.

**Do not flag a deliberate decision.** If `DESIGN.md` says "purple, sampled from the brand mark"
then purple is not a finding. A tell is an *unspecified default*, never a banned value.

---

## adopt

Produce `DESIGN.md` at the frontend root. It is the single authority; every later change cites it.

### Make four decisions before writing any token

1. **Reference.** One real anchor — a physical object, a place, a printed artifact, a named
   direction (editorial, brutalist, utilitarian-dense, technical-mono, warm-consumer). It must be
   specific enough that two designers given it would produce recognizably related work.
   "Modern and clean" is not a reference; it is the absence of one.
2. **Color.** Sample from the reference or the real brand. Build a **custom neutral ramp** —
   stock `gray`/`slate`/`zinc` is itself a tell. Cap at three hues: dominant ≈60%, neutral ≈30%,
   sharp accent ≈10%. Extend by tint and shade only, never by adding a hue. Semantic
   (success/warn/error) lives outside the brand hues.
3. **Type.** A display face and a text face, each with a stated reason. Avoid both the no-choice
   defaults (Inter, Geist, Roboto) and the tasteful-choice defaults (Instrument Serif, Fraunces,
   Playfair). Body ≥16px. Measure 60–80 characters. One modular scale.
4. **Layout intent.** What is each surface *for*, and what should the user do first? Structure
   follows the answer, not a template.

### Required sections of DESIGN.md

Typography · Color (every token with its role and a "never use" list) · Space & shape (8pt grid,
explicit radius scale) · Elevation (3–5 named levels, no ad-hoc shadows) · Component conventions
· Layout rules **including explicit negative constraints** · Motion · Personality (3–5 adjectives
plus anti-examples) · Changelog.

Be numeric. `#0E1A16` not "deep green"; `4px` not "slightly rounded". **Silence in the design
system is where the defaults come back.**

Then implement the tokens in code — CSS custom properties or a Tailwind `@theme` block — so the
document and the codebase cannot drift.

---

## redesign / build

### Order of operations

Structure → type → color → elevation → motion. Never start with color; color applied to a
template that was never questioned just repaints the slop.

### Separation ladder

To visually separate two things, take the **first** rung that works and stop:

1. whitespace
2. a 3–5% background lightness shift
3. a hairline rule
4. elevation
5. a border — and never a flat neutral 1px box out of habit

Colored left-border strips are reserved for genuine semantic state. As decoration they are the
single most reliable AI tell.

### Non-negotiables

- Every value comes from a token. An arbitrary value (`p-[13px]`, `#3a7d5f`) is a bug unless
  `DESIGN.md` gained a token for it in the same change.
- Every interactive element ships **hover, focus-visible, active, disabled** — plus **loading,
  empty, error** where the component can be in those states. This is the highest-severity tell
  and the one most often skipped.
- Motion only communicates state or directs attention. It honors `prefers-reduced-motion`.
  If everything animates the same way, delete the animation.
- Vary section rhythm down a page. Identical padding on every section reads as a template.
- Show the real product over abstract icon-cards. Specificity is the thing a statistical model
  cannot fake, and therefore the thing that most reads as human.
- Copy gets rewritten too. A beautiful layout wrapped around "Everything you need to
  supercharge your workflow" is still slop.

### Pre-ship gate

Ship only when all of these hold:

- [ ] One committed direction; tokens hold across every screen
- [ ] ≤3 active hues; one focal point per screen
- [ ] Display + text pairing declared; body ≥16px
- [ ] Radius scale is explicit and applied by role, not uniformly
- [ ] ≤3 elevation recipes on core surfaces
- [ ] Spacing on the grid; no arbitrary one-off values
- [ ] Contrast measured, not eyeballed, on every text/background pair
- [ ] All interactive states designed, including focus-visible
- [ ] Real content at real lengths — long names, empty lists, huge numbers — doesn't break layout
- [ ] Tested at 390×844 and at desktop width
- [ ] Dark mode is a decision, either way
- [ ] Nothing on screen is there only because it was the default

### Regression is the normal case

Defaults reassert themselves on every new page. Unslop is not a one-time fix — it is why
`DESIGN.md` exists and why `build` reads it before writing a line.

---

## References

- `references/design-language.md` — this repo's committed direction (also at `frontend/DESIGN.md`)
- `references/sources.md` — the research this skill is derived from
