#!/usr/bin/env python3
"""Statistics for the paper, computed from the main-run replies.

  python3 -I paper_stats.py GT_DIR BATCH_OUT OUT_DIR [B]

GT_DIR     folder with the 78 consensus ground-truth sheets
BATCH_OUT  folder written by batch_run.py: BATCH_OUT/<provider>/run<k>/Dnn.json
OUT_DIR    receives stats.json, per_diagram_errors.csv, element_runs.csv, diff_runs.txt
B          bootstrap resamples (default 10000)

Uses the matching of ucd_tools.py unchanged. Bootstrap: diagrams are resampled with
replacement (each diagram carries its three runs), F1 is recomputed from the pooled counts,
and the 2.5th and 97.5th percentiles form the 95% interval (percentile method).
"""
import csv, json, os, random, sys, glob, re
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ucd_tools import TYPES, FUZZY, keyset, reply_to_rows, load_gt, overlap  # noqa: E402
import difflib

MODELS = [("claude", "Claude"), ("openai", "ChatGPT"), ("gemini", "Gemini")]
PILOT = {"D03", "D12", "D27", "D38", "D48", "D61"}


def same(p, k, fuzzy, lenient):
    return p == k or (fuzzy and overlap(p[0], k[0]) >= 0.6) or (
        lenient and len(p) == len(k) and all(a == b or difflib.SequenceMatcher(None, a, b).ratio() >= 0.9
                                             for a, b in zip(p, k)))


def match_flags(gt, pr, fuzzy, lenient):
    """Same greedy one-to-one matching as ucd_tools.match; returns (hit flag per gt item, unmatched preds)."""
    pr = list(pr); flags = []
    for k in gt:
        hit = next((i for i, p in enumerate(pr) if same(p, k, fuzzy, lenient)), None)
        flags.append(hit is not None)
        if hit is not None:
            pr.pop(hit)
    return flags, pr


def prf(tp, ng, npd):
    p = tp / npd if npd else None; r = tp / ng if ng else None
    if ng == 0 and npd == 0:
        return None, None, None
    f = 2 * tp / (ng + npd)
    return p, r, f


def main(gt_dir, bo, out, B=10000):
    os.makedirs(out, exist_ok=True)
    gt = load_gt(gt_dir)
    dids = sorted(gt)
    # counts[mode][model][did][type] = [tp, ng, npd] summed over runs
    counts = {m: {mod: {d: {t: [0, 0, 0] for t in TYPES} for d in dids} for mod, _ in MODELS} for m in ("strict", "lenient")}
    elem = defaultdict(lambda: defaultdict(int))  # (model, did, type, idx, key) -> runs found (lenient)
    diffs = defaultdict(set)  # (model, did, type, kind, key) -> runs
    nruns = defaultdict(int)
    for mod, _ in MODELS:
        for run in (1, 2, 3):
            for did in dids:
                f = os.path.join(bo, mod, f"run{run}", did + ".json")
                if not os.path.exists(f):
                    print("missing", f); continue
                nruns[mod] += 1
                d = json.load(open(f, encoding="utf-8"))
                for mode in ("strict", "lenient"):
                    len_ = mode == "lenient"
                    g = keyset(gt[did], len_, "gt"); pr = keyset(reply_to_rows(d), len_, "pred")
                    for t in TYPES:
                        flags, extra = match_flags(g[t], pr[t], t in FUZZY, len_)
                        c = counts[mode][mod][did][t]
                        c[0] += sum(flags); c[1] += len(g[t]); c[2] += len(pr[t])
                        if len_:
                            for i, (k, h) in enumerate(zip(g[t], flags)):
                                elem[(mod, did, t, i, " | ".join(k))][run] += int(h)
                                if not h:
                                    diffs[(mod, did, t, "MISSING", " | ".join(k))].add(run)
                            for k in extra:
                                diffs[(mod, did, t, "EXTRA", " | ".join(k))].add(run)
                        elif t == "System boundary" and len(pr[t]) > len(g[t]):
                            diffs[(mod, did, t, "STRICT EXTRA BOUNDARY", str(len(pr[t])))].add(run)

    def pooled(mode, mod, ds):
        tot = {t: [0, 0, 0] for t in TYPES}
        for d in ds:
            for t in TYPES:
                for j in range(3):
                    tot[t][j] += counts[mode][mod][d][t][j]
        return tot

    def summary(tot):
        res = {}
        for t in TYPES:
            p, r, f = prf(*tot[t]); res[t] = dict(tp=tot[t][0], n_gt=tot[t][1], n_pred=tot[t][2], P=p, R=r, F1=f)
        fs = [res[t]["F1"] for t in TYPES if res[t]["F1"] is not None]
        tp = sum(v[0] for v in tot.values()); ng = sum(v[1] for v in tot.values()); npd = sum(v[2] for v in tot.values())
        res["_mean_F1"] = sum(fs) / len(fs); res["_micro"] = dict(zip(("P", "R", "F1"), prf(tp, ng, npd)))
        res["_errors"] = (ng - tp) + (npd - tp)
        return res

    present = {t: sum(1 for d in dids if any(k != ("no",) for k in keyset(gt[d], True, "gt")[t])) for t in TYPES}
    S = {"diagrams_with_type": present, "rare_types": [t for t in TYPES if present[t] < 5], "runs_found": dict(nruns), "pooled": {}, "without_pilot": {}, "bootstrap": {}, "paired_diff": {}}
    rest = [d for d in dids if d not in PILOT]
    for mode in ("strict", "lenient"):
        S["pooled"][mode] = {name: summary(pooled(mode, mod, dids)) for mod, name in MODELS}
        S["without_pilot"][mode] = {name: summary(pooled(mode, mod, rest)) for mod, name in MODELS}

    # bootstrap over diagrams (lenient and strict), with paired differences in micro-F1 and mean F1
    rng = random.Random(20261107)
    for mode in ("lenient", "strict"):
        samples = {name: {t: [] for t in TYPES + ["_mean_F1", "_micro_F1"]} for _, name in MODELS}
        for _ in range(B):
            ds = [rng.choice(dids) for _ in dids]
            for mod, name in MODELS:
                tot = {t: [0, 0, 0] for t in TYPES}
                for d in ds:
                    c = counts[mode][mod][d]
                    for t in TYPES:
                        x = c[t]; y = tot[t]; y[0] += x[0]; y[1] += x[1]; y[2] += x[2]
                fs = []
                for t in TYPES:
                    f = prf(*tot[t])[2]
                    samples[name][t].append(f)
                    if f is not None: fs.append(f)
                samples[name]["_mean_F1"].append(sum(fs) / len(fs))
                tp = sum(v[0] for v in tot.values()); ng = sum(v[1] for v in tot.values()); npd = sum(v[2] for v in tot.values())
                samples[name]["_micro_F1"].append(2 * tp / (ng + npd))

        def ci(v):
            v = sorted(x for x in v if x is not None)
            if not v: return None
            return [v[int(0.025 * (len(v) - 1))], v[int(0.975 * (len(v) - 1))], len(v)]
        S["bootstrap"][mode] = {name: {t: ci(samples[name][t]) for t in samples[name]} for _, name in MODELS}
        pd = {}
        names = [n for _, n in MODELS]
        for i in range(3):
            for j in range(i + 1, 3):
                for key in ("_micro_F1", "_mean_F1"):
                    dv = [a - b for a, b in zip(samples[names[i]][key], samples[names[j]][key])]
                    pd[f"{names[i]}-{names[j]}{key}"] = ci(dv)
        S["paired_diff"][mode] = pd

    # paired permutation tests (sign flip per diagram) on micro- and macro-F1 differences, Holm-corrected
    def stat(mode, mod_counts):
        tot = {t: [0, 0, 0] for t in TYPES}
        for c in mod_counts:
            for t in TYPES:
                x = c[t]; y = tot[t]; y[0] += x[0]; y[1] += x[1]; y[2] += x[2]
        fs = [prf(*tot[t])[2] for t in TYPES]; fs = [f for f in fs if f is not None]
        tp = sum(v[0] for v in tot.values()); ng = sum(v[1] for v in tot.values()); npd = sum(v[2] for v in tot.values())
        return 2 * tp / (ng + npd), sum(fs) / len(fs)
    S["permutation"] = {}
    names = dict(MODELS)
    for mode in ("lenient", "strict"):
        res = {}
        for a, b in (("claude", "openai"), ("claude", "gemini"), ("openai", "gemini")):
            A = [counts[mode][a][d] for d in dids]; Bc = [counts[mode][b][d] for d in dids]
            oa, ob = stat(mode, A), stat(mode, Bc)
            obs = [oa[0] - ob[0], oa[1] - ob[1]]
            ge = [0, 0]; N = B
            for _ in range(N):
                xa, xb = [], []
                for u, v in zip(A, Bc):
                    if rng.random() < 0.5: u, v = v, u
                    xa.append(u); xb.append(v)
                sa, sb = stat(mode, xa), stat(mode, xb)
                for k in (0, 1):
                    if abs(sa[k] - sb[k]) >= abs(obs[k]) - 1e-12: ge[k] += 1
            res[f"{names[a]} vs {names[b]}"] = {"micro_diff": obs[0], "macro_diff": obs[1],
                                                 "p_micro": (ge[0] + 1) / (N + 1), "p_macro": (ge[1] + 1) / (N + 1)}
        for key in ("p_micro", "p_macro"):  # Holm over the three pairs
            items = sorted(res.items(), key=lambda kv: kv[1][key]); m = len(items); prev = 0
            for i, (k, v) in enumerate(items):
                adj = min(1.0, max(prev, (m - i) * v[key])); v[key + "_holm"] = adj; prev = adj
        S["permutation"][mode] = res

    # Spearman correlation between diagram size (ground-truth elements) and errors per diagram (lenient)
    def ranks(v):
        o = sorted(range(len(v)), key=lambda i: v[i]); r = [0.0] * len(v); i = 0
        while i < len(o):
            j = i
            while j + 1 < len(o) and v[o[j + 1]] == v[o[i]]: j += 1
            for k in range(i, j + 1): r[o[k]] = (i + j) / 2 + 1
            i = j + 1
        return r

    def pearson(x, y):
        n = len(x); mx = sum(x) / n; my = sum(y) / n
        sxy = sum((a - mx) * (b - my) for a, b in zip(x, y)); sx = sum((a - mx) ** 2 for a in x) ** .5; sy = sum((b - my) ** 2 for b in y) ** .5
        return sxy / (sx * sy) if sx and sy else 0.0
    S["spearman"] = {}
    size = [sum(counts["lenient"]["claude"][d][t][1] for t in TYPES) / 3 for d in dids]
    for mod, name in MODELS:
        err = [sum(counts["lenient"][mod][d][t][1] + counts["lenient"][mod][d][t][2] - 2 * counts["lenient"][mod][d][t][0] for t in TYPES) / 3 for d in dids]
        rx, ry = ranks(size), ranks(err); rho = pearson(rx, ry)
        ge = 0
        for _ in range(B):
            sh = ry[:]; rng.shuffle(sh)
            if abs(pearson(rx, sh)) >= abs(rho) - 1e-12: ge += 1
        S["spearman"][name] = {"rho": rho, "p": (ge + 1) / (B + 1), "n": len(dids)}

    # run-to-run agreement on ground-truth elements (lenient)
    rr = {}
    for mod, name in MODELS:
        c = {"all3": 0, "one_or_two": 0, "none": 0}; bytype = {t: {"all3": 0, "one_or_two": 0, "none": 0} for t in TYPES}
        for (m, did, t, i, k), runs in elem.items():
            if m != mod: continue
            n = sum(runs.values()); cat = "all3" if n == 3 else ("none" if n == 0 else "one_or_two")
            c[cat] += 1; bytype[t][cat] += 1
        rr[name] = {"total": c, "by_type": bytype}
    S["run_to_run"] = rr
    # extra (spurious) predictions: in how many runs does each recur
    ex = {}
    for mod, name in MODELS:
        c = {1: 0, 2: 0, 3: 0}
        for (m, did, t, kind, k), runs in diffs.items():
            if m == mod and kind == "EXTRA": c[len(runs)] += 1
        ex[name] = c
    S["extra_recurrence"] = ex
    # Fleiss' kappa over items = ground-truth elements and distinct spurious elements, rated present/absent by each run
    fk = {}
    for mod, name in MODELS:
        items = []
        for (m, did, t, i, k), runs in elem.items():
            if m == mod: items.append(sum(runs.values()))
        for (m, did, t, kind, k), runs in diffs.items():
            if m == mod and kind == "EXTRA": items.append(len(runs))
        n = 3; N = len(items)
        Pi = [(c * (c - 1) + (n - c) * (n - c - 1)) / (n * (n - 1)) for c in items]
        p1 = sum(items) / (N * n); pe = p1 ** 2 + (1 - p1) ** 2; pbar = sum(Pi) / N
        fk[name] = {"items": N, "unanimous_share": sum(1 for c in items if c in (0, 3)) / N, "P_obs": pbar, "P_exp": pe,
                    "kappa": (pbar - pe) / (1 - pe) if pe < 1 else None}
    S["fleiss"] = fk

    # per-diagram errors (lenient), mean per run
    with open(os.path.join(out, "per_diagram_errors.csv"), "w", newline="", encoding="utf-8") as fh:
        wr = csv.writer(fh); wr.writerow(["model", "diagram", "fn", "fp", "errors_mean_per_run", "n_gt"])
        conc = {}
        for mod, name in MODELS:
            errs = []
            for d in dids:
                fn = sum(counts["lenient"][mod][d][t][1] - counts["lenient"][mod][d][t][0] for t in TYPES)
                fp = sum(counts["lenient"][mod][d][t][2] - counts["lenient"][mod][d][t][0] for t in TYPES)
                ng = sum(counts["lenient"][mod][d][t][1] for t in TYPES) // 3
                wr.writerow([name, d, fn, fp, round((fn + fp) / 3, 3), ng]); errs.append((fn + fp, d))
            errs.sort(reverse=True); tot = sum(e for e, _ in errs)
            conc[name] = dict(total_errors=tot, diagrams_with_errors=sum(1 for e, _ in errs if e),
                              error_free=sum(1 for e, _ in errs if e == 0),
                              top5_share=sum(e for e, _ in errs[:5]) / tot if tot else 0,
                              top10_share=sum(e for e, _ in errs[:10]) / tot if tot else 0,
                              top10=[d for _, d in errs[:10]])
        S["concentration"] = conc
    with open(os.path.join(out, "element_runs.csv"), "w", newline="", encoding="utf-8") as fh:
        wr = csv.writer(fh); wr.writerow(["model", "diagram", "type", "index", "element", "runs_found"])
        for (m, did, t, i, k), runs in sorted(elem.items()):
            wr.writerow([m, did, t, i, k, sum(runs.values())])
    with open(os.path.join(out, "diff_runs.txt"), "w", encoding="utf-8") as fh:
        for (m, did, t, kind, k), runs in sorted(diffs.items()):
            fh.write(f"{m}\t{did}\t{t}\t{kind}\truns {','.join(map(str, sorted(runs)))}\t{k}\n")
    # model identifiers returned by the APIs (from run_log.csv, if present)
    ids = {}
    for mod, name in MODELS:
        f = os.path.join(bo, mod, "run_log.csv")
        if os.path.exists(f):
            rows = list(csv.DictReader(open(f, encoding="utf-8")))
            for col in (rows[0].keys() if rows else []):
                if "model" in col.lower():
                    ids.setdefault(name, {})[col] = sorted({r[col] for r in rows if r.get(col)})
    S["model_ids"] = ids
    json.dump(S, open(os.path.join(out, "stats.json"), "w", encoding="utf-8"), indent=1)
    print("written", out)


if __name__ == "__main__":
    a = sys.argv[1:]
    main(a[0], a[1], a[2], int(a[3]) if len(a) > 3 else 10000)
