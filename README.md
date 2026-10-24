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

- [ ] Phase 0: Setup
- [ ] Phase 1: Data engineering
- [ ] Phase 2: EDA and data quality
- [ ] Phase 3: Methods
- [ ] Phase 4: Evaluation
- [ ] Phase 5: Case studies and communication
- [ ] Phase 6: Polish

## Limitations

FAERS is a spontaneous reporting system: it cannot provide incidence rates or prove causality, and it is affected by reporting biases. Results should be read as signal detection, not as evidence of causal effects.

## License

MIT
