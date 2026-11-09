# SurveyDoctor website — manual QA checklist

A click-through check of the website (BLUEPRINT §7.12, Stage 14). Run it once on a laptop-width window and once at phone width, before each release and after any big change. Tick each line, and write down anything that looks wrong in the log at the end.

**Phone width without a phone:** in Edge or Chrome press F12, then Ctrl+Shift+M (device toolbar), and choose a 375 px wide device (e.g. "iPhone SE"). Reload the page after switching.

## 0. Start

| Step | Expected |
|---|---|
| Start the API: in `backend/`, run `uvicorn api.main:app` (on this laptop, ask Claude to start it) | `http://localhost:8000/api/health` shows `{"status":"ok",…}` |
| Start the website: in `frontend/`, `npm run dev` | `http://localhost:5173` opens the landing page |

Test files:
- **Sample:** the "Try with sample data" button (bfi, 2,800 respondents).
- **Messy CSV:** `backend/tests/fixtures/google_forms_sample.csv`. It has text answers, a typo label ("Strongly agre"), personal columns, a blank row and missing answers.

## 1. Landing

- [ ] One sentence says what the tool does; two buttons: "Try with sample data" (filled) and "Upload your survey" (outlined).
- [ ] "What it checks", "Getting a CSV file from your form" (Google Forms and Microsoft Forms) and "Your data" are shown.
- [ ] The Google Forms and Microsoft Forms steps match what those websites show today. **[Not verified yet: please check once against the real menus.]**
- [ ] Press Tab once: a blue "Skip to content" button appears top left. Press Enter: focus jumps to the page content.

## 2. Upload (messy CSV)

- [ ] "Upload your survey" → drag the messy CSV onto the dashed box (or "Choose a file").
- [ ] Shows **12 responses**, **12 columns**, **7** rating questions, **2** personal columns left out.
- [ ] The note names "Email Address" and "Your name". Neither column, nor any email address, appears in the preview.
- [ ] Long headers show a short code above them (Q1, Q2, …).
- [ ] The preview table scrolls sideways inside its box. On a phone, the page itself does not scroll sideways.
- [ ] Primary button: "Check answer labels".

## 3. Answer labels

- [ ] "Recognised: agreement labels, 5 points"; a note that the answers also fit 7 points.
- [ ] "1 answer needs a number": "Strongly agre" is highlighted with the words "needs a number".
- [ ] "Confirm labels" without choosing a number → a red box: "Choose a number for “Strongly agre” …". Focus moves to it.
- [ ] Choose 5 → "Confirm labels" → the Scales screen opens.

## 4. Scales

- [ ] Q1–Q7 are ticked; Timestamp, Q8 (age) and Q9 (comments) are not. The answer range is 1–5 (from the labels).
- [ ] "Run checks" with no scale → "Create at least one scale and choose its questions."
- [ ] "Add a scale", name it "Teamwork", choose Teamwork for Q1–Q4, and tick "Reverse" for Q2. The scale shows "4 questions".
- [ ] Untick Q2: it leaves Teamwork ("3 questions"), and its Scale and Reverse controls are disabled. Tick it again and put it back in Teamwork, reverse-worded.
- [ ] "Download schema" saves `surveydoctor_schema.json`. "Load a schema file" with that file fills the screen in again.
- [ ] "Run checks": the message "Running checks on 12 respondents…" shows, then Results opens.

## 5. Results

- [ ] The verdict band is at the top: a status word with an icon, one sentence, and four chips (Careless responding, Reliability, Factor structure, Robustness), each with a word as well as a colour.
- [ ] Clicking a chip jumps to its section.
- [ ] Careless responding: rules table, histogram (hover a bar → tooltip), "Show as table" switches it to a table, and a sortable flag table with reasons. Clicking a column heading sorts it, and the arrow changes.
- [ ] Reliability, Factor structure (scree plot with dashed threshold line, loadings table), Sample size, Robustness ("Not checked yet"), Data checks, Limitations and Downloads are all present.
- [ ] Sample data: 2,800 respondents, 686 flagged by 1+ rule, 72 by 2+, Openness alpha below 0.70, E3, N4 and O4 marked "cross".

## 6. Robustness (sample data)

- [ ] Results → "Check robustness". "Run robustness check" with nothing chosen → "Choose the column that defines the groups."
- [ ] Choose Agreeableness, column `gender`, Group A 1, Group B 2 → run. The Result heading comes into view: "✓ No concern", a "Stable: …" sentence, and a table with 4 rows (all respondents, then 3 exclusion variants).
- [ ] "Correlate two scales" with Neuroticism and Extraversion also gives a table, with columns "Pearson r" and "Spearman's rho".
- [ ] "Back to results": the Robustness chip now says "No concern", and the Robustness section shows the sentence.
- [ ] Change anything on the Scales screen → the Results and Robustness steps become unavailable until "Run checks" is pressed again.

## 7. Downloads

- [ ] "Download report" → `surveydoctor_report_<file>.html` opens in a browser, shows the same verdict, and includes the robustness section if a check was run. Print preview (Ctrl+P) fits A4.
- [ ] "Download flags (CSV)" → opens in Excel with every respondent, and accents look right. With the messy CSV: **no email addresses or names** anywhere.
- [ ] "Download schema (JSON)" → the same file as on the Scales screen.

## 8. Errors and waiting

| Do this | Expected |
|---|---|
| Upload an Excel file (.xlsx) | "This looks like an Excel workbook, not a CSV file. …" |
| Upload an empty file (a new, empty text file renamed `.csv`) | "The file is empty. …" |
| Upload a file over 10 MB | "The file is larger than 10 MB. …", and the file is not sent |
| Stop the API (Ctrl+C), then click "Try with sample data" | After about 3 s: "Starting the analysis server — this can take up to a minute on the free plan." Restart the API within a minute → the sample loads by itself |
| Leave the API stopped for over 90 s | "Could not reach the analysis server. …" |
| Refresh the page on any step | Back to the landing page with nothing kept (the footer says so) |

## 9. Keyboard and accessibility

- [ ] Every step can be done with Tab, Shift+Tab, Enter, Space and the arrow keys alone, without a mouse.
- [ ] Every focused control has a visible blue outline.
- [ ] When an error appears, the screen reader or focus moves to it. When a screen changes, focus moves to its heading.
- [ ] Windows Settings → Accessibility → Visual effects → Animation effects **off** → the verdict band appears without fading in.
- [ ] Browser zoom at 200%: nothing overlaps, and the page does not scroll sideways (tables may scroll inside their box).

## Log

| Date | Who | Browser and width | Result / problems found |
|---|---|---|---|
| | | | |
