1. Define a structured claim-source mapping schema with fields: claim, sourceUrl, documentName, relevantExcerpt, publicationDate
Why: Every finding in a multi-agent research system must carry its provenance. Without structured claim-source mappings, attribution is lost during summarisation. The final output then becomes text that sounds plausible. Nobody can trace it, and it has no verifiable sources.

You should see: A TypeScript interface or JSON schema with all five required fields: claim (the assertion), sourceUrl (where found), documentName (title), relevantExcerpt (supporting passage), and publicationDate (when published or data collected). Each field should be required, not optional.

Nudge
The publication date is not just metadata tidiness. It is essential for correct interpretation when two sources report different numbers.

Guidance
Include a description for each field explaining what it contains and why it is required for provenance tracking.


2. Implement two research subagents that output findings using the claim-source mapping schema, including publication dates
Why: Subagents must output in the structured format from the start. If subagents return unstructured prose, attribution is already lost before synthesis begins. Requiring structured output at the subagent level is what end-to-end provenance depends on.

You should see: Two subagent functions that each return an array of ClaimSourceMapping objects with all fields populated, including publication dates. Each subagent should research a different aspect of the same topic.

Nudge
Assign each subagent a specific research focus (e.g., market data vs regulatory developments) to simulate a real multi-agent research pipeline.

Guidance
The subagent prompt must explicitly require structured output with all five claim-source mapping fields. Without this instruction, subagents will return prose.


3. Build a synthesis agent that merges findings from both subagents while explicitly preserving all claim-source mappings through the merge process
Why: Step 3 (synthesis) is the most common failure point for attribution. The synthesis agent naturally compresses and paraphrases, destroying claim-source mappings unless explicitly instructed to preserve them. The exam tests whether you understand that attribution must be explicitly maintained through every synthesis step.

You should see: A synthesis output where every claim is traceable to its source. The synthesis should combine related findings but maintain inline citations or a reference section linking each claim to its original source URL, document name, and publication date.

Nudge
The synthesis prompt must explicitly require that every claim in the output is traceable to a specific source. Without this instruction, the agent will paraphrase and drop attribution.

Guidance
Structure the synthesis output with inline citation markers (e.g., [1], [2]) linked to a references section at the end that contains the full claim-source mappings.


4. Handle conflicting sources by annotating both values with full attribution and possible explanations, without arbitrarily selecting one value
Why: When two credible sources report different statistics, arbitrarily selecting one destroys information and presents false certainty. The exam tests that the correct approach is to annotate both values with source attribution and let the consumer, who reads the output, decide. Different publication dates often explain different numbers as trends, not contradictions.

You should see: A conflict handling function that detects overlapping claims with different values, preserves both with full attribution, and adds a possible explanation noting temporal or methodological differences. The output should never silently pick one value.

Nudge
Check for conflicts by comparing claims about the same measure (e.g., market growth rate). When values differ, both must be preserved with their dates.

Guidance
Include a possibleExplanation field that notes temporal differences (different reporting periods), methodological differences, or scope differences that may explain the discrepancy.


5. Implement content-appropriate rendering in the final output: format financial data as tables, news findings as prose, and technical findings as structured lists
Why: The exam tests that synthesis should not put everything into a uniform format. Financial data is most readable as tables, news context reads naturally as prose, and technical findings are clearest as structured lists. Forcing all content into one format degrades readability.

You should see: A rendering function that detects the content type of each section and applies the appropriate format. Financial data should appear in tables with columns for year, value, and source. News should be prose paragraphs. Technical findings should be bulleted lists.

Nudge
Classify content type based on the nature of the claims: numerical comparisons = financial/table, narrative events = news/prose, specifications or patterns = technical/list.

Guidance
Each rendered section should still include inline citations linking back to the claim-source mappings. The format changes; the attribution does not.