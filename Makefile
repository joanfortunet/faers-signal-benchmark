.PHONY: help env-check lint test download load transform data

help:
	@echo "Available commands:"
	@echo "  make env-check  - print versions of the main libraries"
	@echo "  make lint       - check code style with ruff"
	@echo "  make test       - run the unit tests"
	@echo "  make download   - download FAERS quarterly files into data/raw"
	@echo "  make load       - load new quarters into data/faers_warehouse.duckdb"
	@echo "  make transform  - deduplicate and build the drug-event tables"
	@echo "  make data       - download + load + transform"

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

data: download load transform
