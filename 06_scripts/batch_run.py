#!/usr/bin/env python3
"""Main run through the three providers' batch APIs: one image plus the prompt per request.

Run from the kit folder (the one that holds prompt_v1.0.txt, png/ and tools/):

  python tools\\batch_run.py PROVIDER submit --dry-run   build the requests, send nothing
  python tools\\batch_run.py PROVIDER submit             send the batch (all 78 images x 3 runs)
  python tools\\batch_run.py PROVIDER status             show how far the batch is
  python tools\\batch_run.py PROVIDER fetch              download the replies when it has ended
  python tools\\batch_run.py PROVIDER submit --missing   send again only what is missing or unparsable

PROVIDER is claude, openai or gemini. Options for submit: --images D03,D12 (a subset, for a tiny
test batch), --reps 1 (only some of the 3 runs; use it to split a batch if a provider's
queue limit rejects the whole), --out DIR (default batch_out).

Needs the provider's library and its key in the environment (ANTHROPIC_API_KEY, OPENAI_API_KEY or
GEMINI_API_KEY). Same settings as the pilot: one user message (image first, then the prompt), no
system prompt, provider default temperature and reasoning, output limits 16,000 (Claude) and
25,000 (ChatGPT, Gemini). Every request is one separate call. Replies are saved as
OUT/<provider>/run<k>/<Dnn>.txt, parsed replies as .json, and the provider's raw batch files and
a run_log.csv are kept. A reply counts as usable if it parses as JSON after removing at most one
outer ```json fence (the fence is logged in the "fenced" column).
"""
import argparse, base64, csv, datetime, json, os, sys

MODELS = {"claude": "claude-opus-5-5", "openai": "gpt-6-astra", "gemini": "gemini-3.1-pro-preview"}
MAX_TOKENS = {"claude": 16000, "openai": 25000, "gemini": 25000}
KEYS = {"claude": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY", "gemini": "GEMINI_API_KEY"}
PROMPT_FILE = "prompt_v1.0.txt"
PNG_DIR = "png"
REPETITIONS = 3
ENDED_GEMINI = ("JOB_STATE_SUCCEEDED", "JOB_STATE_FAILED", "JOB_STATE_CANCELLED", "JOB_STATE_EXPIRED")


def parse_reply(text):
    t = text.strip()
    fenced = False
    if t.startswith("```") and t.endswith("```"):
        t = t[3:-3]
        if t.startswith("json"):
            t = t[4:]
        fenced = True
    return json.loads(t), fenced


def paths(provider, out):
    d = os.path.join(out, provider)
    return d, os.path.join(d, "batch_ids.txt"), os.path.join(d, "batch_requests.jsonl"), os.path.join(d, "run_log.csv")


def all_ids(images, reps):
    imgs = images or sorted(f[:-4] for f in os.listdir(PNG_DIR) if f.endswith(".png"))
    return [f"{i}_r{r}" for r in reps for i in imgs]


def usable(provider, out, cid):
    i, r = cid.split("_r")
    j = os.path.join(out, provider, f"run{r}", i + ".json")
    return os.path.exists(j)


def b64(i):
    return base64.b64encode(open(os.path.join(PNG_DIR, i + ".png"), "rb").read()).decode()


def client(provider):
    if not os.environ.get(KEYS[provider]):
        sys.exit(f"Set the environment variable {KEYS[provider]} first.")
    if provider == "claude":
        import anthropic
        return anthropic.Anthropic()
    if provider == "openai":
        import openai
        return openai.OpenAI()
    from google import genai
    return genai.Client(api_key=os.environ["GEMINI_API_KEY"])  # keep a reference while in use


def last(provider, out):
    f = paths(provider, out)[1]
    if not os.path.exists(f):
        sys.exit("No batch has been submitted yet.")
    return open(f).read().split()[-1]


# ------------------------------------------------------------------ submit
def submit(a):
    p, out = a.provider, a.out
    prompt = open(PROMPT_FILE, encoding="utf-8").read()
    reps = [int(x) for x in a.reps.split(",")] if a.reps else list(range(1, REPETITIONS + 1))
    images = [x for x in a.images.split(",") if x]
    ids = all_ids(images, reps)
    if a.missing:
        ids = [c for c in ids if not usable(p, out, c)]
    if not ids:
        print("Nothing to send."); return
    d, batch_file, req_file, _ = paths(p, out)
    os.makedirs(d, exist_ok=True)
    model, mx = MODELS[p], MAX_TOKENS[p]
    reqs = []
    for cid in ids:
        i = cid.split("_r")[0]
        data = b64(i)
        if p == "claude":
            reqs.append({"custom_id": cid, "params": {"model": model, "max_tokens": mx, "messages": [{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": data}},
                {"type": "text", "text": prompt}]}]}})
        elif p == "openai":
            reqs.append({"custom_id": cid, "method": "POST", "url": "/v1/responses", "body": {
                "model": model, "max_output_tokens": mx, "input": [{"role": "user", "content": [
                    {"type": "input_image", "image_url": "data:image/png;base64," + data},
                    {"type": "input_text", "text": prompt}]}]}})
        else:
            reqs.append({"key": cid, "request": {"contents": [{"role": "user", "parts": [
                {"inline_data": {"mime_type": "image/png", "data": data}}, {"text": prompt}]}],
                "generation_config": {"max_output_tokens": mx}}})
    print(f"{len(reqs)} requests built, first {ids[0]}, last {ids[-1]}.")
    if p == "claude":
        if a.dry_run:
            print("Dry run: nothing sent."); return
        b = client(p).messages.batches.create(requests=reqs)
        bid = b.id; state = b.processing_status
    else:
        with open(req_file, "w", encoding="utf-8") as f:
            f.write("\n".join(json.dumps(r, ensure_ascii=False) for r in reqs) + "\n")
        print(f"Request file: {req_file} ({os.path.getsize(req_file) / 1e6:.1f} MB)")
        if a.dry_run:
            print("Dry run: nothing sent."); return
        cl = client(p)
        if p == "openai":
            up = cl.files.create(file=open(req_file, "rb"), purpose="batch")
            b = cl.batches.create(input_file_id=up.id, endpoint="/v1/responses", completion_window="24h")
            bid, state = b.id, b.status
        else:
            from google.genai import types
            up = cl.files.upload(file=req_file, config=types.UploadFileConfig(display_name="uc-diagram-requests", mime_type="jsonl"))
            job = cl.batches.create(model=model, src=up.name, config={"display_name": "uc-diagram-extraction"})
            bid, state = job.name, job.state.name
    open(batch_file, "a").write(bid + "\n")
    print(f"Batch submitted: {bid}  status: {state}")
    print(f"Check later with:  python tools\\batch_run.py {p} status")


# ------------------------------------------------------------------ status
def status(a):
    p = a.provider
    cl = client(p)
    bid = last(p, a.out)
    if p == "claude":
        b = cl.messages.batches.retrieve(bid); c = b.request_counts
        print(f"Batch {bid}: {b.processing_status}. processing {c.processing}, succeeded {c.succeeded}, "
              f"errored {c.errored}, canceled {c.canceled}, expired {c.expired}")
    elif p == "openai":
        b = cl.batches.retrieve(bid); c = b.request_counts
        print(f"Batch {bid}: {b.status}. " + (f"completed {c.completed}, failed {c.failed}, total {c.total}" if c else ""))
        if b.status == "failed" and b.errors:
            print("   failed:", "; ".join(e.message for e in b.errors.data))
    else:
        job = cl.batches.get(name=bid)
        print(f"Batch {bid}: {job.state.name}")
        if job.state.name == "JOB_STATE_FAILED":
            print("The job failed:", job.error)


# ------------------------------------------------------------------ fetch
def g(d, *names):
    for n in names:
        if isinstance(d, dict) and n in d:
            return d[n]
    return None


def save(a, cid, text, row_common):
    """Save a reply and its parsed JSON; return (usable, fenced)."""
    i, r = cid.split("_r")
    d = os.path.join(a.out, a.provider, f"run{r}")
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, i + ".txt"), "w", encoding="utf-8").write(text)
    try:
        obj, fenced = parse_reply(text)
        json.dump(obj, open(os.path.join(d, i + ".json"), "w", encoding="utf-8"), indent=1)
        return True, fenced
    except Exception:
        return False, False


def fetch(a):
    p = a.provider
    cl = client(p)
    bid = last(p, a.out)
    d, _, _, log_file = paths(p, a.out)
    rows = []  # (custom_id, result_type, model_returned, status, in, out, reasoning, text)
    if p == "claude":
        b = cl.messages.batches.retrieve(bid)
        if b.processing_status != "ended":
            sys.exit(f"Batch {bid} is still '{b.processing_status}'. Try again later.")
        for res in cl.messages.batches.results(bid):
            if res.result.type != "succeeded":
                rows.append((res.custom_id, res.result.type, "", "", "", "", "", "")); continue
            m = res.result.message
            rows.append((res.custom_id, "succeeded", m.model, m.stop_reason, m.usage.input_tokens,
                         m.usage.output_tokens, "", "".join(x.text for x in m.content if x.type == "text")))
    else:
        raw = ""
        if p == "openai":
            b = cl.batches.retrieve(bid)
            if b.status == "failed":
                sys.exit(f"Batch {bid} failed: nothing to download.")
            if b.status not in ("completed", "expired", "cancelled"):
                sys.exit(f"Batch {bid} is still '{b.status}'. Try again later.")
            for fid in (b.output_file_id, b.error_file_id):
                if fid:
                    raw += cl.files.content(fid).text + "\n"
        else:
            job = cl.batches.get(name=bid)
            if job.state.name not in ENDED_GEMINI:
                sys.exit(f"Batch {bid} is still '{job.state.name}'. Try again later.")
            if not (job.dest and job.dest.file_name):
                sys.exit(f"Batch {bid} ended as {job.state.name} with no result file. {job.error or ''}")
            raw = cl.files.download(file=job.dest.file_name).decode("utf-8")
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, "batch_output_" + bid.replace("/", "_") + ".jsonl"), "w", encoding="utf-8").write(raw)
        for line in raw.splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            if p == "openai":
                cid = rec["custom_id"]; resp = rec.get("response") or {}; body = resp.get("body") or {}
                if rec.get("error") or resp.get("status_code") != 200:
                    err = rec.get("error") or body.get("error") or {}
                    rows.append((cid, "error:" + str(err.get("code", resp.get("status_code"))), "", "", "", "", "", "")); continue
                text = "".join(c.get("text", "") for it in (body.get("output") or []) if it.get("type") == "message"
                               for c in (it.get("content") or []) if c.get("type") == "output_text")
                st = body.get("status", "")
                if st == "incomplete" and body.get("incomplete_details"):
                    st += ":" + str(body["incomplete_details"].get("reason"))
                u = body.get("usage") or {}
                rows.append((cid, "succeeded", body.get("model", ""), st, u.get("input_tokens", 0), u.get("output_tokens", 0),
                             (u.get("output_tokens_details") or {}).get("reasoning_tokens", ""), text))
            else:
                cid = rec.get("key"); resp = rec.get("response"); cands = g(resp, "candidates") or []
                if not resp or not cands:
                    rows.append((cid, "error:" + json.dumps(rec.get("error") or "no response")[:80], "", "", "", "", "", "")); continue
                cand = cands[0]
                parts = g(g(cand, "content") or {}, "parts") or []
                text = "".join(x.get("text", "") for x in parts if not x.get("thought"))
                um = g(resp, "usageMetadata", "usage_metadata") or {}
                rt = g(um, "thoughtsTokenCount", "thoughts_token_count") or 0
                rows.append((cid, "succeeded", g(resp, "modelVersion", "model_version") or "",
                             g(cand, "finishReason", "finish_reason") or "",
                             g(um, "promptTokenCount", "prompt_token_count") or 0,
                             (g(um, "candidatesTokenCount", "candidates_token_count") or 0) + rt, rt, text))
    new = not os.path.exists(log_file)
    log = open(log_file, "a", newline="", encoding="utf-8"); w = csv.writer(log)
    if new:
        w.writerow(["custom_id", "batch_id", "fetched_utc", "result_type", "model_returned", "status", "input_tokens",
                    "output_tokens", "reasoning_tokens", "valid_json", "fenced"])
    now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    ok = bad = fen = tin = tout = 0
    for cid, rt_, mr, st, ti, to, rtok, text in rows:
        if rt_ != "succeeded":
            w.writerow([cid, bid, now, rt_, "", "", "", "", "", False, False]); bad += 1; continue
        good, fenced = save(a, cid, text, None)
        ok += good; bad += (not good); fen += fenced
        tin += ti or 0; tout += to or 0
        w.writerow([cid, bid, now, rt_, mr, st, ti, to, rtok, good, fenced])
    log.close()
    print(f"Saved. Usable replies: {ok} (of which fenced: {fen}). Not usable (error, expired or not JSON): {bad}.")
    print(f"Tokens: input {tin}, output {tout}.")
    if bad:
        print(f"Send the missing ones again with:\n  python tools\\batch_run.py {p} submit --missing")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("provider", choices=list(MODELS))
    ap.add_argument("cmd", choices=["submit", "status", "fetch"])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--missing", action="store_true")
    ap.add_argument("--images", default="")
    ap.add_argument("--reps", default="")
    ap.add_argument("--out", default="batch_out")
    a = ap.parse_args()
    {"submit": submit, "status": status, "fetch": fetch}[a.cmd](a)
