1. Create a system prompt with explicit escalation criteria covering all three valid triggers: explicit human request, policy exceptions/gaps, and inability to make progress
Why: Explicit escalation criteria in the system prompt are the proportionate first response before adding infrastructure like classifier models or sentiment analysis. The exam tests that prompt optimisation should always precede architectural changes for escalation calibration.

You should see: A system prompt with three clearly defined escalation triggers, each with a description and decision rule. The prompt should also explicitly list the two anti-patterns (sentiment-based and confidence-based escalation) as things to avoid.

Nudge
Structure the criteria as a numbered list with trigger, description, and action for each of the three valid triggers.

Guidance
Include the distinction between policy gaps (policy is silent on this situation) and policy violations (the policy says no). Gaps require escalation; violations have documented answers.


2. Add few-shot examples showing: immediate escalation for explicit human request, autonomous resolution for a frustrated customer with a straightforward issue, and escalation for a policy gap
Why: Few-shot examples demonstrating when to escalate versus when to resolve autonomously directly address unclear decision boundaries. This is the exact technique the exam identifies as the correct improvement for a support agent with poor first-contact resolution rates.

You should see: Three examples in the system prompt, each showing a different scenario with the correct decision and reasoning. The frustrated-but-resolvable example should show the agent acknowledging frustration and offering the resolution directly.

Nudge
Each example should show the customer message, the agent reasoning, and the action taken. The reasoning is critical for teaching the model to apply the same reasoning to new cases.

Guidance
The key distinction to demonstrate: frustrated customer with simple issue = resolve it, customer who explicitly says I want a human = escalate immediately.


3. Implement ambiguous customer matching logic that requests additional identifiers (email, phone, order number) instead of selecting heuristically
Why: Selecting from ambiguous matches using heuristics (most recent, most active) risks privacy violations and incorrect actions. The exam tests that the only safe response to multiple customer matches is to ask for additional identifiers to disambiguate.

You should see: A matching function that detects when multiple records are returned and immediately asks for disambiguation rather than applying any selection heuristic. The disambiguation request should suggest specific identifier types.

Nudge
Never select the most recent or most active record. Any heuristic-based selection risks exposing one customer data to another.

Guidance
The disambiguation prompt should offer multiple identifier options: email, phone number, order number, or postcode. Let the customer choose which to provide.


4. Test with four scenarios: frustrated customer with simple issue, calm customer requesting policy exception, customer explicitly requesting a human, and ambiguous customer match
Why: These four scenarios cover all the critical decisions the exam tests: the difference between frustration and an explicit human request, policy gap versus violation distinction, absolute rule for explicit human requests, and privacy-safe disambiguation.

You should see: Correct handling of all four scenarios: resolution offered for the frustrated customer, escalation for the policy gap, immediate escalation for the explicit human request (no investigation first), and disambiguation request for the ambiguous match.

Nudge
The critical check for scenario 3 is that the agent escalates IMMEDIATELY without any investigation or let me try first response.

Guidance
Verify the frustrated customer scenario does NOT trigger escalation. Frustration with a resolvable issue should be resolved, not escalated.


5. Verify the agent never attempts investigation before honouring an explicit human request and never selects from ambiguous matches using heuristics
Why: These are the two absolute rules the exam tests with no exceptions. Any attempt to investigate before escalating on an explicit human request, or any heuristic selection from ambiguous matches, is a critical failure that would cost marks on the exam.

You should see: For explicit human requests: the escalation happens in the very first response with zero investigation steps. For ambiguous matches: the response always asks for additional identifiers, never selects a record. Both rules should hold across multiple phrasings and edge cases.

Nudge
Test multiple phrasings of explicit human requests: transfer me to a human, I want a person, let me speak to someone real, get me a manager.

Guidance
For ambiguous matches, test that even when one match seems more likely (same city, recent activity), the system still asks for disambiguation rather than selecting.

