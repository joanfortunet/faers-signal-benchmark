.PHONY: help env-check lint test download load transform scores reference benchmark export app report data

help:
	@echo "Available commands:"
	@echo "  make env-check  - print versions of the main libraries"
	@echo "  make lint       - check code style with ruff"
	@echo "  make test       - run the unit tests"
	@echo "  make download   - download FAERS quarterly files into data/raw"
	@echo "  make load       - load new quarters into data/faers_warehouse.duckdb"
	@echo "  make transform  - deduplicate and build the drug-event tables"
	@echo "  make scores     - score every drug-event pair with PRR, ROR, BCPNN and EBGM"
	@echo "  make reference  - build the label-based reference set from openFDA"
	@echo "  make benchmark  - time-to-detection replay against label changes (SrLC)"
	@echo "  make export     - export compact data for the Streamlit app"
	@echo "  make app        - run the Streamlit signal explorer"
	@echo "  make report     - render the Quarto report to reports/report.html"
	@echo "  make data       - download + load + transform + scores"

env-check:
	@python -c "import duckdb, pandas, sklearn, statsmodels; print('duckdb', duckdb.__version__, '| pandas', pandas.__version__, '| scikit-learn', sklearn.__version__, '| statsmodels', statsmodels.__version__)"

lint:
	@ruff check .

test:
	@pytest -q

download:
	python -m faers.ingest

load:
	python -m faers.load

transform:
	python -m faers.transform

scores:
	python -m faers.scores

reference:
	python -m faers.reference

benchmark:
	python -m faers.benchmark

export:
	python -m faers.export

app:
	streamlit run app/app.py

report:
	quarto render reports/report.qmd

data: download load transform scores
