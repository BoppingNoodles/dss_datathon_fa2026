# Phoenix: Person 4 pipeline (Places / Reviews / services / API / audits).
# SOURCE=real uses data/raw/ (see README "Raw data"); SOURCE=synthetic needs no downloads.
SOURCE ?= real
PY := uv run python

.PHONY: install synthetic places reviews index services audits test api fixtures all clean-processed

install:
	uv sync --group dev --frozen

synthetic:
	$(PY) -m src.data.make_synthetic

places:
	$(PY) -m src.data.places --source $(SOURCE)

reviews: places
	$(PY) -m src.data.reviews --source $(SOURCE)

index: reviews
	$(PY) -m src.recommend.build_index --source $(SOURCE)

services: index
	$(PY) -m src.audit.coverage_report --source $(SOURCE)

audits: services
	$(PY) -m src.audit.data_audit --source $(SOURCE)
	$(PY) -m src.audit.service_ranking_audit --source $(SOURCE)
	$(PY) -m src.audit.worklists --source $(SOURCE)
	$(PY) -m src.audit.privacy_check --source $(SOURCE)

fixtures:
	$(MAKE) synthetic && $(MAKE) services SOURCE=synthetic && $(PY) -m src.audit.export_fixtures

test:
	uv run pytest -q

api:
	PHOENIX_SOURCE=$(SOURCE) uv run uvicorn backend.app.main:app --reload --port 8000

all: services audits test

clean-processed:
	rm -rf data/processed/$(SOURCE)
