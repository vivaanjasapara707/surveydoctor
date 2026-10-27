# SurveyDoctor design plan

**Status: approved by the owner on 27 October 2026** (decisions in §10). Styling code follows this plan. The plan covers the HTML report (Stage 10) and the website (Stages 12–14). Both use the same palette, type and principles.

Written 27 October 2026 by Claude Code from the brief in BLUEPRINT §7.13. The frontend-design skill was not installed, so it was not used. All contrast ratios below were computed (WCAG 2.1 formula), and the chart colours were checked with a palette validator for colour-blind separation. None of them were estimated by eye.

---

## 1. Principles

1. **Verdict first, evidence second.** The top of every results view answers one question: can I trust this data, and where should I look? Everything below it is the evidence, in the order a careful reader checks it.
2. **An instrument, not a dashboard.** Quiet surfaces, thin rules and one accent colour. No gradients, shadows or decorative illustrations. Numbers are the content.
3. **Colour never works alone.** Every status has a word and an icon as well as a colour. Every chart series is also labelled by name.
4. **Say what was done and what it does not prove.** Caveats sit next to the result they qualify, in the same type size, not in a footnote.
5. **Plain, active words.** Buttons say what they do ("Run checks", "Download report"). Errors say what went wrong and how to fix it.

## 2. Palette

| Name | Hex | Role |
|---|---|---|
| Ink | `#18212B` | Main text, headings, numbers |
| Graphite | `#4A5562` | Secondary text, table headers, axis labels |
| Slate | `#67717C` | Muted text: captions, notes, timestamps |
| Paper | `#FFFFFF` | Page background, chart surface |
| Mist | `#F4F5F3` | Panels, table stripes, code blocks |
| Rule | `#D5D9DD` | Dividers and table lines (decorative, not text) |
| Field border | `#8A939C` | Input and button outlines (needs 3:1) |
| Signal | `#1F5F99` | The one accent: links, primary button, focus ring, chart series 1 |
| Copper | `#C2581F` | Chart series 2 only (e.g. the parallel-analysis threshold line) |
| Clear | `#1E6B35` on tint `#E6F2E9` | Status: no concern found by this check |
| Review | `#8A5300` on tint `#FBF0D9` | Status: look at this before drawing conclusions |
| Problem | `#A6261F` on tint `#FAE6E4` | Status: serious concern (only robustness "unstable", see §5) |

### Measured contrast (WCAG 2.1; AA needs 4.5:1 for text, 3:1 for UI parts)

| Pair | Ratio |
|---|---|
| Ink on Paper / on Mist | 16.26 / 14.87 |
| Graphite on Paper / on Mist | 7.59 / 6.94 |
| Slate on Paper / on Mist | 4.96 / 4.54 |
| Signal on Paper / on Mist | 6.66 / 6.09 |
| Paper text on Signal (primary button) | 6.66 |
| Clear on its tint / on Paper | 5.68 / 6.54 |
| Review on its tint / on Paper | 5.60 / 6.33 |
| Problem on its tint / on Paper | 6.00 / 7.20 |
| Field border on Paper (UI part) | 3.12 |
| Rule on Paper | 1.42 (decorative only; never the only boundary of a control) |

**Chart colours (Signal + Copper on Paper):** all validator checks pass. Simulated colour-blind separation is ΔE 19.6 (target ≥ 8), normal-vision separation is ΔE 28.1 (floor 15), and both colours are at least 3:1 against the page.

**Dark mode** is not planned for v1. The report must print, and one well-checked theme is better than two half-checked ones. The tokens are named so that a dark theme can be added later.

## 3. Typography

**Proposal A (recommended): IBM Plex Sans + IBM Plex Mono.** Plex was designed for technical documents. It reads as precise without being cold, and it is free under the SIL Open Font Licence.
- **Website:** fonts are self-hosted, with no requests to Google. This needs a small font package or the font files in the repo. That is a new dependency, so the owner must approve it (CLAUDE.md).
- **Report:** two weights of Plex Sans and one of Plex Mono are embedded as WOFF2, because the report must make no external requests. Measured in Stage 10: the three WOFF2 files are 176 KB (about 235 KB as base64), and the whole bfi report, with fonts and two charts, is 382 KB.

**Proposal B (no new dependency): system fonts.** `system-ui, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif` for text and `ui-monospace, "Cascadia Mono", Consolas, monospace` for code. The report stays small, but it looks slightly different on each operating system.

Either way:
- **Numbers in tables** use tabular figures (`font-variant-numeric: tabular-nums`) and are right-aligned, with the same number of decimals within a column.
- **Mono is only for** column codes (A1, Q12A), the schema JSON and file names. Statistics stay in the text face.
- **Scale** (ratio 1.25):

| Use | Website | Report (print) |
|---|---|---|
| Verdict headline | 31 px / 600 | 20 pt / 600 |
| Section heading | 25 px / 600 | 15 pt / 600 |
| Subheading | 20 px / 600 | 12 pt / 600 |
| Body | 16 px / 400, line height 1.5 | 10.5 pt / 400, line height 1.45 |
| Table, caption | 14 px / 400 | 9 pt / 400 |
| Small print | 12 px / 400 (Slate) | 8 pt / 400 |

## 4. Layout

### Report (A4, one column)

```text
┌──────────────────────────────────────────────┐
│ SurveyDoctor report · file name · date       │  Slate, small
│                                              │
│ ┌──────────────────────────────────────────┐ │
│ │ ⚠ REVIEW BEFORE DRAWING CONCLUSIONS      │ │  Verdict band (§5)
│ │ One sentence naming the checks to review │ │
│ │ ✓ Reliability ✓ Structure ⚠ Careless ... │ │  Check chips
│ └──────────────────────────────────────────┘ │
│                                              │
│ Summary: N, items, scales, flagged, ...      │  Key figures, 2 columns
│ ──────────────────────────────────────────── │
│ 2 Data checks                                │  Numbered sections,
│ 3 Careless responding  [histogram] [table]   │  same order as §7.9
│ 4 Reliability          [table]               │
│ 5 Factor structure     [scree] [loadings]    │
│ 6 Sample sensitivity   [3 rows]              │
│ 7 Robustness           [variant table]       │
│ 8 fsQCA (if requested)                       │
│ 9 Limitations                                │
│ 10 Methods and references                    │
│ ──────────────────────────────────────────── │
│ SurveyDoctor v… · generated … · No data was  │  Footer on every page
│ stored.                                      │
└──────────────────────────────────────────────┘
```

- **Width:** max 720 px on screen, centred. Print margins 18 mm, A4 portrait.
- **Page breaks:** sections start on a new line, never in the middle of a table row. A table can span pages, with its header row repeated.
- **Charts:** full column width, 2× resolution PNG, with alt text that states what the chart shows in numbers.
- **On a phone:** tables scroll sideways inside their own box; the page itself never does.

### Website (guided flow, BLUEPRINT §7.12)

```text
┌──────────────────────────────────────────────────────────┐
│ SurveyDoctor            1 Upload › 2 Labels › 3 Scales › │  Step bar
│                         4 Results › 5 Robustness         │
├──────────────────────────────────────────────────────────┤
│ ┌──────────────────────────────────────────────────────┐ │
│ │ Verdict band (same component as the report)          │ │
│ └──────────────────────────────────────────────────────┘ │
│ [Careless] [Reliability] [Structure] [Sample size]       │  Section tabs
│                                                          │  (anchor links on
│ Careless responding                                      │   a phone)
│ ┌──────────────┐  686 respondents flagged by at least    │
│ │ histogram    │  one rule; 72 by two or more.           │
│ └──────────────┘                                         │
│ ┌──────────────────────────────────────────────────────┐ │
│ │ Sortable flag table: ID · rules · reasons            │ │
│ └──────────────────────────────────────────────────────┘ │
│                         [Download report] [Flags CSV]    │
└──────────────────────────────────────────────────────────┘
```

(686 and 72 are the real bfi counts from Stage 3; they illustrate wording, not layout.)

- **Width:** max 1040 px. Below 640 px the step bar becomes "Step 3 of 5: Scales" and the section tabs become a list of anchor links.
- **One primary action per screen** (Signal button). Everything else is a secondary (outlined) button or a text link.

## 5. The verdict band (the memorable element)

A full-width panel at the top of the results and of the report:
- **Headline:** a large status word with its icon:
  - ✓ **No concerns found by these checks**
  - ⚠ **Review before drawing conclusions**
  - ✕ **Serious concern**
- **One sentence** naming the checks that need attention, generated by `text.py`.
- **A row of chips**, one per check, each with icon, word and colour: Careless responding, Reliability, Structure, Robustness. Sample size is always shown as information, never as a status.
- **Behaviour:** clicking a chip on the website jumps to its section. In the report, the chips are plain text.

**Proposed status rules (needs owner approval).** These rules are statistics logic, so they will be computed in the backend (`text.py` or the pipeline) and only displayed by the frontend. Thresholds are taken from the blueprint where it has them, and none are invented:

| Check | Clear | Review | Problem |
|---|---|---|---|
| Careless responding | Nobody flagged by 2 or more rules | At least one respondent flagged by 2 or more rules | Never; flags are heuristics |
| Reliability | Every scale α ≥ 0.70 (§7.10 "commonly treated as acceptable"), no reverse-item warnings | Any scale below 0.70, or a reverse-item warning | Never |
| Structure | KMO ≥ 0.60 and every scale has its own factor | KMO < 0.60, a scale sharing a factor, or the analysis was skipped | Never |
| Robustness | "stable" | "sensitive" | "unstable" |
| Overall | All checks clear | Any check on Review | Robustness "unstable" |

If no analysis is declared, Robustness shows "Not checked" in Slate with no status icon. The overall headline then never claims more than the checks that ran ("No concerns found by these checks").

## 6. Components and states

- **Buttons:**
  - Primary: Signal background with Paper text.
  - Secondary: Paper background, Field-border outline, Ink text.
  - Corner radius 4 px, minimum height 40 px (44 px on touch screens).
- **Focus:** 2 px Signal outline with a 2 px offset on everything that can be focused. It is never removed.
- **Tables:** Rule lines, Mist header row, numbers right-aligned in tabular figures, and the sort state shown as an arrow and in `aria-sort`.
  - Flagged and weak or cross-loading cells get a tint and a word or symbol ("weak", "cross"), never the tint alone.
- **Notes and warnings:** a left border of 3 px in the status colour, the status word in bold, then the plain-English message. The same component is used for API errors.
- **Loading:**
  - Text first: "Running checks on 2,800 respondents…" (the real N of the upload).
  - A thin progress bar with no spinner when steps are known.
  - The wake-up message from §7.12 after 3 s with no response.
- **Empty states:** one sentence saying what will appear and what to do ("Upload a CSV to start, or try the sample data").

## 7. Charts

Charts in the report use matplotlib. Charts on the website use Recharts (§3.2), with hover tooltips and a "Show as table" toggle. Both follow the same rules:
- **Composite-score histogram:** a single series in Signal, with thin bars and a 2 px gap between them. It has no legend, because the title names it. The caption says: "A relative ranking within this file, not a probability."
- **Scree plot:**
  - Observed eigenvalues: Signal, a 2 px line with 8 px dots.
  - Parallel-analysis threshold: Copper, a 2 px dashed line. The dashes are a second cue besides colour.
  - Both lines are labelled by name at their right end, and there is also a legend.
  - The suggested number of factors is marked with a thin Graphite vertical rule and a label.
- **Axes:** Graphite labels, light Rule gridlines on the y-axis only, and no chart borders. One y-axis per chart, always.
- **Not a chart:** the loadings matrix (a table with highlights), the variant table and the sensitivity results (both short tables).

## 8. Motion

At most one animation: the verdict band fades in (150 ms) when results first appear. It is switched off when the user's system asks for reduced motion. Nothing else moves.

## 9. Tokens (for Tailwind in Stage 12, and CSS variables in the report)

`ink`, `graphite`, `slate`, `paper`, `mist`, `rule`, `field`, `signal`, `copper`, `clear`, `clear-tint`, `review`, `review-tint`, `problem`, `problem-tint`. Font tokens: `sans`, `mono`. Spacing on a 4 px grid (4, 8, 12, 16, 24, 32, 48). Radius `sm` = 4 px. Components use tokens only, never raw hex.

## 10. Owner decisions (27 October 2026)

1. **Typeface:** Proposal A, IBM Plex. The owner approved the font files as a dependency.
2. **Verdict status rules** in §5: approved as written.
3. **Palette:** approved as written.
4. **Dark mode:** out of scope for v1, agreed.
