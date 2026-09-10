"""Self-contained, escaped HTML reports with no remote assets or script execution."""
import html
import json
from pathlib import Path


def render(folder: Path, result: dict, events: list[dict], patch: str):
    esc = lambda value: html.escape(str(value))
    rows = []
    for event in events:
        detail = json.dumps(event.get("result", {}), indent=2)
        rows.append(f'<details><summary><span>{event["step"]:02}</span> {esc(event["tool"])}'
                    f'<b>{"OK" if event["result"].get("ok") else "ERROR"}</b></summary>'
                    f'<pre>{esc(detail)}</pre></details>')
    test_rows = "".join(f'<tr><td>{i + 1}</td><td>{"Passed" if t["success"] else "Failed"}</td>'
                        f'<td>{t["passed"]} / {t["total"]}</td><td>{t["duration_seconds"]}s</td></tr>'
                        for i, t in enumerate(result["test_runs"]))
    budget = result["budget"]
    page = f'''<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PatchPilot · {esc(result['run_id'])}</title>
<style>
:root{{color-scheme:dark;font-family:Inter,ui-sans-serif,system-ui,sans-serif;background:#101419;color:#e6edf3}}
*{{box-sizing:border-box}}body{{max-width:1120px;margin:auto;padding:42px 26px 80px}}header{{display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #303944;padding-bottom:22px}}
.brand{{font-size:22px;font-weight:750;letter-spacing:-.8px}}.brand i{{color:#92e4bd;font-style:normal}}.tag{{color:#92e4bd;border:1px solid #375d4e;padding:7px 12px;border-radius:24px;font-size:12px}}
.eyebrow{{color:#92e4bd;text-transform:uppercase;letter-spacing:2px;font-size:11px;margin-top:42px}}h1{{font-size:clamp(28px,4vw,46px);letter-spacing:-1.5px;line-height:1.15;max-width:800px;margin:14px 0}}p{{color:#aab7c4;line-height:1.7}}.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:32px 0}}.card{{padding:22px;background:#192129;border:1px solid #303944;border-radius:12px}}.card strong{{display:block;font-size:27px;margin-top:10px}}.label{{font-size:12px;color:#aab7c4}}section{{margin-top:34px}}h2{{font-size:20px}}pre{{font:12px/1.65 ui-monospace,monospace;white-space:pre-wrap;overflow-wrap:anywhere;background:#151c23;padding:20px;border-radius:9px;color:#c4d9c9}}table{{border-collapse:collapse;width:100%;text-align:left}}td,th{{padding:13px;border-bottom:1px solid #303944}}th{{color:#9eaebb;font-size:12px}}details{{border:1px solid #303944;border-radius:8px;margin:9px 0}}summary{{padding:15px;cursor:pointer;font-family:ui-monospace,monospace;font-size:13px}}summary span{{color:#82929f;margin-right:15px}}summary b{{float:right;color:#92e4bd;font-size:11px}}details pre{{margin:0;border-radius:0 0 8px 8px}}footer{{margin-top:40px;font-size:12px;color:#8393a2}}@media(max-width:650px){{.grid{{grid-template-columns:repeat(2,1fr)}}header{{gap:15px}}}}
</style>
<header><div class="brand"><i>▧</i> PatchPilot</div><div class="tag">{esc(result['status'].replace('_',' '))}</div></header>
<div class="eyebrow">Maintenance run / {esc(result['provider'])} provider</div>
<h1>{esc(result['issue'].splitlines()[0].lstrip('# '))}</h1>
<p>{esc(result.get('summary') or result.get('error') or 'Run stopped before review.')}</p>
<div class="grid"><div class="card"><span class="label">Tool steps</span><strong>{budget['steps']}</strong></div>
<div class="card"><span class="label">Test executions</span><strong>{len(result['test_runs'])}</strong></div>
<div class="card"><span class="label">Elapsed</span><strong>{result['duration_seconds']}s</strong></div>
<div class="card"><span class="label">Estimated model cost</span><strong>${budget['estimated_cost']:.4f}</strong></div></div>
<p>This is a {esc(result['provider'])} run. Scripted runs use predefined actions and measure pipeline behavior, not model capability. Publication requires a separate human approval.</p>
<section><h2>Implementation plan</h2><p>{esc(result['plan'])}</p></section>
<section><h2>Validation history</h2><table><thead><tr><th>Attempt</th><th>Outcome</th><th>Tests passed</th><th>Duration</th></tr></thead><tbody>{test_rows}</tbody></table></section>
<section><h2>Proposed patch</h2><pre>{esc(patch or 'No patch produced.')}</pre></section>
<section><h2>Tool trace</h2>{''.join(rows)}</section>
<footer>Run {esc(result['run_id'])} · Base {esc(result['base_commit'][:12])} · Patch SHA-256 {esc(result['patch_sha256'])}<br>Local artifacts are editable. Hashes detect accidental changes, not malicious tampering.</footer></html>'''
    (folder / "report.html").write_text(page)
