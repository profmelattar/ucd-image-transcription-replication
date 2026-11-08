#!/usr/bin/env python3
"""Figures for the paper from the output of paper_stats.py.

  python3 -I make_figures.py STATS_DIR OUT_DIR

Writes fig_f1_ci, fig_error_concentration and fig_run_stability as PNG (600 dpi) and PDF.
Colours are from the Okabe-Ito palette; models are also told apart by marker shape and hatching,
so the figures remain readable in grayscale.
"""
import csv, json, os, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

TYPES = ["System boundary", "Actor", "Use case", "Abstract use case", "Include", "Extend",
         "Extension point", "Extend condition", "UC generalization", "Actor generalization",
         "Bidirectional association", "Directed association", "Note",
         "Other relationship", "Other dependency", "Other"]
LABEL = {"UC generalization": "Use case generalization"}
MODELS = ["Claude", "ChatGPT", "Gemini"]
COL = {"Claude": "#0072B2", "ChatGPT": "#E69F00", "Gemini": "#009E73"}
MARK = {"Claude": "o", "ChatGPT": "s", "Gemini": "^"}
FILL = {"Claude": "full", "ChatGPT": "none", "Gemini": "full"}
HATCH = {"Claude": "", "ChatGPT": "////", "Gemini": "...."}

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 7, "axes.linewidth": 0.6,
                     "xtick.major.width": 0.6, "ytick.major.width": 0.6, "pdf.fonttype": 42})


def save(fig, out, name):
    for ext in ("png", "pdf"):
        fig.savefig(os.path.join(out, f"{name}.{ext}"), dpi=600, bbox_inches="tight")
    plt.close(fig)


def fig_f1(S, out):
    pooled, boot = S["pooled"]["lenient"], S["bootstrap"]["lenient"]
    fig, ax = plt.subplots(figsize=(2.55, 4.1))
    off = {"Claude": -0.25, "ChatGPT": 0.0, "Gemini": 0.25}
    for m in MODELS:
        for i, t in enumerate(TYPES):
            f = pooled[m][t]["F1"]; ci = boot[m][t]
            if f is None: continue
            y = i + off[m]
            if ci: ax.plot([ci[0], ci[1]], [y, y], color=COL[m], lw=0.9, solid_capstyle="butt")
            ax.plot(f, y, MARK[m], ms=3.6, color=COL[m], mfc=COL[m] if FILL[m] == "full" else "white", mew=0.8)
    rare = set(S.get("rare_types", []))
    ax.set_yticks(range(len(TYPES))); ax.set_yticklabels([LABEL.get(t, t) + (" †" if t in rare else "") for t in TYPES])
    ax.invert_yaxis(); ax.set_xlim(0.0, 1.02); ax.set_xlabel("F1 (lenient matching), 95% bootstrap interval")
    for i in range(len(TYPES)):
        if i % 2 == 0: ax.axhspan(i - 0.5, i + 0.5, color="0.94", zorder=0, lw=0)
    ax.grid(axis="x", color="0.85", lw=0.4); ax.set_axisbelow(True)
    for s in ("top", "right"): ax.spines[s].set_visible(False)
    h = [plt.Line2D([], [], marker=MARK[m], ls="-", lw=0.9, ms=3.6, color=COL[m],
                    mfc=COL[m] if FILL[m] == "full" else "white", label=m) for m in MODELS]
    ax.legend(handles=h, loc="lower center", bbox_to_anchor=(0.45, 1.0), ncol=3, frameon=False, fontsize=6.5, handlelength=1.8)
    save(fig, out, "fig_f1_ci")


def fig_conc(stats_dir, S, out):
    rows = list(csv.DictReader(open(os.path.join(stats_dir, "per_diagram_errors.csv"), encoding="utf-8")))
    fig, axs = plt.subplots(3, 1, figsize=(3.45, 3.9), sharex=True, sharey=True)
    ymax = max(float(r["errors_mean_per_run"]) for r in rows)
    for ax, m in zip(axs, MODELS):
        v = sorted(((float(r["errors_mean_per_run"]), r["diagram"]) for r in rows if r["model"] == m), reverse=True)
        ax.bar(range(len(v)), [e for e, _ in v], width=0.8, color=COL[m], edgecolor="black", lw=0.3, hatch=HATCH[m])
        c = S["concentration"][m]
        ax.text(0.98, 0.92, f"{m}: {c['total_errors']} errors in 234 replies\n"
                            f"Top 5 diagrams ({', '.join(d for _, d in v[:5])}): {c['top5_share']:.0%}\n"
                            f"Error-free diagrams: {c['error_free']} of 78",
                transform=ax.transAxes, ha="right", va="top", fontsize=6)
        ax.set_ylim(0, ymax * 1.15); ax.set_ylabel("Errors per run")
        for s in ("top", "right"): ax.spines[s].set_visible(False)
    axs[-1].set_xlabel("Diagrams, sorted by errors per run (lenient matching)")
    axs[-1].set_xticks([0, 9, 19, 29, 39, 49, 59, 69, 77]); axs[-1].set_xticklabels(["1", "10", "20", "30", "40", "50", "60", "70", "78"])
    fig.align_ylabels(axs)
    save(fig, out, "fig_error_concentration")


def fig_runs(S, out):
    rr = S["run_to_run"]
    cats = [("all3", "Found in all three runs", "0.35", ""), ("one_or_two", "Found in one or two runs", "0.75", "////"),
            ("none", "Found in no run", "white", "")]
    fig, ax = plt.subplots(figsize=(3.2, 1.45))
    lo = min(rr[m]["total"]["all3"] / sum(rr[m]["total"].values()) for m in MODELS) * 100
    x0 = max(0, (lo // 5) * 5 - 5)
    for i, m in enumerate(MODELS):
        tot = rr[m]["total"]; n = sum(tot.values()); left = 0
        for k, lab, col, h in cats:
            w = tot[k] / n * 100
            ax.barh(i, w, left=left, color=col, edgecolor="black", lw=0.4, hatch=h, height=0.6)
            if k != "all3":
                ax.text(100.6 if k == "none" else left + w / 2, i, f"{tot[k]}", va="center",
                        ha="left" if k == "none" else "center", fontsize=6,
                        bbox=None if k == "none" else dict(boxstyle="square,pad=0.1", fc="white", ec="none"))
            else:
                ax.text(x0 + 0.4, i, f"{tot[k]} ({w:.1f}%)", va="center", ha="left", fontsize=6, color="white")
            left += w
    ax.set_yticks(range(3)); ax.set_yticklabels(MODELS); ax.invert_yaxis()
    ax.set_xlim(x0, 100); ax.set_xlabel("Ground-truth elements (%)")
    for s in ("top", "right"): ax.spines[s].set_visible(False)
    ax.legend(handles=[Patch(facecolor=c, edgecolor="black", hatch=h, lw=0.4, label=l) for _, l, c, h in cats],
              loc="lower center", bbox_to_anchor=(0.45, 1.0), ncol=3, frameon=False, fontsize=6, handlelength=1.4,
              columnspacing=0.8)
    save(fig, out, "fig_run_stability")


if __name__ == "__main__":
    sd, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    S = json.load(open(os.path.join(sd, "stats.json"), encoding="utf-8"))
    fig_f1(S, out); fig_conc(sd, S, out); fig_runs(S, out)
    print("figures written to", out)
