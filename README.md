# 🇬🇧 UK ILR Absence Calculator

A free, privacy-first Streamlit web app that helps UK visa holders track their absences and assess eligibility for **Indefinite Leave to Remain (ILR)** — before they apply.

All calculations happen in the browser session; no data is stored or transmitted.

---

## Features

- **180-day rolling window** — finds the worst 12-calendar-month period in your history, using the Home Office's calendar-month method (not a fixed 365 days).
- **Single-trip cap** — flags any trip longer than 6 months.
- **10-year total cap** — checks the 548-day cumulative limit for the Long Residence route.
- **PASS / CAUTION / FAIL verdict** with plain-English explanations for every breach and warning.
- **Key date calculator** — earliest ILR eligibility date and earliest application date (28 days before).
- **Interactive trip editor** — add, edit, and delete trips inline with a date-range picker.
- **CSV round-trip import/export** — save your trips and restore them in a future session.
- **Excel report export** — a multi-sheet workbook with a summary, trip list, yearly breakdown, and findings.
- **Charts** — stacked monthly bar chart, rolling-window gauge, and year-by-year bar chart.
- **FAQ section** — answers common questions about the 180-day rule, how travel days are counted, route differences, and more.

---

## Supported Routes

| Route | Qualifying Period | Rolling Limit | Total Cap |
|---|---|---|---|
| 5-Year (Skilled Worker, Spouse, Innovator, etc.) | 5 years | 180 days / 12 months | None |
| 10-Year Long Residence | 10 years | 180 days / 12 months | 548 days |

---

## Project Structure

```
src/ilr_absence/
├── app.py        # Entry point: page config, CSS injection, main()
├── config.py     # Constants: ROUTES, COUNTRIES, REASONS, CSS
├── engine.py     # ILRAbsenceEngine — all absence calculations
└── ui.py         # Streamlit UI: header, sidebar, trip editor, results, FAQ, footer
```

---

## Getting Started

### Prerequisites

- Python ≥ 3.14
- [Poetry](https://python-poetry.org/) for dependency management

### Installation

```bash
git clone https://github.com/your-username/ilr-absence.git
cd ilr-absence
poetry install
```

### Running locally

```bash
poetry run streamlit run src/ilr_absence/app.py
```

The app opens at `http://localhost:8501`.

---

## How It Works

### Absence counting

Both the **departure day and the return day** count as days outside the UK, which mirrors the Home Office's conservative counting approach.

### Rolling 12-month window

The engine samples candidate end-dates (trip boundaries ±7 days, monthly markers, and the planned ILR date) and for each evaluates the 12-calendar-month window ending on that date. The worst window found is reported.

```
window_start = end_date − 12 calendar months + 1 day
window_end   = end_date
absence_days = days in absence_set ∩ [window_start, window_end]
```

### Eligibility verdict

| Condition | Status |
|---|---|
| Any absence rule breached | **FAIL** |
| Warnings about approaching limits | **CAUTION** |
| No issues or substantive warnings | **PASS** |

A notice that the qualifying period is not yet complete does not by itself raise the status to CAUTION.

---

## Dependencies

| Package | Purpose |
|---|---|
| `streamlit` | Web app framework |
| `pandas` | Data manipulation and CSV/Excel I/O |
| `plotly` | Interactive charts |
| `python-dateutil` | Calendar-month arithmetic (`relativedelta`) |
| `pycountry` | ISO country list for the destination picker |
| `openpyxl` | Excel export engine |

---

## Disclaimer

This tool is for **informational purposes only** and does not constitute legal advice. Immigration rules change frequently. Always verify with the [official Home Office guidance](https://www.gov.uk/indefinite-leave-to-remain) and consult a qualified immigration adviser.
