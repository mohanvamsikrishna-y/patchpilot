.PHONY: demo test eval check runner

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
