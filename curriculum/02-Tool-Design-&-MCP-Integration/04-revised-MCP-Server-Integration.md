# MCP Server Integration: Revised POC Requirements (5 steps → 2 POCs, Claude Agent SDK)

> **Source:** `04-raw-MCP-Server-Integration.md` · **Exam:** Claude Certified Architect – Foundations · **Topic:** Tool Design & MCP Integration → MCP Server Integration · **Build with:** Claude Agent SDK for Python (`claude_agent_sdk`), plus the `mcp` package (installed with the SDK) for one stdio server

---

## 1. Verdict: 2 POCs

The 5 raw steps are not 5 separate concepts. Steps 1–3 are **one question asked three ways**: where does a server's configuration live, and who sees it? The answers are the team file, the secret it must not contain, and the personal file. Steps 4–5 are about **what the agent sees once a server is connected**: data offered as a resource, and tools whose descriptions must compete with the built-in ones. What you need to learn splits into configuration and context:

| POC | What it teaches | Raw steps |
|---|---|---|
| **POC 1: Configuration scopes and secrets** | **Who gets which server:** a committed `.mcp.json` with the official GitHub server, whose credential is the reference `${GITHUB_TOKEN}`, never the token; a personal server in a sandboxed `~/.claude.json`; and one live session whose init message shows each server's `source` (`project` or `user`) and `status` | 1, 2, 3 |
| **POC 2: Resources and descriptions that compete** | **What the agent sees:** a database schema offered as the MCP resource `db://schema/main` replaces a chain of `list_tables`/`describe_table` calls, and a `search_codebase` tool wins against the built-in `Grep` only when its description says what it does, what it returns, when to use it, and why it beats Grep | 4, 5 |

**What changes with the Agent SDK:** the SDK runs Claude Code, which reads MCP configuration from three places:
- `.mcp.json` in the project, when `setting_sources` includes `"project"`;
- the user's `~/.claude.json`, which is always read;
- the `mcp_servers` option in code.

The init `SystemMessage` lists every server with its `name`, `status` and `source` (`project`, `user` or `sdk`). So the scoping hierarchy can be checked from code instead of from the `/mcp` panel. In SDK sessions, project servers load without the approval prompt that interactive sessions show. Claude reads MCP resources through two built-in tools, `ListMcpResourcesTool` and `ReadMcpResourceTool`, which must be named in `tools` (`tools=[]` removes them). The SDK's in-process `create_sdk_mcp_server()` takes tools only, so the resource lives in a small standalone stdio server built with `MCPServer` from the `mcp` package. Two things can only be observed, not coded: whether a developer's `${GITHUB_TOKEN}` is valid (the server's `status` shows it), and which search tool Claude prefers (measured from its first search call). The interactive side of each step (`claude mcp add`, `/mcp`, `@` mentions) is recorded in the terminal table for the later tutorial.

- **Why not 1 POC:** POC 1 changes files outside the code (`.mcp.json` and a user config) and needs only one session that reads the init message. POC 2 needs a working server and many measured runs. If one POC did both, a bad config could look like a bad description, and you couldn't tell which.
- **Why not 3 or more:** step 2 is one line of step 1's file, and step 3 only makes sense next to step 1, because the lesson is the difference between the two scopes. Steps 4 and 5 both change what one server offers, and they share its code and its runner.

**Applies to both POCs:** Python 3.10+, `pip install claude-agent-sdk` (a recent 0.2.x; it bundles the Claude Code binary and installs the `mcp` package), `ANTHROPIC_API_KEY` set in the environment (never hard-coded), mock data only, and beginner-friendly code (small, commented scripts). `GITHUB_TOKEN`, a GitHub personal access token with read access, is optional: without it, POC 1 shows the GitHub server failing to connect, which is still the expected result. Runs go through `run_agent()` from `01-revised-Agentic-Loops.md` (`poc2_agent_loop.py`), as extended in `05-revised-Agent-SDK-Hooks.md` (`options=`, `tool_results`) and in `01-revised-Tool-Interface-Design.md` (`first_response_tools`). `sentence_count()` comes from `01-revised-Tool-Interface-Design.md`. The data belongs to Lumen Home, the made-up store of `01-revised-Tool-Interface-Design.md`.

**The configuration files** (POC 1). `.mcp.json` sits in the POC folder, which acts as the project root and is committed:

```json
{
  "mcpServers": {
    "github": {
      "type": "http",
      "url": "https://api.githubcopilot.com/mcp/",
      "headers": { "Authorization": "Bearer ${GITHUB_TOKEN}" }
    },
    "lumen": {
      "command": "python",
      "args": ["${CLAUDE_PROJECT_DIR:-.}/lumen_server.py"]
    }
  }
}
```

`user_config/.claude.json` is the sandboxed user scope (E1). It is written by `write_user_config()` on first run, and `.gitignore` excludes it:

```json
{
  "mcpServers": {
    "claude-code-docs": { "type": "http", "url": "https://code.claude.com/docs/mcp" },
    "lumen": { "command": "python", "args": ["user_config/old_lumen_server.py"] }
  }
}
```

The personal server is the public Claude Code documentation server, an experimental integration that needs no credential. The second `lumen` entry points at a script that doesn't exist, and it exists only to show which scope wins when two scopes use the same name (C9). `.env.example` adds `GITHUB_TOKEN=`, empty, for each developer to fill in. `.gitignore` lists `.env` and `user_config/`.

**The stdio server `lumen_server.py`** (POC 2) uses `from mcp.server import MCPServer`, `mcp = MCPServer("lumen")` and `mcp.run()` (stdio) under `if __name__ == "__main__":`. Two environment variables switch its parts on and off: `LUMEN_SCHEMA_RESOURCE` (`on` or `off`) and `LUMEN_SEARCH_DESCRIPTION` (`sparse` or `enhanced`). Its parts:
- **The resource:** `@mcp.resource("db://schema/main", name="lumen-db-schema", title="Lumen Home database schema", description="Every table in the Lumen Home order database, with its columns, types and foreign keys.", mime_type="application/json")`, registered only when `LUMEN_SCHEMA_RESOURCE` is `on`. It returns `SCHEMA` as a dict, which the server sends as JSON.
- **`list_tables()`:** returns the 6 table names.
- **`describe_table(table)`:** returns one table's columns, or an error listing the valid names.
- **`search_codebase(query)`:** registered with `@mcp.tool(description=SEARCH_DESCRIPTIONS[mode])`. It scores each `SEARCH_INDEX` entry by how many of its keywords appear in the query, and returns the top 3 with a score above 0 as `<path>:<line> <function>: <summary>`.

`SCHEMA` has 6 tables. Every column is typed, and a foreign key (FK) is marked `→ table`:

| Table | Columns |
|---|---|
| `customers` | `customer_id` TEXT PK, `name` TEXT, `email` TEXT, `tier` TEXT, `created_at` TIMESTAMP |
| `orders` | `order_id` TEXT PK, `customer_id` TEXT → customers, `placed_at` TIMESTAMP, `status` TEXT, `total_cents` INTEGER |
| `order_items` | `order_id` TEXT → orders, `sku` TEXT → products, `quantity` INTEGER, `unit_price_cents` INTEGER |
| `products` | `sku` TEXT PK, `name` TEXT, `category` TEXT, `price_cents` INTEGER |
| `shipments` | `shipment_id` TEXT PK, `order_id` TEXT → orders, `carrier` TEXT, `tracking_number` TEXT, `shipped_at` TIMESTAMP |
| `refunds` | `refund_id` TEXT PK, `order_id` TEXT → orders, `amount_cents` INTEGER, `reason` TEXT, `created_at` TIMESTAMP |

`lumen_repo/` is a small TypeScript repo that `Grep` and `search_codebase` both search. It has 8 files, each 20–40 lines, and it is never compiled. Three of its functions answer the test questions, but the words in their code differ from the words in the questions:

| File | Function | What it does | The keyword trap |
|---|---|---|---|
| `src/billing/settlement.ts` | `canReverseCharge(order)` | decides refund eligibility: delivered within 30 days and not disputed | the file never says "refund" |
| `src/billing/refunds.ts` | `issueRefund(orderId, amountCents)` | executes a refund | says "refund" everywhere, but decides nothing |
| `src/promotions/ledger.ts` | `hasRedeemed(customerId, code)` | blocks a second use of a promo code | says "redeem", never "promo" or "twice" |
| `src/cart/discounts.ts` | `applyPromoCode(cart, code)` | parses and applies promo codes | says "promo" everywhere |
| `src/integrations/outbox.ts` | `deliverWithBackoff(event)` | re-sends failed partner callbacks with exponential backoff | never says "webhook" or "retry" |
| `src/integrations/partners.ts` | `registerPartnerCallback(url)` | stores a partner's `/webhooks/...` URL | says "webhook" |
| `src/orders/status.ts`, `src/customers/profile.ts` | filler | order status labels, profile formatting | none |

`SEARCH_INDEX` has one entry per function `{path, line, function, summary, keywords}`. The keywords of the three answers are: `canReverseCharge`: refund, refunded, eligible, eligibility, window, reverse, charge; `hasRedeemed`: promo, coupon, code, twice, reuse, once, redeem; `deliverWithBackoff`: webhook, retry, retries, failed, delivery, backoff, callback.

Every run gets its options from `mcp_setup.py`:

```python
POC_DIR = Path(__file__).resolve().parent
USER_CONFIG_DIR = POC_DIR / "user_config"   # stands in for ~/.claude and ~/.claude.json (E1)

def build_scope_options():
    # POC 1: load every scope the way Claude Code does for a developer
    return ClaudeAgentOptions(
        model="claude-opus-5-5",
        system_prompt="You are a configuration check. Reply with the single word READY.",
        cwd=str(POC_DIR),                                # the project root: .mcp.json is read from here
        setting_sources=["user", "project"],             # user: the sandboxed config; project: .mcp.json
        tools=[],                                        # no built-in tools: this run only reads the init message
        env={
            "CLAUDE_CONFIG_DIR": str(USER_CONFIG_DIR),   # the user scope is user_config/.claude.json, never your real one (E1)
            "CLAUDE_CODE_MCP_STARTUP_WAIT_MS": "10000",  # wait up to 10 s, so the init statuses are settled (E2)
            "ENABLE_TOOL_SEARCH": "false",
        },
        max_turns=1,                                     # one answer is enough
    )

def build_lumen_options(resource="on", search="enhanced", builtins=(), cwd=POC_DIR, system_prompt=DATA_PROMPT):
    # POC 2: only the lumen server, defined in code
    return ClaudeAgentOptions(
        model="claude-opus-5-5",
        system_prompt=system_prompt,
        cwd=str(cwd),                                    # lumen_repo/ for the search test, so Grep and Read search it
        mcp_servers={"lumen": {
            "command": sys.executable,                   # this venv's Python, which has the mcp package (E3)
            "args": [str(POC_DIR / "lumen_server.py")],
            "env": {"LUMEN_SCHEMA_RESOURCE": resource, "LUMEN_SEARCH_DESCRIPTION": search},
        }},
        strict_mcp_config=True,                          # ignore .mcp.json and the user config: only this server
        tools=list(builtins),                            # the built-ins each test needs, named explicitly
        allowed_tools=list(builtins) + ["mcp__lumen__list_tables", "mcp__lumen__describe_table",
                                        "mcp__lumen__search_codebase"],
        setting_sources=[],                              # ignore ~/.claude and project settings, CLAUDE.md and hooks
        env={"ENABLE_TOOL_SEARCH": "false"},             # MCP tools load in full, like the built-ins (E4)
        max_turns=12,                                    # safety cap (01 C16)
    )
```

---

## 2. Concepts and POC requirements

All 15 concepts in the raw file (C1–C15) are covered: all 15 are new or build on earlier POCs and are taught below. 6 of them (C1, C2, C5, C8, C9, C10) also have a command part, recorded in the terminal table for the tutorial, and none was already covered by an earlier revised file (see the end of this section).
Previous revised files checked: `01-revised-Agentic-Loops.md`, `02-revised-Multi-Agent-Orchestration.md`, `03-revised-Subagent-Invocation-and-Context-Passing.md`, `04-revised-Workflow-Enforcement-and-Handoff.md`, `05-revised-Agent-SDK-Hooks.md`, `06-revised-Task-Decomposition-Strategies.md`, `01-revised-Tool-Interface-Design.md`, `02-revised-Structured-Error-Responses.md`, `03-revised-Tool-Distribution-&-Tool-Choice.md` (`05-revised-Built-in-Tools.md` is still empty).
Raw step → concepts: **1** → C1–C4 · **2** → C5–C7 · **3** → C8–C9 · **4** → C10–C12 · **5** → C13–C15.
Rows marked **E** are extras that are not in the raw file. Without them, the POC breaks or gives misleading results.

### POC 1: Configuration scopes and secrets

**Build:** the configuration files (above), `mcp_setup.py` and `poc1_scope_check.py`. POC 2 reuses `mcp_setup.py`. It defines:
- `POC_DIR`, `USER_CONFIG_DIR`, `write_user_config()`, `build_scope_options()` and `build_lumen_options()` (code above);
- `check_mcp_json(path)`: returns a list of problems, empty if the file is valid. Each entry under `mcpServers` must be remote (`type` `http` or `sse`, plus a `url`) or local (a `command`, plus `args` as a list). A `url` without a `type` is an error, because Claude Code would read the entry as stdio and skip it;
- `find_secrets(text)`: returns every substring that looks like a credential: a GitHub token (`ghp_`, `gho_`, `ghu_`, `ghs_` or `ghr_` plus 36 letters or digits, or `github_pat_` plus 22 or more), or `Bearer ` followed by 20 or more token characters that don't start with `${`;
- `staged_secrets()`: inside a git work tree, runs `git diff --cached` and returns `find_secrets()` of its output; elsewhere it returns `None`.

**`poc1_scope_check.py`** first runs the offline checks, then one live session: `query("Reply READY.", options=build_scope_options())`. It prints a table of the init `SystemMessage`'s `data["mcp_servers"]` (`name`, `source`, `status`), then the number of `mcp__github__` tools in `data["tools"]`.

| ID | Concept | Requirement | Acceptance |
|---|---|---|---|
| C1 | A `.mcp.json` at the project root configures an official MCP server, the GitHub remote endpoint (**New**) | Create `.mcp.json` (above) in the POC folder, which is the project root, because `build_scope_options()` sets `cwd` to it and loads the `"project"` setting source. The `github` entry uses GitHub's official endpoint `https://api.githubcopilot.com/mcp/` | The live table shows `github` with `source` `project`. Its `status` is `connected` when `GITHUB_TOKEN` holds a valid token, and `failed` or `needs-auth` when it is empty or invalid |
| C4 | The file's shape: an `mcpServers` object; a remote entry needs `"type": "http"` and a `url`; a local entry needs `command` and `args` (**New**) | Run `check_mcp_json(".mcp.json")`, then run it on a hand-built copy whose `github` entry lost its `type` | `.mcp.json`: `[]`. It has 2 entries: `github` (remote: `type` `http` plus `url`) and `lumen` (local: `command` plus `args`). The hand-built copy: 1 problem, naming `github` and its missing `type` |
| E3 | A local stdio entry must start the right interpreter and find its script | `lumen`'s `command` is `python`, found through `PATH`, so run the POC from its activated virtual environment, whose Python has the `mcp` package. Its script path uses `${CLAUDE_PROJECT_DIR:-.}`, because a relative path resolves against the directory Claude Code was started from, not the folder of `.mcp.json`. POC 2 avoids both problems by passing `sys.executable` and an absolute path in code | The live table shows `lumen` with `source` `project` and `status` `connected`. If it shows `failed`, the usual cause is a `python` without `mcp` on `PATH` |
| C3 | Using existing community and official servers for standard integrations is always the correct first choice (**New**) | The POC contains no GitHub client code: GitHub's tools come from the official server, configured in 4 lines of JSON. The only server the POC builds itself is `lumen`, because its data is in-house and no public server can provide it | Code review: no GitHub API calls in any `.py` file. With a valid token, the live run prints a non-zero number of `mcp__github__` tools in `init_tools`, none of them written by you |
| C2 | Project-level `.mcp.json` is version-controlled and shared with everyone who clones the repository: team-wide servers belong there, not in `~/.claude.json` (**New**) | The script prints the line `Team servers: .mcp.json (committed, shared). Personal servers: ~/.claude.json (never committed)` after the table, and checks that `.gitignore` excludes `user_config/` and `.env` but not `.mcp.json` | Every server in `.mcp.json` shows `source` `project`. `.gitignore` excludes `user_config/` and `.env`, and `.mcp.json` is not ignored, so a teammate who clones the repository gets `github` and `lumen` |
| C5 | `${GITHUB_TOKEN}` environment-variable expansion for authentication credentials (**New**) | The `github` entry's `headers` hold `"Authorization": "Bearer ${GITHUB_TOKEN}"`. `load_settings()` loads `.env` into the process environment, and Claude Code expands the reference when it starts the server. The variable is also expanded in `command`, `args`, `env` and `url`, and `${VAR:-default}` supplies a default | The `Authorization` value in `.mcp.json` is exactly `Bearer ${GITHUB_TOKEN}`. With a valid token in `.env`, `github` is `connected`, so the expanded header reached GitHub |
| C6 | Committing credentials in `.mcp.json` is a security risk; `${VARIABLE_NAME}` references the variable without containing its value, keeping secrets out of repository history (**New**) | Run `find_secrets()` on `.mcp.json`, then on a hand-built copy whose header is `Bearer ghp_0123456789abcdefghijklmnopqrstuvwxyz` (a fake, token-shaped value) | `.mcp.json`: `[]`. The copy: 1 finding, the fake token. Its whole value would be in the repository history the moment the copy was committed |
| C7 | The check: the headers contain `${GITHUB_TOKEN}`, not a token; `git diff` confirms no secret is staged; each developer sets their own token locally (**New**) | Run `staged_secrets()`. Outside a git repository, print `not a git repository: scanned the files instead` and run `find_secrets()` on every file that git would track (all files except those `.gitignore` excludes). `.env.example` ships `GITHUB_TOKEN=` empty | Inside a repository: `staged_secrets() == []`. Outside: no findings in any non-ignored file. `.env.example` contains `GITHUB_TOKEN=` with no value, so each developer adds their own token to their own `.env` |
| C8 | A personal or experimental MCP server lives in `~/.claude.json`, user-level configuration (**New**) | `write_user_config()` writes `user_config/.claude.json` (above), the sandboxed `~/.claude.json` (E1). Its experimental server is `claude-code-docs`, the public Claude Code documentation server | The live table shows `claude-code-docs` with `source` `user` and `status` `connected`. The `.gitignore` rule `user_config/` keeps the file out of the repository |
| E1 | The user scope is sandboxed with `CLAUDE_CONFIG_DIR` | `build_scope_options()` sets `CLAUDE_CONFIG_DIR` to `user_config/`, so Claude Code reads `user_config/.claude.json` as its global config instead of `~/.claude.json`. Your real file also holds your account and app state, Claude Code rewrites it itself, and a POC must never edit it. To add a real personal server, use `claude mcp add --scope user` in the terminal (terminal table, C8 command) | Code review: no code path opens `~/.claude.json`. After a run, only files inside `user_config/` have changed |
| C9 | The scoping hierarchy: `.mcp.json` for team servers (shared, version-controlled), `~/.claude.json` for personal or experimental ones (personal, not version-controlled, not shared, not in the repository) (**New**) | Print the table grouped by `source`. Both scopes define a server named `lumen`, so the run also shows which one wins. When names clash, Claude Code uses the whole entry from the higher scope (local, then project, then user) and never merges fields | `project`: `github` and `lumen`. `user`: `claude-code-docs`. There is exactly 1 `lumen` row, with `source` `project` and `status` `connected`: the user entry, which points at a missing script, lost to the project entry |
| E2 | The init statuses must be settled before you read them | `CLAUDE_CODE_MCP_STARTUP_WAIT_MS=10000` makes the first turn wait up to 10 seconds for servers from settings files. The init message then reports their settled status (it needs Claude Code v2.1.274 or later, bundled with a recent SDK). Without the wait, those servers often show `pending`, which is not a failure | No row shows `pending`. If one does, raise the wait and rerun |

### POC 2: Resources and descriptions that compete

**Build:** `lumen_server.py` and `lumen_repo/` (above), `poc2_resource_test.py` and `poc2_description_test.py`, reusing `mcp_setup.py` and `run_agent()`. `mcp_setup.py` adds the prompts and descriptions:
- `DATA_PROMPT = "You are a data assistant for Lumen Home. Before you explore with tools, check the MCP resources of the lumen server for a catalogue. Never guess a table or column name."`
- `CODE_PROMPT = "You are a code assistant for the Lumen Home repository in your working directory. Find the code that answers each question and name its file and function. Never guess."`
- `SEARCH_DESCRIPTIONS["sparse"] = "Searches code."`
- `SEARCH_DESCRIPTIONS["enhanced"] = "Searches the Lumen Home codebase by meaning, using a semantic index of every function, so it finds code by what it does even when the code never uses the words in your question. Returns up to 3 matches, each as path:line, the function name and a one-line summary of what it does. Use it first for questions about behavior or intent, such as \"where do we decide whether an order can be refunded?\" or \"what stops a promo code being used twice?\". It is more accurate than Grep for these semantic searches; use Grep only to find an exact string or identifier you already know. It does not return file contents: Read the file at the path it gives."`

`poc2_resource_test.py` makes three runs with `build_lumen_options(resource=..., builtins=("ListMcpResourcesTool", "ReadMcpResourceTool"))`:
- **`catalogue`** (resource `on`): `List the MCP resources of the lumen server, with each one's uri, name, mimeType and description.`
- **`with-resource`** (resource `on`) and **`without-resource`** (resource `off`): `SCHEMA_QUESTION = "Which table and column hold a shipment's tracking number, and which column links a shipment to the customer who placed the order?"`

For each run, print every tool call and count the exploratory calls (`list_tables` plus `describe_table`). The question needs 2 tables, `shipments` and `orders`, so exploring without the resource takes at least 1 + 2 = 3 calls, and 1 + 6 = 7 if Claude describes every table.

`poc2_description_test.py` makes two runs, `sparse` and `enhanced`. Each one asks the three `CODE_QUESTIONS` with `build_lumen_options(search=mode, builtins=("Grep", "Read"), cwd=POC_DIR / "lumen_repo", system_prompt=CODE_PROMPT)`:
1. `Where do we decide whether an order can still be refunded?` → `canReverseCharge`
2. `Which code makes sure a customer can't use the same promo code twice?` → `hasRedeemed`
3. `Where is the retry logic for failed webhook deliveries?` → `deliverWithBackoff`

For each question, print the first search tool Claude called (the first of `Grep` and `mcp__lumen__search_codebase`), every tool call, and whether the answer names the expected function.

| ID | Concept | Requirement | Acceptance |
|---|---|---|---|
| C10 | Expose a content catalogue, here a database schema, as an MCP resource (**New**) | In `lumen_server.py`, register the resource with `@mcp.resource(...)` (above), returning `SCHEMA`. A resource is data the server offers to be read, not an action to call: it takes no input and changes nothing. Run `catalogue` | Claude calls `ListMcpResourcesTool`, and its result lists exactly 1 resource from the `lumen` server |
| C12 | The resource definition: structured data at a URI like `db://schema/main`, with a name, a description and a mimeType (**New**) | Print the `ListMcpResourcesTool` result from `catalogue`. A `python mcp_setup.py` self-check prints `SCHEMA`'s table count and confirms that every column has a type | The listed resource has `uri` `db://schema/main`, `name` `lumen-db-schema`, `mimeType` `application/json` and the description from the decorator. Self-check: 6 tables, and every column is typed |
| C11 | Resources give agents visibility into available data without exploratory tool calls: without one, an agent calls `list_tables`, then `describe_table` for every table (**New**) | Run `with-resource` and `without-resource`. Both use the same prompt, tools and question; only `LUMEN_SCHEMA_RESOURCE` differs. Print both runs' exploratory-call counts and resource reads side by side | `with-resource`: typically 1 `ReadMcpResourceTool` call for `db://schema/main` (sometimes after 1 `ListMcpResourcesTool` call) and 0 exploratory calls. `without-resource`: `ListMcpResourcesTool` finds nothing, then at least 3 exploratory calls (typically 3–7). Both answers name `shipments.tracking_number`, `shipments.order_id` and `orders.customer_id` |
| C15 | The enhanced shape: 3–5 sentences saying what the tool does, what it returns, when to use it, and how it compares to the built-in alternative, such as `search_codebase` being "more accurate than Grep for semantic searches" (**Builds on** `01-revised-Tool-Interface-Design.md` C9) | The self-check prints `sentence_count()` of both `SEARCH_DESCRIPTIONS`, then marks the four parts of the enhanced one: does (sentence 1), returns (`Returns`), when (`Use it first`) and compares (`more accurate than Grep`). New compared with 01's C9: the boundary is drawn against a built-in tool, not against another MCP tool | `sparse`: 1 sentence and none of the four parts. `enhanced`: 5 sentences with all four parts |
| E4 | Tool search is off, so only the descriptions differ | `ENABLE_TOOL_SEARCH=false` (code above). With tool search on (the default), Claude Code defers MCP tools: Claude first sees only their names, while built-in tools such as `Grep` load with their full descriptions. The A/B would then measure deferral as well as descriptions. In real sessions with tool search on, the enhanced description helps twice, because tool search matches queries against it: put the words Claude would search for near its start | No run's tool calls contain `ToolSearch` |
| C14 | With a sparse MCP description, the agent prefers built-in tools like `Grep`, whose descriptions are richer, so enhanced descriptions are required to compete for selection (**New**) | Run `sparse` and then `enhanced`, the same 3 questions with the same tools, prompt and repo. Print, per mode, how many questions started with `Grep` and how many with `search_codebase`, and how many answers named the expected function | `sparse`: typically 2–3 of 3 questions start with `Grep`, and Grep's keyword hits (`refunds.ts`, `discounts.ts`, `partners.ts`) can lead to a wrong function. `enhanced`: typically 3 of 3 start with `search_codebase`, and all 3 answers name `canReverseCharge`, `hasRedeemed` and `deliverWithBackoff` |
| C13 | Enhance the configured server's tool descriptions to explain capabilities and outputs in detail, so that the agent doesn't fall back to built-in tools (**Builds on** `01-revised-Tool-Interface-Design.md` C7) | The only change between the runs is `LUMEN_SEARCH_DESCRIPTION`. The tool's name, schema, handler and index stay the same, so the server's own description is the lever. New compared with 01's C7: the competitor is a built-in tool that the server's author can't change, so the server's description has to be at least as informative as the built-in's | Print `Same server, same tool, same index: only the description changed`, next to the C14 counts |

### Terminal commands (for the later tutorial)

| ID | Concept | Command | Important arguments |
|---|---|---|---|
| C1 (command) | Add the official GitHub server to the project's `.mcp.json` from the terminal (**New**) | `claude mcp add` | `--transport` / `-t`: `http` (recommended for remote servers), `sse` (deprecated) or `stdio` · `--scope` / `-s project`: writes `.mcp.json` (`local` is the default) · `<name> <url>`, such as `github https://api.githubcopilot.com/mcp/` · for a stdio server, `--` before its command and args, such as `-- python lumen_server.py` |
| C5 (command) | Put the token reference, not the token, into the file from the shell (**New**) | `claude mcp add … --header` | `--header` / `-H 'Authorization: Bearer ${GITHUB_TOKEN}'`: use single quotes, because inside double quotes the shell expands the variable and the real token lands in `.mcp.json` · `--env` / `-e KEY=value`: an environment variable for a stdio server · `claude mcp add` doesn't check credentials, so a wrong token only shows up later, in `/mcp` |
| C2 (command) | Team servers from `.mcp.json` need each developer's one-time approval in interactive sessions (**New**) | `/mcp`, `claude mcp reset-project-choices` | `/mcp`: each server's status (`✔ Connected`, `! Needs authentication`, `✘ Failed to connect`, `⏸ Pending approval`), plus approve, sign in (OAuth), reconnect and disable · `claude mcp reset-project-choices`: forgets your approve or reject choices for this project's `.mcp.json` servers |
| C8 (command) | Add a personal or experimental server outside the repository (**New**) | `claude mcp add --scope user` | `--scope user`: available in all your projects, stored in `~/.claude.json`, never shared · `--scope local` (the default): this project only, also stored in `~/.claude.json` · `claude mcp add-json <name> '<json>'`: add a server from its JSON entry |
| C9 (command) | See where each server comes from (**New**) | `claude mcp list`, `claude mcp get <name>`, `claude mcp remove <name>` | `list`: every configured server with its status, plus a warning that names any unset `${VAR}` · `get <name>`: one server's details · `remove <name>`: delete a server · when names clash, local beats project, which beats user |
| C10 (command) | Attach a resource to a prompt without a tool call (**New**) | `@` mention | `@<server>:<protocol>://<path>`, such as `@lumen:db://schema/main`: Claude Code fetches the resource and attaches it to the prompt · type `@` to see the resources of connected servers next to files in the autocomplete |

### Already covered by earlier POCs

None: every concept in this topic is new or builds on an earlier POC (cited in its row).
