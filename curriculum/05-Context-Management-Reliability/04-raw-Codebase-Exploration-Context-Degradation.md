1. Create a coordinator agent that delegates specific codebase exploration tasks to subagents (e.g., find test files, trace dependency chains, identify external integrations)
Why: Subagent delegation is primarily about context isolation, not parallelisation. The main agent context stays free of verbose output for high-level coordination while subagents handle verbose exploration. This directly prevents context degradation by keeping verbose file contents and search results out of the coordinator context.

You should see: A coordinator function that spawns subagents with specific, focused investigation prompts. Each subagent returns a structured summary (key findings, file paths, class names) rather than raw verbose output. The coordinator context should remain free of raw verbose output.

Nudge
Define 3-4 specific investigation tasks, each narrow enough for a single subagent to handle without filling its own context.

Guidance
Each subagent should return structured data (class names, file paths, findings), not the raw file contents it read during exploration.


2. Implement scratchpad file management: agents write key findings (class names, file paths, dependency chains) to a known file and read it before subsequent exploration steps
Why: Scratchpad files are the primary mitigation for context degradation. They persist knowledge outside the conversation context. So the attention shift does not affect that knowledge. That shift is what causes the model to reference typical patterns instead of specific class names and file paths it discovered earlier.

You should see: An agent that writes structured findings to a scratchpad file after each exploration step and reads the scratchpad at the start of each subsequent step. The scratchpad should contain specific class names, file paths, and dependency chains, not summaries.

Nudge
The scratchpad should be a Markdown file with clear sections for key classes, dependency chains, and critical findings. Write to it after each major discovery.

Guidance
This is a deliberate strategy, not a fallback. Agents should be instructed to maintain scratchpad files from the start of any extended exploration session.


3. Build summary injection logic: after Phase 1 exploration, summarise findings and inject the summary into Phase 2 subagent prompts
Why: Summary injection prevents the cold start problem where Phase 2 subagents duplicate Phase 1 exploration because they were not given previous findings. It ensures Phase 2 agents have the architectural understanding needed to ask the right questions without rediscovering the system structure.

You should see: A Phase 1 summary document that captures the high-level architecture, key concerns, and specific investigation targets for Phase 2. This summary is injected into the initial prompt of every Phase 2 subagent.

Nudge
The summary should include the architectural overview, dependency chains discovered, and the specific Phase 2 objective for each subagent.

Guidance
Keep the summary concise and structured. Phase 2 subagents need context, not the full verbose output from Phase 1.


4. Implement crash recovery: each agent exports structured state (explored paths, key findings, next steps) to a manifest file that the coordinator loads on resume
Why: Extended exploration sessions can fail from crashes, network interruptions, or context exhaustion. Without recovery mechanisms, all progress is lost. Structured state manifests enable the coordinator to resume from the last checkpoint rather than restarting from the beginning.

You should see: A manifest file in JSON format containing the session ID, current phase, explored paths, key findings, and next steps. On resume, the coordinator loads this manifest and injects it into agent prompts so exploration continues from the point where it stopped.

Nudge
The manifest should be updated after every significant exploration step, not just at the end of a phase. Frequent checkpointing (saving the manifest) minimises the work lost in a crash.

Guidance
Include a nextSteps array so the resumed session knows exactly what to investigate next without re-analysing the findings.


5. Test context degradation by running an extended exploration session across multiple modules and verify that scratchpad files preserve specific class names and file paths that would otherwise degrade to generic descriptions
Why: This validates that the scratchpad mitigation actually works against context degradation. The observable symptom is the model referencing typical patterns instead of specific classes and paths. You need to confirm that scratchpad files prevent this degradation.

You should see: Two comparison runs: one without scratchpad files where the agent degrades to generic references after exploring 4-5 modules, and one with scratchpad files where the agent maintains specific class names and file paths throughout the entire session.

Nudge
Look for the specific degradation symptom: the agent saying this follows the typical repository pattern instead of the OrderRepository class at src/repos/order.ts implements Repository<T>.

Guidance
After exploring 5+ modules, ask the agent to list all classes it discovered with their file paths. Without scratchpad files, it will miss or generalise. With scratchpad files, it will reference the file for accurate details.