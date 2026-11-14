# Information Provenance and Multi-Source Synthesis: beginner POCs (Claude Agent SDK, Python)

Hands-on POCs for **Context Management & Reliability → Information Provenance and Multi-Source Synthesis** (Claude Certified Architect – Foundations).
Build spec: `curriculum/05-Context-Management-Reliability/06-revised-Information-Provenance-Multi-Source-Synthesis.md`.

## The idea in 30 seconds

```
POC 1, provenance from source to synthesis:
   market-analyst ─┐  claim-source mappings: claim, sourceUrl, documentName,     ┌─► plain prompt     ─► fluent prose, untraceable
                   ├─► relevantExcerpt (word for word), publicationDate ──────────┤
   policy-analyst ─┘  checked in Python against the library                       └─► traceable prompt ─► "... a year [M3]." + References

POC 2, conflicts and rendering (13 fixed gold mappings, 2 planted conflicts):
   K1  12% [M1] (2025-03-10)  vs  18% [M3] (2026-02-20)      keep BOTH, with a possibleExplanation; never pick one
   K2  4.2 GWh [M9] (grid only)  vs  5.1 GWh [M11] (+ behind-the-meter)
   render(): financial -> a table · news -> prose · technical -> a list, every line still carrying its [Mn]
```

* **A claim is only as good as its trail:** subagents return structured claim-source mappings from the start, and
  code checks each one against its source.
* **Synthesis is where attribution dies:** the same mappings come out traceable or untraceable depending on one
  instruction in the synthesis prompt.
* **Show both numbers:** when credible sources disagree, keep both values with their sources and dates, and say what
  might explain the difference. Picking one presents a certainty the sources don't support.
* **Format by content, citations unchanged:** tables for figures, prose for events, lists for specifications.

## Files

| File | What it is | Calls the API? |
|---|---|---|
| `provenance_setup.py` | the 6-document library and its `list_sources`/`read_source` tools, `MAPPING_FIELDS`, `MAPPING_SCHEMA`, `validate_mapping()`, `gold_mappings()`, `with_ids()`, `KIND`, `CONFLICTS`, the two analysts, the three synthesis prompts, `BRIEF_SCHEMA`, `markers()` and `sentences()` | – |
| `coordinator.py` | `run_coordinator()`, copied from `03-revised-Error-Propagation-in-Multi-Agent-Systems/` | – |
| `poc1_provenance.py` | **POC 1**: the research round with 2 analysts, then the plain and the traceable synthesis | Yes, 3 runs (1 call each; the first runs 2 subagents) |
| `poc2_conflicts_rendering.py` | **POC 2**: one structured synthesis of the gold mappings, then the conflict, content-type and rendering checks | Yes, 1 run (1 call) |
| `common.py` | reads `.env`, sets up logging, logs the model's input and output tagged with its agent | – |

## Setup (once)

```bash
cd "05-Context-Management-Reliability/06-revised-Information-Provenance-Multi-Source-Synthesis"
python3 -m venv .venv && source .venv/bin/activate   # Python 3.10+
pip install -r requirements.txt                      # the SDK bundles Claude Code: nothing else to install
cp .env.example .env                                 # then put your API key in .env
```

If `python3 -m venv` says *ensurepip is not available* (Debian/Ubuntu), install the venv package for your
Python version first, e.g. `sudo apt install python3.14-venv`. You can also copy the `.env` from an earlier POC folder.

## Run (in this order)

```bash
python poc1_provenance.py            # 3 runs: research (2 analysts), the plain synthesis, the traceable synthesis
python poc2_conflicts_rendering.py   # 1 run: the structured brief, its conflicts, and two renderings
```

What one run can't show: whether a synthesizer keeps its citations, notices a conflict or classifies a section is a
model behavior, so one run shows the typical result, measured against known answers. POC 2 starts from fixed gold
mappings so that a missed conflict can only come from the synthesis; POC 1 shows that live analysts produce the
same 13 mappings. Real libraries are far larger and their conflicts subtler, but the checks are the same.

## Reading the log

The log shows only what goes **into** each model and what comes **out** of it, plus the lines that hold the lesson.
Lines are tagged with their agent; the synthesis sessions are single agents, tagged `[coordinator]` because they run
through `run_coordinator()`. Each run is also saved to `logs/<script>_<date>_<time>.log`.

Example (illustrative: your ids, timings, wording and counts will differ):

```
13:20:14  MODEL OUTPUT  tool_use     [policy-analyst] mcp__library__read_source {'source_url': 'https://example.net/kestrel-ridge/news/2026-02'}  (id=toolu_G2)
13:20:14  MODEL INPUT   tool_result  [policy-analyst] [{'type': 'text', 'text': 'Title: Kestrel Ridge Utility Newsroom\nURL: ...\nPublished: 2026-02-05\n...'}]  (tool_use_id=toolu_G2, is_error=None)
...
13:20:52  market-analyst: 7 valid claim-source mappings
13:20:52  policy-analyst: 6 valid claim-source mappings
13:20:52  Validation errors: none: every excerpt is word for word in its source
13:21:10  Synthesis plain, from 13 mappings with 0 tool calls: {'body sentences': 6, 'with a valid marker': 0, 'findings cited': 0, 'complete reference lines': 0}
13:21:31  Synthesis traceable, from 13 mappings with 0 tool calls: {'body sentences': 9, 'with a valid marker': 9, 'findings cited': 13, 'complete reference lines': 13}
```

* The two `Synthesis` lines come from the same 13 mappings and the same model: only the instruction differed.
  Compare the two briefs in the `MODEL OUTPUT  text` lines above them.
* POC 2 logs `K1`/`K2` with both values and the explanation, what `pick_one` would drop, then the brief rendered by
  content type and the same sections as uniform bullets.

## Concept map (IDs from the build spec)

| ID | Concept | Where you see it |
|---|---|---|
| C1 | A claim-source mapping schema: five required fields, each with a description | `MAPPING_FIELDS`, `MAPPING_SCHEMA` and `validate_mapping()` in `provenance_setup.py` |
| C2 | Every finding must carry its provenance, or attribution is lost (already covered) | taught in `01-Agentic-Architecture-Orchestration/03-Subagent-Invocation-and-Context-Passing`; here the plain synthesis line shows the loss again |
| C3 | The publication date is essential for interpreting figures that differ | POC 2 line `K1 without dates: ... With dates: 12% (2025-03-10) vs 18% (2026-02-20), 347 days apart` |
| C4 | Two research subagents return mappings with every field, on different aspects | `AGENTS` in `provenance_setup.py`; POC 1 lines `market-analyst: 7 ...` and `policy-analyst: 6 ...` |
| C5 | Subagents output the structured format from the start (already covered) | taught in `01-Agentic-Architecture-Orchestration/03-Subagent-Invocation-and-Context-Passing`; here `research_round()` validates before any synthesis, and prose counts as an error |
| C6 | The subagent prompt must require all five fields (already covered) | taught in `01-Agentic-Architecture-Orchestration/03-Subagent-Invocation-and-Context-Passing`; here `MAPPING_FORMAT` ends both analysts' prompts |
| C7 | A synthesis that merges both reports and keeps every mapping | `synthesize()` in `poc1_provenance.py`: the same numbered mappings to both prompts; `with 0 tool calls` |
| C8 | Synthesis is where attribution is most often lost; the prompt must require it | `PLAIN_PROMPT` against `TRACEABLE_PROMPT`; the two `Synthesis ...` lines |
| C9 | Inline markers linked to a references section with the full mappings | `TRACEABLE_PROMPT`; `traceability()` in `poc1_provenance.py` |
| C10 | Conflict handling: detect the same measure with different values, keep both with attribution | `BRIEF_PROMPT` and `BRIEF_SCHEMA`'s `conflicts`; `check_conflicts()`; the `K1 kept both values ...` and `K2 ...` lines |
| C11 | Picking one credible value destroys information and fakes certainty | `pick_one()` in `poc2_conflicts_rendering.py`; the `pick_one (latest source) on K1/K2 would keep ... and drop ...` lines |
| C12 | `possibleExplanation`: temporal, method or scope differences | the `possibleExplanation (planted reason: temporal/scope)` part of the K1 and K2 lines |
| C13 | Content-appropriate rendering: tables, prose and lists | `render()`; the brief rendered by content type in the log |
| C14 | Don't force all content into one uniform format | `render_uniform()`; the same sections as uniform bullets, logged after `render()`'s |
| C15 | Classify the content type from the nature of the claims | `KIND` and `section_kinds()`; the `Content types: ...` line |
| C16 | Every rendered section keeps its inline citations | `check_rendering()`; the `Rendering check: ...` line and the `## References` section |
| E1 | A fixed set of mappings as POC 2's input | `GOLD = with_ids(gold_mappings())` in `poc2_conflicts_rendering.py` |

## Settings (`.env`)

* `MODEL_ID`: the model for every call; the analyst subagents inherit it (default `claude-sonnet-5-5`).
* `MAX_BUDGET_USD`: the SDK stops a single `query()` call, its subagents included, whose estimated spend passes this (default `1.00`).
