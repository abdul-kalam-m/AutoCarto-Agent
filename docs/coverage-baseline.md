# Coverage baseline — 2026-09-16

Measured before Phase 0 import/trace modules and the polygon migration were
implemented, against the existing working tree including the first web UI.
This is **statement/line coverage**, not branch coverage.

```powershell
python -m pip install -c constraints-ci.txt -e '.[web,dev,geo]' pytest-cov
python -m pytest --cov=autocarto --cov-report=term-missing --cov-report=json:.web-cache/coverage-baseline.json --cov-report=html:.web-cache/coverage-baseline --tb=short
```

Windows, Python 3.12.10, pytest-cov 7.1.0, coverage 7.16.1; local native wheel
pins were matplotlib 3.10.3 and pyproj 3.7.1 (see web setup instructions).

| Scope | Covered / statements | Coverage |
| --- | ---: | ---: |
| All `autocarto` | 2,607 / 2,970 | 87.78% |
| `execution/gates/` | 592 / 638 | 92.79% |
| `execution/sandbox.py` | 188 / 223 | 84.30% |

**316 passed, 30 skipped, 17 warnings; 228.17 seconds.** Skipped tests include
environment-dependent network/container/gVisor checks; this is not evidence
of a new container or gVisor run. Both scopes in operating-manual §13 exceed
its 80% threshold. The per-module measured summaries are retained in
[coverage-baseline.json](coverage-baseline.json). Detailed HTML and raw JSON
remain local under `.web-cache/`.
