# Project: Singapore Property Market 2026 — Interactive Report

Build a **single-page interactive HTML report** titled **"Singapore Property Market 2026"**. All data must come from `research.md` in this directory — do not invent numbers, and do not pull additional figures from the web. If `research.md` does not contain a number you need, omit that element rather than fabricate.

## Deliverable

A single self-contained file: **`index.html`**.
- All CSS inline in a `<style>` tag (or a single `<link>` to one local `styles.css` if you prefer — your call, but keep it to at most two files total: `index.html` + optional `styles.css`).
- All JS inline in `<script>` tags.
- Chart library: load **Chart.js v4** from a CDN (`https://cdn.jsdelivr.net/npm/chart.js`). No build step, no npm, no bundler.
- Must open and render correctly by double-clicking the file (no local server required).

## Page structure (top to bottom)

1. **Header**
   - Title: "Singapore Property Market 2026"
   - Subtitle / tagline: short one-liner (e.g. "A mid-year snapshot of prices, sales, and rentals")
   - Small "Data as of Q1 2026 / April 2026" badge

2. **Executive summary**
   - One short paragraph (2–4 sentences) drawn from the summary in `research.md`.

3. **Stat cards grid**
   - 8 cards in a responsive grid (4 per row on desktop, 2 on tablet, 1 on mobile).
   - Each card: large value, short metric label, tiny period/source line.
   - Use the 8 "hero numbers" listed under "Stat Cards" in `research.md`. Use the exact values from the research file.

4. **Three charts** (each in its own labelled section with a 1–2 sentence caption):
   - **Chart 1 — Bar chart**: "Private price growth by region, Q1 2026" (OCR, RCR, CCR, Landed). Use the QoQ % values from research.md. Negative bar for Landed.
   - **Chart 2 — Line chart**: "HDB vs Private — Q1 2026 inflection". Plot at minimum the Q1 2026 QoQ point (HDB −0.1% vs Private +0.9%). If only one data point per series exists in research.md, render as a small grouped bar instead — do not invent historical points.
   - **Chart 3 — Doughnut or stacked bar**: "2026 new private home pipeline vs forecast take-up". Show launch pipeline (~8,800 private + ~2,300 EC = ~11,100) vs forecast sales range (8,000–10,000). Use the midpoint 9,000 for the take-up slice if a single number is needed.

5. **Narrative sections** (short — 2–4 sentences each, drawn from research.md):
   - Private market
   - HDB market
   - Rental & yield
   - Outlook

6. **Footer**
   - Source list — render the URL list from `research.md` as clickable links.
   - "Data as of Q1 2026 / April 2026" disclaimer.

## Design

- **Style**: clean, modern, editorial — feels like a McKinsey or CBRE report page, not a dashboard.
- **Background**: light (off-white, e.g. `#F8FAFC` or `#FFFFFF` page with `#F1F5F9` section bands).
- **Accent**: blue. Pick a single primary blue (e.g. `#1D4ED8` or `#2563EB`) and one lighter tint for hovers/borders. Avoid rainbow palettes — charts should use shades of blue + one neutral gray for contrast where needed.
- **Typography**: system sans stack (`-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif`). Big, confident headline; comfortable body line-height (1.6).
- **Cards**: subtle shadow or 1px border, generous padding, rounded corners (`border-radius: 12px`).
- **Charts**: white card background, no chart-junk, axis labels in muted gray, gridlines very light.
- **Spacing**: generous vertical rhythm between sections (at least 64px on desktop).
- **Responsive**: works down to ~375px width. Stat grid collapses gracefully; charts shrink to container width.

## Interactivity (keep it light and tasteful)

- Chart.js default tooltips on hover for all three charts.
- Stat cards: subtle hover state (slight lift + accent border).
- Smooth scroll on any in-page anchor links (if you add a nav — optional).
- No modal, no animations beyond hover/transition. No dark mode toggle unless trivially easy.

## Constraints

- **Do not invent data.** Every number on the page must trace to research.md.
- **No emojis** anywhere in the output.
- **No external fonts** (no Google Fonts) — system stack only, to keep the file truly self-contained.
- Chart.js from CDN is the only external dependency.
- Keep the total file under ~600 lines if possible. Readable > clever.

## Build steps

1. Read `research.md` end-to-end.
2. Create `index.html` (and optionally one `styles.css`).
3. Open it in a browser and verify all 3 charts render, all 8 stat cards show, and the layout works at desktop and mobile widths.
4. Report back with the file path(s) and a one-line summary.
