#!/usr/bin/env python3
"""Tools for the UC diagram extraction study (prompt v0.1).

  prepare  IMAGES_DIR OUT_DIR           flatten images onto white, save as PNG
  extract  PROMPT_MD OUT_TXT            write the prompt text block to a file
  convert  REPLY.json OUT.xlsx          reply JSON -> sheet in the annotation layout
  score    GT_DIR REPLIES_DIR [OUT.csv] compare replies with the ground-truth sheets
  diff     GT_DIR REPLIES_DIR [OUT.txt] [lenient]  list the missing and extra items per diagram

Replies are files named D01.json ... D78.json (any run/model prefix goes in the
directory name, e.g. replies/claude/run1/D01.json). The ground-truth sheets are
named "NN Title (Source).xlsx"; NN is matched to DNN.
Run with: python3 -I ucd_tools.py ...
"""
import csv, difflib, glob, json, os, re, sys

TYPES = ["System boundary", "Actor", "Use case", "Abstract use case", "Include", "Extend",
         "Extension point", "Extend condition", "UC generalization", "Actor generalization",
         "Bidirectional association", "Directed association", "Note",
         "Other relationship", "Other dependency", "Other"]
ARROW = " → "


# ---------------------------------------------------------------- prepare
def prepare(src, dst):
    from PIL import Image
    os.makedirs(dst, exist_ok=True)
    for f in sorted(glob.glob(os.path.join(src, "*"))):
        m = re.match(r"(D\d\d)\.", os.path.basename(f))
        if not m:
            continue
        im = Image.open(f)
        if getattr(im, "is_animated", False):
            im.seek(0)
        im = im.convert("RGBA")
        bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
        bg.alpha_composite(im)
        bg.convert("RGB").save(os.path.join(dst, m.group(1) + ".png"))
        print(m.group(1), im.size)


# ---------------------------------------------------------------- extract
def extract(md, out):
    s = open(md, encoding="utf-8").read()
    a = s.index("```text") + len("```text\n")
    b = s.index("\n```", a)
    open(out, "w", encoding="utf-8").write(s[a:b] + "\n")


# ---------------------------------------------------------------- convert
def _s(x):
    return "" if x is None else str(x).strip()


def reply_to_rows(d):
    """Reply dict -> list of (Element, B, C, D) rows; absent types get one 'None' row."""
    g = lambda k: d.get(k) or []
    R = {t: [] for t in TYPES}

    bs = g("system_boundaries")
    if bs:
        for b in bs:
            lab = _s(b.get("label"))
            R["System boundary"].append(("System boundary", "Yes", None, f"Named “{lab}”" if lab else None))
    else:
        R["System boundary"].append(("System boundary", "No", None, None))

    for a in g("actors"):
        R["Actor"].append(("Actor", _s(a.get("name")), None, _s(a.get("details")) or None))
    eps = {}
    for u in g("use_cases"):
        n = _s(u.get("name"))
        R["Use case"].append(("Use case", n, None, _s(u.get("details")) or None))
        if u.get("abstract"):
            R["Abstract use case"].append(("Abstract use case", n, None, None))
        for e in u.get("extension_points") or []:
            eps[(_s(e), n)] = None
    for i in g("includes"):
        R["Include"].append(("Include", _s(i.get("base")) + ARROW + _s(i.get("included")),
                             None, _s(i.get("details")) or None))
    for x in g("extends"):
        base, ext = _s(x.get("base")), _s(x.get("extending"))
        rel = ext + ARROW + base
        R["Extend"].append(("Extend", rel, None, _s(x.get("details")) or None))
        for e in x.get("extension_points") or []:
            eps.setdefault((_s(e), base), None)
        if x.get("condition"):
            R["Extend condition"].append(("Extend condition", _s(x["condition"]), rel, None))
    for (e, base) in eps:
        R["Extension point"].append(("Extension point", e, base, None))
    for k, t in (("use_case_generalizations", "UC generalization"),
                 ("actor_generalizations", "Actor generalization")):
        for x in g(k):
            R[t].append((t, _s(x.get("child")) + ARROW + _s(x.get("parent")), None, _s(x.get("details")) or None))
    for x in g("associations"):
        act, uc = _s(x.get("actor")), _s(x.get("use_case"))
        pts = _s(x.get("arrow_points_to"))
        ma, mu = _s(x.get("multiplicity_at_actor")), _s(x.get("multiplicity_at_use_case"))
        det = []
        if pts == "both": det.append("Arrowheads at both ends")
        elif pts: det.append(f"Arrow points to the {pts.replace('_', ' ')}")
        if ma: det.append(f"multiplicity {ma} at the actor")
        if mu: det.append(f"multiplicity {mu} at the use case")
        if _s(x.get("details")): det.append(_s(x.get("details")))
        t = "Directed association" if pts in ("actor", "use_case") else "Bidirectional association"
        R[t].append((t, act, uc, "; ".join(det) or "No multiplicity"))
    for x in g("notes"):
        R["Note"].append(("Note", _s(x.get("text")), _s(x.get("attached_to")) or "Not attached",
                          _s(x.get("details")) or None))
    for x in g("other_relationships"):
        R["Other relationship"].append(("Other relationship", _s(x.get("from")) + ARROW + _s(x.get("to")),
                                        None, _s(x.get("details")) or None))
    for x in g("other_dependencies"):
        det = "; ".join(v for v in (f"Labelled “{_s(x.get('label'))}”" if _s(x.get("label")) else "",
                                    _s(x.get("details"))) if v)
        R["Other dependency"].append(("Other dependency", _s(x.get("from")) + ARROW + _s(x.get("to")),
                                      None, det or None))
    for x in g("other"):
        R["Other"].append(("Other", _s(x.get("description")), _s(x.get("attached_to")) or "Not attached", None))

    rows = []
    core = TYPES[:13]  # the template's 12 types + actor generalization appear as "None" when absent
    for t in TYPES:
        if R[t]:
            rows += R[t]
        elif t in core and t != "Actor generalization":
            rows.append((t, "None", None, None))
    return rows


def convert(reply_json, out_xlsx):
    import openpyxl
    d = json.load(open(reply_json, encoding="utf-8"))
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = os.path.splitext(os.path.basename(reply_json))[0]
    ws.append(["Element", "Name / Base / Parent / Actor", "Related element", "Details"])
    for r in reply_to_rows(d):
        ws.append(list(r))
    wb.save(out_xlsx)


# ---------------------------------------------------------------- score
def norm(s):
    s = "" if s is None else str(s)
    s = s.replace("“", '"').replace("”", '"').replace("’", "'").replace("‘", "'")
    s = s.replace("«", "<<").replace("»", ">>").replace("->", "→")
    s = re.sub(r"\s*→\s*", "→", s)
    return re.sub(r"\s+", " ", s).strip().strip('"').casefold()


FUZZY = {"Note", "Other"}
UNNAMED = {"", "[no name]", "no name", "unnamed", "[unnamed]", "null", "[illegible]"}


def norm_l(s, side, name_like=True):
    """Lenient normalisation (rules reported in the paper; applied identically to every model):
    dash variants unified, spaces around '-' and '\\' removed, trailing annotator remarks in
    parentheses dropped from ground-truth names, and unnamed actors mapped to one empty name."""
    s = norm(s)
    s = re.sub(r"[\u2013\u2014\u2212]", "-", s)
    s = re.sub(r"\s*([-\\])\s*", r"\1", s)
    if name_like:
        if side == "gt":
            s = re.sub(r"\s*\([^)]*\)\s*$", "", s)
        if s in UNNAMED or re.match(r"^\[?(unnamed )?actor( \d+)?\]?$", s):
            s = ""
    return s


def keyset(rows, lenient=False, side="gt"):
    """rows -> {type: [key,...]}, skipping 'None' rows. System boundary compared as Yes/No.
    lenient=True applies the lenient normalisation and counts at most one system boundary."""
    out = {t: [] for t in TYPES}

    def n(x, t):
        if lenient and t not in FUZZY:
            return norm_l(x, side, True)
        return norm(x)

    for t, b, c, _ in rows:
        if t not in out:
            continue
        if t == "System boundary":
            out[t].append((norm(b),))
        elif str(b).strip().casefold() == "none":
            continue
        elif t in ("Extension point", "Bidirectional association", "Directed association", "Extend condition"):
            out[t].append((n(b, t), n(c, t)))
        else:
            out[t].append((n(b, t),))
    if lenient and len(out["System boundary"]) > 1 and side != "gt":
        out["System boundary"] = [("yes",)]
    return out


def overlap(a, b):
    """Word overlap: shared words / words of the shorter text."""
    x, y = set(re.findall(r"\w+", a)), set(re.findall(r"\w+", b))
    return len(x & y) / min(len(x), len(y)) if x and y else 0.0


def match(gt, pr, fuzzy, lenient=False):
    """Return number of matched items (multiset; fuzzy uses ratio >= 0.8 on first field)."""
    pr = list(pr)
    tp = 0
    for k in gt:
        hit = None
        for i, p in enumerate(pr):
            if p == k or (fuzzy and overlap(p[0], k[0]) >= 0.6) or (
                    lenient and len(p) == len(k) and all(a == b or difflib.SequenceMatcher(None, a, b).ratio() >= 0.9
                                                         for a, b in zip(p, k))):
                hit = i
                break
        if hit is not None:
            tp += 1
            pr.pop(hit)
    return tp


def load_gt(gt_dir):
    import openpyxl
    res = {}
    for f in glob.glob(os.path.join(gt_dir, "**", "*.xlsx"), recursive=True):
        m = re.match(r"(\d\d)\b", os.path.basename(f))
        if not m:
            continue
        ws = openpyxl.load_workbook(f).worksheets[0]
        rows = [tuple(r) for r in ws.iter_rows(min_row=2, values_only=True) if r[0]]
        res["D" + m.group(1)] = rows
    return res


def compute(gt, rep_dir, lenient):
    tot = {t: [0, 0, 0] for t in TYPES}  # tp, n_gt, n_pred
    per = []
    for f in sorted(glob.glob(os.path.join(rep_dir, "**", "D[0-9][0-9].json"), recursive=True)):
        did = os.path.basename(f)[:3]
        if did not in gt:
            print("no ground truth for", f); continue
        try:
            d = json.load(open(f, encoding="utf-8"))
            pr = keyset(reply_to_rows(d), lenient, "pred")
        except Exception as e:  # invalid JSON counts as a failure
            print("FAILED", f, e); per.append((f, "parse_failure", 0, 0, 0)); continue
        g = keyset(gt[did], lenient, "gt")
        for t in TYPES:
            tp = match(g[t], pr[t], t in FUZZY, lenient)
            tot[t][0] += tp; tot[t][1] += len(g[t]); tot[t][2] += len(pr[t])
            per.append((f, t, tp, len(g[t]), len(pr[t])))
    return tot, per


def show(tot):
    print(f"{'type':28} {'P':>6} {'R':>6} {'F1':>6}   n_gt n_pred")
    for t, (tp, ng, npd) in tot.items():
        if ng == 0 and npd == 0: continue
        p = tp / npd if npd else 0.0; r = tp / ng if ng else 0.0
        f1 = 2 * p * r / (p + r) if p + r else 0.0
        print(f"{t:28} {p:6.2f} {r:6.2f} {f1:6.2f}   {ng:4d} {npd:4d}")


def score(gt_dir, rep_dir, out_csv=None):
    """Prints a strict table (normalised exact match) and a lenient table (dash and spacing
    variants, annotator remarks in parentheses, unnamed actors, spelling slips up to 10%)."""
    gt = load_gt(gt_dir)
    rows = []
    for mode in ("strict", "lenient"):
        tot, per = compute(gt, rep_dir, mode == "lenient")
        print(f"\n== {mode.upper()} ==")
        show(tot)
        rows += [(mode,) + r for r in per]
    if out_csv:
        with open(out_csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh); w.writerow(["mode", "file", "type", "tp", "n_gt", "n_pred"]); w.writerows(rows)


def diff(gt_dir, rep_dir, out_txt=None, mode="strict"):
    lenient = mode == "lenient"
    gt = load_gt(gt_dir)
    lines = []
    for f in sorted(glob.glob(os.path.join(rep_dir, "**", "D[0-9][0-9].json"), recursive=True)):
        did = os.path.basename(f)[:3]
        if did not in gt:
            continue
        try:
            pr = keyset(reply_to_rows(json.load(open(f, encoding="utf-8"))), lenient, "pred")
        except Exception as e:
            lines.append(f"{did}: FAILED to parse ({e})"); continue
        g = keyset(gt[did], lenient, "gt")
        for t in TYPES:
            miss, extra = list(g[t]), list(pr[t])
            for k in list(miss):  # remove matched pairs
                for i, p in enumerate(extra):
                    if p == k or (t in FUZZY and overlap(p[0], k[0]) >= 0.6) or (lenient and len(p) == len(k) and all(x == y or difflib.SequenceMatcher(None, x, y).ratio() >= 0.9 for x, y in zip(p, k))):
                        miss.remove(k); extra.pop(i); break
            for k in miss:
                lines.append(f"{did}  {t}  MISSING (in ground truth, not in reply): {' | '.join(k)}")
            for k in extra:
                lines.append(f"{did}  {t}  EXTRA (in reply, not in ground truth): {' | '.join(k)}")
    text = "\n".join(lines) or "No differences."
    print(text)
    if out_txt:
        open(out_txt, "w", encoding="utf-8").write(text + "\n")


if __name__ == "__main__":
    c, a = (sys.argv[1] if len(sys.argv) > 1 else ""), sys.argv[2:]
    {"prepare": prepare, "extract": extract, "convert": convert, "score": score, "diff": diff}.get(
        c, lambda *_: print(__doc__))(*a)
