# Five-minute demo

Start with the README and its architecture diagram. Then run the checkout fixture.

```sh
python3 -m patchpilot demo
```

Open `report.html` from the printed output directory. Explain that this is a scripted fixture used to test the maintenance pipeline reliably without an API key.

Show the validation history. The original implementation converts a Decimal total to an integer and loses cents. The first edit switches to `round`, which still fails the midpoint case. The second edit uses `quantize` with explicit half-up rounding. All five tests then pass.

Open `patch.diff`. Only `cart.py` changes. Open `trace.jsonl` to show the file reads, plan, edits, failed observation, repair, and successful review request. Open `run.json` to show the measured timings and zero model usage for the scripted run.

Then show `tests/test_tools.py`. Point out the test for stale validation, the protected test path, the timeout case, and operation ID replay. These explain why the controller is more than a prompt around a shell command.

```sh
python3 -m unittest discover -s tests -v
python3 -m patchpilot eval
```

Close by explaining the live provider and publication boundary. The live adapter chooses its own tool calls. It needs an API key and has not been measured in the initial build. The publication command needs an explicit hash of the reviewed plan and creates a draft PR.

Do not show a scripted run as an autonomous model result. Do not call a local test run a Docker run. The report labels the provider and runner so the distinction is visible.
