# Use case diagram extraction prompt, draft v0.5 (7 November 2026)

Status: draft v0.5, in pilot. v0.4 → v0.5 after the Gemini pilot: a type label such as "Use Case" printed inside an ellipse is not part of the name (Gemini appended " use case" to every name in D38, which has this label; Claude and ChatGPT had not). The remaining Gemini differences (swapped line ends in D27 and an extra association in D48) are model errors, not prompt changes. Earlier history: v0.3 → v0.4 after the third pilot run: an arrow with arrowheads at both ends is reported as "both" (the ground truth treats it as a bidirectional association, like a plain line). v0.2 → v0.3 after the second pilot run (6 diagrams, Claude): any text box or sticky note is a note (not `other`); stereotypes are not part of names; an extend reuses the exact text of the base's extension point entry; associations are given as actor, use case and which end the arrowhead is at, with multiplicity per end, matching the ground-truth convention (actor first, direction in Details). v0.1 → v0.2 after the first pilot call (D03, Claude): `other` restricted to references outside the diagram, and `details` restricted to non-standard notation, unreadable labels and ambiguities (v0.1 returned logo, bullet text and colours that the ground truth does not contain).

Task (confirmed by Mohamed 7 Nov 2026: "all constructs possible, everything"): for each of the 78 diagrams, the LLM lists every construct drawn in the image, in the same element types as the 78 ground-truth annotation sheets (one Excel file per diagram, consensus of two annotators, completed before the LLM runs). Each model's answer is scored row by row against these sheets. The prompt goes beyond the Excel types (actor generalization) so that nothing drawn is left out; extra types are scored separately.

---

## 1. Models

| Provider | Identifier | Access and settings | Status on 7 Nov 2026 |
|---|---|---|---|
| Anthropic | `claude-opus-5-5` | Provider API, default settings, no system prompt | Check the Anthropic models overview and deprecations pages. |
| OpenAI | `gpt-6-astra` | Provider API, default settings | No deprecation in the OpenAI changelog (released 3 Sep 2026). Newer models exist (`gpt-6.1-sol`, `gpt-6.1-terra`). This model **does not accept custom `temperature` or `top_p`**. |
| Google | `gemini-3.1-pro-preview` | Provider API, default settings | Highest risk because it is a preview model. The Gemini deprecations page says "No shutdown date announced", but Google retired the earlier `gemini-3-pro-preview` less than four months after release. |

What to check with each provider just before the runs:
1. The deprecations or retirement page lists no shutdown date before your last run.
2. The `model` field in the API response (record it for every call; it is the identifier you report).
3. Whether the identifier is an alias or a dated snapshot. If it is an alias, report that the provider may update it, and give the run dates.
4. The model accepts image input through the batch API.

Sources: [Gemini API deprecations](https://ai.google.dev/gemini-api/docs/deprecations?hl=en), [OpenAI API changelog](https://developers.openai.com/api/docs/changelog?mw_entry=2026-08-21-3a253b16744d621b).

---

## 2. Settings to fix and report

| Setting | Proposal | Rationale |
|---|---|---|
| Message | One user message: image first, then the prompt text. No system prompt, examples, tools or retrieval. | One identical input for all three providers, with nothing model-specific. |
| Temperature, top_p, reasoning, effort | Provider defaults, not set. Record the defaults in force on the run date. | `gpt-6-astra` rejects custom temperature, so setting it for only two models would make the conditions unequal. |
| Max output tokens | 16,000 for Claude, 25,000 for ChatGPT and Gemini. Report them. | Reasoning tokens count against the limit, so ChatGPT and Gemini get more room for their own reasoning plus the reply. Avoids truncated JSON on large diagrams (D48 has many elements). |
| Structured output | Prompt-only JSON. Do not turn on each provider's JSON-schema mode. | The three schema modes work differently, so the input would not be identical. A reply that is not valid JSON counts as a failure and is reported. |
| Runs | 3 independent calls per image per model: 78 × 3 = 234 calls per model, 702 in total. | Lets you report run-to-run variation and a majority answer. |
| Image preprocessing | Flatten every image onto white and save as PNG at its original resolution. Report this step. | Several images are transparent with black text (D11, D21, D57, D58). If a provider puts them on black, the labels disappear. Some providers also reject GIF. |
| Image size | Report pixel sizes. Note that providers resize large images. | Small labels may become hard to read. Report this as a threats-to-validity point, not something to fix. |
| Order and naming | Send images as `D01`–`D78`, in a seeded random order. | The file name gives no hint about the source or content. |
| Traces | Keep every request and response, plus the provider's raw batch files. | Guideline "Report session traces". |
| Prompt versions | Freeze as v1.0 after the pilot. Publish v0.x and the pilot outputs. | Guideline "Report system and prompt design". |

Pilot suggestion: run v0.1 through the chat apps on 4–6 diagrams that cover the hard cases (D22 note on extend, D27 «Exclude», D48 compartments, D60 dots, a transparent PNG). Fix only the wording, then freeze. Report the pilot diagrams, because they are part of the test set.

---

## 3. The prompt (send verbatim, after the image)

```text
The image attached to this message is a UML use case diagram.

TASK
List every construct of the types defined below that is drawn in the
diagram, as completely as possible. Transcribe what is drawn, not what the
author probably meant. If a symbol or notation is not standard UML but clearly
stands for one of the construct types below, record it as that type and
describe the original notation in "details". Anything that does not map to
one of the types goes under the last three types (other_relationships,
other_dependencies, other). Copy names exactly as written,
including spelling mistakes, capitalisation and line breaks (replace a line
break with a single space). A stereotype written with a name (for example
<<CRUD>> before or above it) is not part of the name: leave it out. The same
applies to a type label such as the words "Use Case" printed inside an ellipse
or box under or beside the name. Do not add, merge, correct or rename anything.
If a label cannot be read, write "[illegible]" and say so in "details".

CONSTRUCT TYPES
- system_boundaries: each rectangle drawn around use cases. Give the label
  only if it is written on the rectangle itself; otherwise null. Never use the
  file name, and never invent or guess a name or domain.
- actors: each actor (stick figure, box marked <<actor>>, or other symbol).
- use_cases: each use case (ellipse, or a box marked <<use case>>). Give its
  name and "abstract" (true only if the name is in italics or
  marked {abstract}). "extension_points" lists the entries of an "extension
  points" compartment inside the use case, in order; otherwise [].
- includes: each arrow labelled <<include>>, from the base use case to the
  included use case.
- extends: each arrow labelled <<extend>>, from the extending use case to the
  base use case. "extension_points" lists the extension points of the base
  use case that this extend uses, copied with the exact text of the entry in
  the base use case's extension points compartment (do not add a new entry or
  a shortened form of one that is already in the compartment). If the base has
  no compartment, list the extension point named on the arrow or in a note
  attached to it; otherwise []. "condition" is the
  condition text written on the arrow, in a note attached to the arrow, or in
  a note labelled "Condition:" attached to the arrow; otherwise null. Copy the
  condition text exactly, with its braces if it has them.
- use_case_generalizations: each generalization (solid line, hollow triangle)
  between two use cases, from child to parent.
- actor_generalizations: each generalization between two actors, from child
  to parent.
- associations: each line or arrow between an actor and a use case that is
  not one of the types above. Always give "actor" first and "use_case"
  second. "arrow_points_to" is "use_case" if there is an arrowhead at the use
  case end only, "actor" if there is an arrowhead at the actor end only, "both"
  if there are arrowheads at both ends, and null if the line has no arrowhead. Record any multiplicity written on the line (for
  example 1, 0..1, *, 1..*) in "multiplicity_at_actor" if it is next to the
  actor end, and in "multiplicity_at_use_case" if it is next to the use case
  end; otherwise null. Do not guess which end a multiplicity belongs to; if it
  is not clearly next to one end, write null and describe it in "details".
- notes: each note: any box, sticky note, callout or info card that holds text,
  with or without a folded corner, whatever the text says (including text that
  refers to source code, tutorials or other documents). Give the text and the
  element it is attached to, or null.
- other_relationships: each line or arrow between two use cases that is not an
  include, extend or generalization and is not drawn as a dashed arrow with a
  label (for example an unlabelled solid arrow). Give "from" (tail) and "to"
  (head), and describe how it is drawn in "details".
- other_dependencies: each dashed arrow whose label is not <<include>> or
  <<extend>> (for example <<exclude>>). Give "from" (tail), "to" (head) and the
  label as written, and describe it in "details" if needed.
- other: only a hyperlink or a link-style reference to another diagram or
  document that is NOT inside a box, note or callout (those are notes). Do not
  use "other" for boxes with text, logos, titles, free text, bullet lists,
  decorative elements, colours, layout or connector lines of notes. Give the
  text of the reference and say what it is attached to, or null.

Refer to actors and use cases by their names exactly as transcribed. If a
type does not appear in the diagram, give an empty list. Use "details" only
for non-standard notation, an unreadable label, or a real ambiguity about the
element; never for colours, icons, fill, position or layout. Otherwise write
null.

OUTPUT
Reply with one JSON object and nothing else, with no text before or after it
and no code fences. Use exactly these keys:

{
  "system_boundaries": [{"label": "...", "details": null}],
  "actors": [{"name": "...", "details": null}],
  "use_cases": [{"name": "...", "abstract": false, "extension_points": [], "details": null}],
  "includes": [{"base": "...", "included": "...", "details": null}],
  "extends": [{"extending": "...", "base": "...", "extension_points": [], "condition": null, "details": null}],
  "use_case_generalizations": [{"child": "...", "parent": "...", "details": null}],
  "actor_generalizations": [{"child": "...", "parent": "...", "details": null}],
  "associations": [{"actor": "...", "use_case": "...", "arrow_points_to": null, "multiplicity_at_actor": null, "multiplicity_at_use_case": null, "details": null}],
  "notes": [{"text": "...", "attached_to": null, "details": null}],
  "other_relationships": [{"from": "...", "to": "...", "details": null}],
  "other_dependencies": [{"from": "...", "to": "...", "label": "...", "details": null}],
  "other": [{"description": "...", "attached_to": null}]
}
```

---

## 4. Design rationale (for the paper)

- **One prompt for all three providers.** There are no model names, roles or provider-specific formatting tips in the prompt, so the input is the same for every model.
- **No persona.** This task is transcription, not judgement, so a persona line (for example "You are an experienced requirements engineer") adds nothing and is one more variable. Easy to add back.
- **"Transcribe what is drawn".** This follows the annotation rule "code what is drawn, not what the author probably meant", which the human annotators used. Model and human outputs then measure the same construct.
- **Element types match the Excel schema one to one.** Each key maps to an Excel row type: `abstract: true` to Abstract use case, `extension_points` to Extension point, `condition` to Extend condition, `directed` to Bidirectional or Directed association. Empty lists correspond to the "None" rows. Scoring can then be done by a script. Actor generalization is included because it appears in the data, although the template sheet omits it.
- **Extension points and conditions are defined by where they are drawn.** The definitions copy the annotation template and codebook, so the borderline cases are settled the same way for models and annotators: D22 (note on the extend), D60 (dots with notes, no compartment) and D38 (note on a use case, not on the extend).
- **Output keys.** The output keys follow the 16 element types in Mohamed's 78 annotation sheets: the 12 template types, actor generalization, and Other relationship, Other dependency and Other (D38, D27, D40). Non-standard notation is recorded as an existing construct when it clearly maps to one (original notation in "details"); otherwise it goes under one of the three other keys. Not tracked: role names, actor-actor or use case-use case associations, free text labels.
- **JSON only, no markers.** A reply that is cut off fails to parse as JSON, so a parse failure detects truncation without extra markers.
- **Zero-shot, no examples.** An example diagram would come from the dataset or would hint at the answers, and every example would bias the format of the replies.

## 5. Open questions for Mohamed

1. (Answered: full list, everything.) Do you want actor generalization added to the Excel template and codebook so the ground truth covers them?
2. Add a persona line, or keep the prompt persona-free?
3. Do the same three model identifiers stay if one is retired before the runs, or switch all three to current models?
