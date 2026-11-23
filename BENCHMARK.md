# Benchmark

Measured with `python scripts/benchmark.py` on a Windows 11 desktop (Ryzen 5 7600X), Python 3.11.15.
Medians over repeated runs. The 100 comp case reuses the five sample comps with new ids.
The PDF step includes launching Edge through Playwright each time, five runs.
Numbers vary by machine. Rerun the script to get yours.

| Step | Median ms | Max ms |
|---|---|---|
| validate, sample (5 comps) | 0.2 | 0.4 |
| render HTML, sample (5 comps, 2 photos) | 22.6 | 72.8 |
| validate, 100 comps | 1.5 | 19.8 |
| render HTML, 100 comps | 28.5 | 33.5 |
| render PDF, sample (browser launch included) | 1256.3 | 1474.7 |

Sample HTML size: 21 KB. Sample PDF size: 109 KB.

What this says: validation and HTML are effectively instant. A PDF takes about a second and a
quarter, nearly all of it browser startup.
