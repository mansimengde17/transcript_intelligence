PYTHON ?= python3
export PYTHONPATH := src

.PHONY: pipeline advanced eval test serve mcp all

pipeline:
	$(PYTHON) src/pipeline.py

advanced:
	$(PYTHON) -m ti.advanced_pipeline

eval:
	$(PYTHON) evals/run_evals.py

test:
	$(PYTHON) -m unittest discover -s tests -v

serve:
	uvicorn ti.api:app --app-dir src --host 0.0.0.0 --port 8080

mcp:
	$(PYTHON) -m ti.mcp_server

all: pipeline advanced eval test
