.PHONY: demo demo-live doctor test eval check runner format format-check agent-image

demo:
	python3 -m patchpilot demo

test:
	python3 -m unittest discover -s tests -v

eval:
	python3 -m patchpilot eval

check: test eval
	python3 -m compileall -q patchpilot tests

runner:
	docker build -f Dockerfile.runner -t patchpilot-runner:local .

demo-live:
	python3 -m patchpilot demo --provider codex --open

doctor:
	python3 -m patchpilot doctor

format:
	python3 -m black patchpilot tests

format-check:
	python3 -m black --check patchpilot tests

agent-image:
	docker build -f Dockerfile.agent -t patchpilot-agent:local .
