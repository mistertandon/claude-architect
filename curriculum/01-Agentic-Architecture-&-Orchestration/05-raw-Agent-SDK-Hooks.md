1. Create an agent with three MCP tools that return data in different formats: Tool A returns Unix timestamps and numeric status codes, Tool B returns ISO 8601 dates and string statuses, Tool C returns DD/MM/YYYY dates and single-character status codes
Why: This recreates the data format chaos example from the exam. Without normalisation, the model must interpret three different date formats and three different status representations, leading to inconsistent parsing across iterations.

You should see: Three tool implementations that each return data with distinct date and status formats. Tool A uses epoch seconds and numeric codes, Tool B uses ISO strings and English statuses, Tool C uses DD/MM/YYYY and single characters.


2. Implement a PostToolUse hook that intercepts all tool results and normalises dates to ISO 8601 format and status codes to human-readable English strings
Why: PostToolUse hooks run after execution but before the model processes the result. This is the correct hook direction for data normalisation — the exam tests whether you know that PostToolUse transforms data after execution, not before.

You should see: A HookCallback registered under PostToolUse that reads tool_response and rewrites it: Unix timestamps and DD/MM/YYYY dates to ISO 8601, numeric and single-character status codes to English strings. The rewritten object comes back as updatedToolOutput inside hookSpecificOutput.


3. Verify the model receives consistent data by testing with queries that require results from all three tools
Why: Consistent data eliminates interpretation errors. Without normalisation, the model might confuse day/month order in DD/MM/YYYY or misinterpret status code P as processed instead of pending. Verification proves the hook works across all tool outputs.

You should see: Three tool results that all use ISO 8601 dates and English status strings, whichever tool produced them. The model response should reference dates and statuses consistently.


4. Add a PreToolUse hook that blocks process_refund when the amount exceeds $500 and redirects to a human escalation workflow
Why: A PreToolUse hook runs before execution — the refund never processes. The exam specifically warns against using PostToolUse for blocking, because by that point the action has already occurred. Pre-execution interception is the only correct hook direction for policy enforcement.

You should see: A PreToolUse callback that inspects the refund amount and denies anything above $500, returning permissionDecision deny with a permissionDecisionReason. The refund tool never executes for denied calls.


5. Add a second PreToolUse hook that blocks transfer_funds until aml_check has returned a pass result in the current session
Why: This is the AML compliance scenario from the exam. Prompt instructions achieve 95% compliance, but regulatory requirements demand 100%. The hook provides deterministic enforcement that no prompt can match — a single missed AML check can result in legal penalties.

You should see: Two callbacks: a PreToolUse hook on transfer_funds that denies until session state records a passing AML check, and a PostToolUse hook on aml_check that sets that state.


6. Test both hooks by attempting to trigger the blocked operations and verify they are prevented before execution
Why: Testing confirms that the hooks provide deterministic enforcement. The key verification is that blocked tools never execute — the hook prevents the call, not just logs a warning after the fact.

You should see: Both denied operations leave their tool handlers untouched, and the model receives the permissionDecisionReason. Once the prerequisites are met, the same operations run.

