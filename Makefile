.PHONY: help env-check lint

help:
	@echo "Available commands:"
	@echo "  make env-check  - print versions of the main libraries"
	@echo "  make lint       - check code style with ruff"

env-check:
	@python -c "import duckdb, pandas, sklearn, statsmodels; print('duckdb', duckdb.__version__, '| pandas', pandas.__version__, '| scikit-learn', sklearn.__version__, '| statsmodels', statsmodels.__version__)"

lint:
	@ruff check .
