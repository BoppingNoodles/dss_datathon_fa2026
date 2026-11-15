# Phoenix: Person 4 pipeline (Places / Reviews / services / API / audits).
# SOURCE=real uses data/raw/ (see README "Raw data"); SOURCE=synthetic needs no downloads.
SOURCE ?= real
PY := uv run python

.PHONY: web requirements install synthetic places reviews index services person1 audits test api fixtures all clean-processed

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

person1: services
	$(PY) -m src.recommend.prepare_person1 --source $(SOURCE)

audits: person1
	$(PY) -m src.audit.data_audit --source $(SOURCE)
	$(PY) -m src.audit.service_ranking_audit --source $(SOURCE)
	$(PY) -m src.audit.worklists --source $(SOURCE)
	$(PY) -m src.audit.privacy_check --source $(SOURCE)

fixtures:
	$(MAKE) synthetic && $(MAKE) person1 SOURCE=synthetic && $(PY) -m src.audit.export_fixtures

test:
	uv run pytest -q

api:
	PHOENIX_SOURCE=$(SOURCE) uv run uvicorn backend.app.main:app --reload --port 8000

requirements:
	uv lock
	uv export --frozen --no-dev --no-hashes --no-emit-project -o requirements.txt -q
	uv export --frozen --only-group dev --no-hashes --no-emit-project -o requirements-dev.txt -q

web:
	cd frontend && npm install && npm run dev

all: services audits test

clean-processed:
	rm -rf data/processed/$(SOURCE)

# Teammate runtime handoff; these targets never rebuild the raw-data pipelines.
.PHONY: data-bundle data-install data-check
data-bundle:
	$(PY) -m src.data.runtime_bundle create

data-install:
	@test -n "$(BUNDLE)" || (echo 'Usage: make data-install BUNDLE=/path/to/phoenix-real-runtime-v1.tar.gz' && exit 1)
	$(PY) -m src.data.runtime_bundle install "$(BUNDLE)"

data-check:
	$(PY) -c 'import json; from src.recommend.data_readiness import readiness; print(json.dumps(readiness("$(SOURCE)"), indent=2))'
