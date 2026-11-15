# FAERS Signal Detection Benchmark

> **Work in progress.** This README describes the project plan. Results will be added as each phase is completed.

Benchmark of classical, Bayesian and machine-learning methods for detecting drug safety signals in the FDA Adverse Event Reporting System (FAERS), validated against known drug label changes.

## Motivation

Pharmacovigilance relies on spontaneous reports to detect adverse drug reactions early. Many detection methods exist (disproportionality analysis, Bayesian shrinkage, machine learning), but they are rarely compared head to head against a clear ground truth, and even less often in terms of **how early** each one flags a signal.

## Research questions

1. Which method best detects known adverse drug reactions?
2. Which method detects them earliest, relative to the date of the drug label update?
3. How sensitive are the results to deduplication, thresholds and masking effects?

## Planned approach

- **Data:** FDA FAERS quarterly files (from 2014 Q3) and openFDA drug labels as ground truth.
- **Methods:** PRR, ROR, BCPNN and MGPS/EBGM (own implementations), penalized logistic regression and gradient boosting.
- **Evaluation:** AUC, average precision, precision@k, and time to detection using temporal validation.
- **Stack:** Python, DuckDB/SQL, scikit-learn, statsmodels, Quarto, Streamlit, pytest, GitHub Actions.

## Data

- **Source:** FDA Adverse Event Monitoring System (AEMS, formerly FAERS), quarterly data extract files in ASCII format.
- **Time window:** 2014 Q3 to 2026 Q2 (inclusive). Additional fields were introduced in 2014 Q3, so earlier files are not used.
- **Download date:** 2026-10-24
- **Note:** the files are raw and not cumulative. The same case can appear in several quarters, which is handled in the deduplication step.

## Data pipeline

Everything runs locally with DuckDB; no database server is needed.

| Step | Command | What it does |
|---|---|---|
| 1. Download | `make download` | Downloads and unzips the quarterly files into `data/raw/` (skips quarters already there). |
| 2. Load | `make load` | Loads every new quarter into `data/faers_warehouse.duckdb` as raw text tables, one transaction per quarter, logging loaded and rejected lines in `load_log`. |
| 3. Transform | `make transform` | Runs the SQL steps in `sql/`: deduplication, name normalisation and the drug-event contingency table. |

Main tables produced:

- `demo_dedup`: one row per case, keeping only its latest version (most recent `fda_dt`, then highest `primaryid`, as recommended by the FDA) and excluding cases the FDA has deleted.
- `drug_clean`, `reac_clean`, `outc_clean`: drugs, reactions (MedDRA preferred terms) and outcomes of the kept cases. Drug names use the active ingredient (`prod_ai`, or `drugname` if missing), in upper case, with biosimilar suffixes removed (`ADALIMUMAB-ADAZ` → `ADALIMUMAB`).
- `drug_event_counts`: the 2x2 table (`a`, `b`, `c`, `d`) for every primary-suspect drug and event pair, the common input of all disproportionality methods.

## Project structure

```
├── sql/          # SQL queries (schema, deduplication, contingency tables)
├── src/faers/    # Python package (ingestion, methods, evaluation)
├── tests/        # Unit tests
├── notebooks/    # Exploratory analysis and case studies
├── app/          # Interactive dashboard
├── reports/      # Quarto report
└── data/         # Local data (not tracked by Git)
```

## Roadmap

- [x] Phase 0: Setup
- [ ] Phase 1: Data engineering
  - [x] Download script
  - [x] Raw load into DuckDB
  - [x] Deduplication and contingency table
  - [ ] Full 2014 Q3 – 2026 Q2 window loaded and checked
- [ ] Phase 2: EDA and data quality
- [ ] Phase 3: Methods
- [ ] Phase 4: Evaluation
- [ ] Phase 5: Case studies and communication
- [ ] Phase 6: Polish

## Limitations

FAERS is a spontaneous reporting system: it cannot provide incidence rates or prove causality, and it is affected by reporting biases. Results should be read as signal detection, not as evidence of causal effects.

## License

MIT
