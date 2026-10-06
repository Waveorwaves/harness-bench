# Common commands. Everything here uses the fake agent; nothing calls a model.
PYTHON ?= python3

.PHONY: test demo demo-showcase clean-demo

test:
	$(PYTHON) -m unittest discover -s tests

# Fake agents of different skill on the five core tasks, then the report and HTML page.
demo: clean-demo
	$(PYTHON) -m harness_bench pin --suite suites/demo-mock.json --output runs/demo/pinned.json --sandbox local
	$(PYTHON) -m harness_bench plan --suite runs/demo/pinned.json --output runs/demo/plan.json
	$(PYTHON) -m harness_bench run --plan runs/demo/plan.json --sandbox local
	$(PYTHON) -m harness_bench report --plan runs/demo/plan.json \
		--results runs/$$($(PYTHON) -c "import json;print(json.load(open('runs/demo/plan.json'))['plan_id'][:16])")/results.jsonl \
		--html runs/demo/index.html

# Stored sample solutions to the two visual tasks, captured and paired for blind judging. Needs HB_BROWSER.
# This redraws the pairs each time, so picks from an earlier run of this target stop matching.
demo-showcase:
	rm -rf runs/demo-showcase
	$(PYTHON) -m harness_bench pin --suite suites/demo-showcase.json --output runs/demo-showcase/pinned.json --sandbox local
	$(PYTHON) -m harness_bench plan --suite runs/demo-showcase/pinned.json --output runs/demo-showcase/plan.json
	$(PYTHON) -m harness_bench run --plan runs/demo-showcase/plan.json --sandbox local
	$(PYTHON) -m harness_bench judge-prepare --plan runs/demo-showcase/plan.json --task sunset-sail --replace
	$(PYTHON) -m harness_bench judge-prepare --plan runs/demo-showcase/plan.json --task pirate-ship-3d --replace

clean-demo:
	rm -rf runs/demo
