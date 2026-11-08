# Replication package: Reading UML use case diagrams from images

Data and scripts for the evaluation of claude-opus-5-5, gpt-6-astra and gemini-3.1-pro-preview on 78 use case diagram images.

| Folder | Contents |
|---|---|
| `01_corpus/` | 78 images as downloaded, the same images flattened onto white (as sent to the models), `index.csv` with source URLs |
| `02_ground_truth/` | 78 consensus sheets, codebooks v1 and v2, empty annotation template |
| `03_prompts/` | prompt versions v0.1 to v0.5 and the frozen v1.0 (identical to v0.5), prompt design notes |
| `04_pilot/` | the six pilot diagrams and the pilot replies per prompt version |
| `05_main_run/` | 702 main-run replies (3 models × 3 runs × 78 diagrams), run logs, batch ids, raw batch files |
| `06_scripts/` | image preparation, model runs, batch runs, scoring, statistics, figures |
| `07_results/` | score and diff tables (strict and lenient), statistics, figures |

Reproduce the scores (Python 3, openpyxl):

    python3 -I 06_scripts/ucd_tools.py score 02_ground_truth/consensus 05_main_run/claude 07_results/scores/score_claude.csv
    python3 -I 06_scripts/paper_stats.py 02_ground_truth/consensus 05_main_run 07_results/stats
    python3 -I 06_scripts/make_figures.py 07_results/stats 07_results/figures

API keys are read only from the environment variables ANTHROPIC_API_KEY, OPENAI_API_KEY and GEMINI_API_KEY.

License: MIT for the scripts, CC BY 4.0 for everything else (see LICENSE). The diagram images remain the property of their sources (`01_corpus/index.csv`).
