# GEMINI.md: Instructions for Building the Interactive Report

This document contains step-by-step instructions for the **Antigravity AI Coding Assistant** to build a high-fidelity, premium, single-page interactive HTML report titled **'Singapore Property Market 2026'** using the data from `research.md`.

---

## 1. Technical Framework & Constraints

*   **Format:** A single-page, responsive dashboard (`index.html`).
*   **Styling:** Vanilla CSS, written in an external stylesheet (`styles.css`) or inlined in a `<style>` tag within the HTML for easy sharing. Do not use TailwindCSS.
*   **Interactivity & Logic:** Vanilla JavaScript (`app.js` or inlined `<script>`).
*   **Typography:** Google Fonts (e.g., `'Inter'`, sans-serif or `'Outfit'`, sans-serif) to ensure a premium, modern feel.
*   **Data Source:** Read all stats, medians, transaction counts, and trends from `research.md` (copying them exactly).
*   **Icons:** Use beautiful, lightweight SVG icons or Lucide CDN icons for stat cards and section headers.

---

## 2. Design System & Aesthetics (Premium "Wow" Guidelines)

*   **Theme:** Clean, modern, light background with a premium tech-business feel.
*   **Color Palette (Harmonious Blue Accents):**
    *   *Primary/Brand Blue:* `hsl(220, 90%, 56%)` (Deep Indigo Blue)
    *   *Accent/Cyan:* `hsl(190, 95%, 45%)` (Vibrant Cyan)
    *   *Neutral Dark:* `hsl(224, 25%, 12%)` (Rich slate/navy for text)
    *   *Neutral Light:* `hsl(210, 40%, 98%)` (Ultra-light grayish-blue for background)
    *   *Card Background:* `hsl(0, 0%, 100%)` (Pure white) with a subtle border `1px solid hsl(210, 30%, 90%)` and a smooth drop shadow `0 4px 20px -2px rgba(0, 0, 0, 0.05)`.
*   **Transitions & Micro-animations:**
    *   Use smooth transition timings: `transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);`.
    *   Add scale and lift translations to cards on hover (`transform: translateY(-4px);`).
    *   Incorporate HSL gradients (`linear-gradient(135deg, hsl(220, 90%, 56%) 0%, hsl(190, 95%, 45%) 100%)`) for primary highlights and buttons.

---

## 3. Page Structure & Components

### 3.1 Header & Hero Section
*   A premium, full-width header with an organic background grid or soft gradient bubble in the corner.
*   Include a prominent title: **"Singapore Property Market 2026"**.
*   Include a description: *An Interactive Visual Analysis of Public and Private Housing Trends (2025 – Q1 2026)*.
*   A clean metadata badge: `Dataset: Q1 2026 Official Releases (HDB & URA)`.

### 3.2 Summary & Narrative Grid
*   A two-column grid. Left column: Executive Summary explaining the "soft landing" and cooling measures. Right column: Summary of the cooling index change (-0.1% for HDB, +0.9% for URA private) highlighting the divergence trend.

### 3.3 Dashboard KPI Stat Cards (Interactive)
Create four distinct, beautifully styled stat cards:
1.  **HDB Overall Median Price (2025):** **S$628,000** (Subtitle: "Full-Year Benchmark")
2.  **HDB Price Index Shift (Q1 2026):** **-0.1%** (Subtitle: "First drop in 7 years", colored in soft red)
3.  **Million-Dollar Transactions (2025):** **1,594 flats** (Subtitle: "+54% Year-over-Year surge", colored in indigo gradient)
4.  **Private Property Index (Q1 2026):** **+0.9%** (Subtitle: "Continuous expansion", colored in soft green)

*Interactivity:* Clicking any card should open a clean slide-over modal or expand an accordion showing the underlying research source, transaction counts, or relevant context from `research.md`.

### 3.4 Visual Charts Section (3 Clean Charts)
Include Chart.js (via CDN: `https://cdn.jsdelivr.net/npm/chart.js`) to render three highly polished, interactive charts with custom blue/indigo/cyan styling:

1.  **Chart 1: HDB Resale Price Index Growth Trend (Bar/Line Combo)**
    *   *X-Axis:* 2024, 2025, Q1 2026
    *   *Data:* 2024 (9.7% annual growth), 2025 (2.9% annual growth), Q1 2026 (-0.1% quarterly decline).
    *   *Type:* Line or clean curved area chart, showing the plateau/soft landing.
2.  **Chart 2: HDB Median Price Premiums by Estate (Comparison Bar Chart)**
    *   *X-Axis:* Jurong West (3-Room), Woodlands (4-Room), Choa Chu Kang (4-Room), Bukit Merah (4-Room), Toa Payoh (4-Room), Queenstown (4-Room).
    *   *Data:* Jurong West (S$386,500), Woodlands (S$550,000), Choa Chu Kang (S$550,900), Bukit Merah (S$938,000), Toa Payoh (S$1,000,000), Queenstown (S$1,038,000).
    *   *Type:* Horizontal or vertical bar chart with a gradient fill.
3.  **Chart 3: Public vs. Private Property Index Divergence (Comparison Group)**
    *   *Categories:* HDB Resale Index, URA Private Index, OCR Private (Non-Landed) Index.
    *   *Data:* -0.1%, +0.9%, +2.2% (respectively).
    *   *Type:* Side-by-side bar chart showing the split between public contraction and private expansion in Q1 2026.

### 3.5 Interactive Estate Reference Tool
*   Provide a drop-down menu that lets the user select an estate (e.g., Queenstown, Toa Payoh, Bukit Merah, Sengkang, Jurong West).
*   Upon selection, dynamic JS should update a clean visual layout showing the median prices for **3-Room, 4-Room, and 5-Room flats** in that estate, based on the Q1 2026 data table in `research.md`.
*   Include a nice "Affordability Meter" or rating based on the pricing tier.

### 3.6 Sources & Footnote Footer
*   A beautifully formatted table or list detailing the sources mapping back to HDB Releases, URA Real Estate Statistics, and data.gov.sg compiled files.

---

## 4. Steps for Antigravity to Implement

1.  **Initialize Files:** Create the `index.html`, `styles.css`, and `app.js` inside the directory.
2.  **Incorporate Fonts:** Link Google Fonts (`Inter` or `Outfit`) in the HTML header.
3.  **Implement Layout:** Code the HTML structure with a header, multi-column grid, stat cards, chart containers, and the interactive estate reference dropdown.
4.  **Style with CSS:**
    *   Define custom variables (`--primary`, `--accent`, `--bg-light`, `--card-bg`, etc.) at the `:root` level.
    *   Construct a fully responsive grid system using CSS Grid and Flexbox.
    *   Implement standard hover effects, border radii (e.g., `12px` or `16px`), card shadows, and transition effects.
5.  **Chart JS Initialization:**
    *   Include the Chart.js script tag.
    *   Initialize the three charts in `app.js`. Use custom colors from our palette (`hsl(220, 90%, 56%)` and `hsl(190, 95%, 45%)`) with clean grid lines and custom tooltips.
6.  **Interactive Scripting:**
    *   Implement card expansion toggle logic.
    *   Implement the dropdown estate selector to dynamically render the corresponding HDB pricing details and mature/non-mature badges.
7.  **Quality Check:**
    *   Ensure all numbers correspond exactly to those listed in `research.md`.
    *   Verify mobile and tablet responsive layouts.
