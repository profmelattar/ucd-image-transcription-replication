#!/usr/bin/env python3
"""Send the prompt plus one image to Claude, ChatGPT and Gemini, and save everything.

Not tested against the live APIs (no keys in the build environment): run the pilot first.

Setup (on your own machine, keys never go in the chat or in a file):
  pip install anthropic openai google-genai
  export ANTHROPIC_API_KEY=...  OPENAI_API_KEY=...  GEMINI_API_KEY=...

Usage:
  python3 run_models.py PROMPT.txt PNG_DIR OUT_DIR --models claude,openai,gemini \
      --images D03,D12,D27,D38,D48,D61 --runs 1

Settings (identical for all three): one user message, image first and then the prompt text;
no system prompt, tools or examples; provider default temperature and reasoning; the same
output-token limits as the earlier paper (16,000 Claude; 25,000 ChatGPT and Gemini). Every call writes OUT_DIR/<model>/run<k>/<Dnn>.raw.json (full response),
<Dnn>.txt (reply text) and <Dnn>.json (parsed reply, only if the reply is valid JSON), and
appends a line to OUT_DIR/calls.jsonl with model, returned model id and timestamp.
"""
import argparse, base64, datetime, json, os, sys, time

MODELS = {"claude": "claude-opus-5-5", "openai": "gpt-6-astra", "gemini": "gemini-3.1-pro-preview"}
# Same limits and same call forms as the earlier paper's API scripts (replication package,
# stage1/prompt_trial/scripts): room for the model's own reasoning plus the reply. Report them.
MAX_TOKENS = {"claude": 16000, "openai": 25000, "gemini": 25000}
KEYS = {"claude": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY", "gemini": "GEMINI_API_KEY"}


def call_claude(model, prompt, png):
    import anthropic
    r = anthropic.Anthropic().messages.create(
        model=model, max_tokens=MAX_TOKENS["claude"],
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                         "data": base64.b64encode(png).decode()}},
            {"type": "text", "text": prompt}]}])
    return ("".join(b.text for b in r.content if b.type == "text"), r.model, r.stop_reason,
            r.usage.input_tokens, r.usage.output_tokens, "", r.model_dump())


def call_openai(model, prompt, png):
    import openai
    r = openai.OpenAI().responses.create(
        model=model, max_output_tokens=MAX_TOKENS["openai"],
        input=[{"role": "user", "content": [
            {"type": "input_image", "image_url": "data:image/png;base64," + base64.b64encode(png).decode()},
            {"type": "input_text", "text": prompt}]}])
    status = r.status + (":" + str(r.incomplete_details.reason) if r.status == "incomplete" and r.incomplete_details else "")
    d = getattr(r.usage, "output_tokens_details", None)
    return (r.output_text or "", r.model, status, r.usage.input_tokens, r.usage.output_tokens,
            getattr(d, "reasoning_tokens", "") if d else "", r.model_dump())


def call_gemini(model, prompt, png):
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])  # keep a reference: the client closes when garbage-collected
    r = client.models.generate_content(
        model=model,
        contents=[types.Part.from_bytes(data=png, mime_type="image/png"), prompt],
        config=types.GenerateContentConfig(max_output_tokens=MAX_TOKENS["gemini"]))
    try:
        text = r.text or ""
    except Exception:
        text = ""
    try:
        status = str(r.candidates[0].finish_reason).replace("FinishReason.", "")
    except Exception:
        status = "no candidate"
    um = r.usage_metadata
    rt = um.thoughts_token_count or 0
    return (text, getattr(r, "model_version", "") or "", status, um.prompt_token_count or 0,
            (um.candidates_token_count or 0) + rt, rt, r.model_dump(mode="json"))


def parse_reply(text):
    """Parse the reply as JSON. Returns (obj, fenced). Only one outer code fence
    (```json ... ```) is removed, nothing else; any other text makes the parse fail."""
    t = text.strip()
    fenced = False
    if t.startswith("```") and t.endswith("```"):
        t = t[3:-3]
        if t.startswith("json"):
            t = t[4:]
        fenced = True
    return json.loads(t), fenced


CALLS = {"claude": call_claude, "openai": call_openai, "gemini": call_gemini}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("prompt"); ap.add_argument("png_dir"); ap.add_argument("out_dir")
    ap.add_argument("--models", default="claude,openai,gemini")
    ap.add_argument("--images", default="")
    ap.add_argument("--runs", type=int, default=1)
    a = ap.parse_args()
    prompt = open(a.prompt, encoding="utf-8").read()
    ids = [i for i in a.images.split(",") if i] or sorted(
        f[:-4] for f in os.listdir(a.png_dir) if f.endswith(".png"))
    os.makedirs(a.out_dir, exist_ok=True)
    log = open(os.path.join(a.out_dir, "calls.jsonl"), "a", encoding="utf-8")
    for m in a.models.split(","):
        if not os.environ.get(KEYS[m]):
            sys.exit(f"Set the environment variable {KEYS[m]} first.")
        for k in range(1, a.runs + 1):
            d = os.path.join(a.out_dir, m, f"run{k}"); os.makedirs(d, exist_ok=True)
            for i in ids:
                t_ = os.path.join(d, i + ".txt")
                if os.path.exists(t_) and os.path.getsize(t_) > 0:
                    j_ = os.path.join(d, i + ".json")
                    if not os.path.exists(j_):  # re-parse a saved reply
                        try:
                            obj, _f = parse_reply(open(t_, encoding="utf-8").read())
                            json.dump(obj, open(j_, "w", encoding="utf-8"), indent=1)
                            print(m, k, i, "re-parsed" + (" (fenced)" if _f else ""))
                        except Exception:
                            print(m, k, i, "saved reply is not valid JSON")
                    continue  # resume
                png = open(os.path.join(a.png_dir, i + ".png"), "rb").read()
                t0 = time.time(); err = None; text = ""; ret = status = None; tin = tout = rt = ""
                try:
                    text, ret, status, tin, tout, rt, raw = CALLS[m](MODELS[m], prompt, png)
                    json.dump(raw, open(os.path.join(d, i + ".raw.json"), "w"), indent=1, default=str)
                except Exception as e:
                    err = repr(e)
                open(os.path.join(d, i + ".txt"), "w", encoding="utf-8").write(text or "")
                ok = False; fenced = False
                try:
                    obj, fenced = parse_reply(text)
                    json.dump(obj, open(os.path.join(d, i + ".json"), "w", encoding="utf-8"), indent=1); ok = True
                except Exception:
                    pass
                log.write(json.dumps({"model": m, "requested": MODELS[m], "returned": ret, "status": status, "input_tokens": tin,
                                      "output_tokens": tout, "reasoning_tokens": rt, "max_tokens": MAX_TOKENS[m], "image": i,
                                      "run": k, "valid_json": ok, "fenced": fenced, "error": err, "seconds": round(time.time() - t0, 1),
                                      "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}) + "\n"); log.flush()
                print(m, k, i, ("ok (fenced)" if fenced else "ok") if ok else ("ERROR " + err if err else "invalid JSON"))


if __name__ == "__main__":
    main()
