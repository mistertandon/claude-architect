1. Create a case facts extractor that identifies transactional data (amounts, dates, order numbers, statuses) from tool results
Why: The persistent case facts block is the single most important pattern in context window management. Extracting transactional facts into a structured block that is never summarised prevents progressive summarisation from destroying critical numerical values and identifiers.

You should see: A function that takes raw tool output and returns a structured object containing only the transactional facts: customer ID, order numbers, amounts, dates, and statuses. Non-transactional narrative content should be excluded.

Nudge
Focus on data types that summarisation destroys: numbers, dates, identifiers, and statuses. These are the fields a support agent needs to process a refund.

Guidance
Define a fixed set of transactional field types to extract: monetary amounts, dates, order/reference numbers, status values, and customer identifiers.


2. Implement a persistent case facts block that is prepended to every prompt, outside summarised history
Why: The case facts block must persist across every turn regardless of what happens to the conversation history. It sits outside the summarised portion of the context, ensuring amounts, dates, and order numbers survive even when earlier conversation turns are compressed.

You should see: A prompt construction function that always includes the case facts block at the top of every message, followed by any summarised history, followed by the current turn. The case facts block should be clearly delimited with a section header.

Nudge
Use a clear delimiter like a section header to separate the case facts block from the conversation history so the model treats them differently.

Guidance
The case facts block should be formatted as structured data (JSON or a clear key-value list) prepended to the system prompt or first user message of every API call.


3. Build a tool result trimmer that filters order lookup responses from 40+ fields to only the 5 relevant return-related fields
Why: Untrimmed tool results consume the context budget without anyone noticing. An order lookup returning 40+ fields consumes tokens in every subsequent turn as conversation history grows. Trimming to relevant fields before results enter context is essential, not optional.

You should see: A trimming function that takes a raw tool result object and returns only the fields needed for the current task. The trimmed result should be 80-90% smaller than the original.

Nudge
Implement this as a PostToolUse hook or within the tool implementation itself, before the result enters conversation history.

Guidance
Define the relevant fields based on the task context. For a refund workflow: order_id, order_date, total_amount, return_eligible, and item_description.


4. Test with a multi-turn conversation where summarisation occurs and verify that transactional facts survive intact across all turns
Why: This validates that the persistent case facts pattern actually works. The exam tests whether you understand that progressive summarisation destroys specific amounts and dates, and the case facts block is the fix. You need to verify this empirically.

You should see: A 6-8 turn conversation where summarisation occurs after turn 4. After summarisation, the agent should still reference the exact refund amount ($247.83), order number (#8891), and date (March 3rd) from the case facts block. Without the block, these values would be lost to summarisation.

Nudge
Run two versions: one with the case facts block and one without. After summarisation, ask the agent to confirm the refund amount and order number. The version without the block will lose specifics.

Guidance
Simulate summarisation by replacing turns 1-4 with a compressed summary after turn 4, keeping the case facts block intact in both versions.


5. Add key findings placement logic that positions summaries at the beginning of aggregated inputs to mitigate the lost-in-the-middle effect
Why: Models process information at the beginning and end of long inputs reliably, but findings buried in the middle may be missed. Placing key findings summaries at the start of aggregated inputs is a structural fix for this well-documented phenomenon.

You should see: An aggregation function that places a Key Findings Summary section at the top of combined inputs, followed by detailed results with explicit section headers. The key findings should be concise bullet points drawn from the detailed content.

Nudge
The fix is structural, not prompt-based. Do not tell the model to pay attention to everything. Instead, reorganise the input so critical information is at the beginning.

Guidance
Extract one-line summaries from each source and place them in a Key Findings Summary section at the top. Follow with detailed results using clear section headers.