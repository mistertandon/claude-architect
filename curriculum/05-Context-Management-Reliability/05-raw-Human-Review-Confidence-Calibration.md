1. Create a mock extraction system that outputs field-level confidence scores for different document types (invoices, receipts, scanned PDFs, international documents)
Why: Field-level confidence scores are the foundation of intelligent review routing. The exam tests that raw model confidence is not calibrated and must be validated against ground truth before use. Building the mock system gives you data to calibrate against.

You should see: An extraction function that returns each field with its value and a confidence score between 0.0 and 1.0. The system should process at least 4 document types with noticeably different confidence distributions per type.

Nudge
Generate realistic confidence distributions: high confidence on standard invoices, lower on handwritten receipts and scanned PDFs, lowest on international documents.

Guidance
Include at least 3 fields per extraction (vendor name, date, amount) with independent confidence scores for each field.

2. Implement accuracy tracking broken down by document type and field segment — not just aggregate metrics
Why: Trusting aggregate metrics is the most dangerous misconception in production extraction systems. 97% overall accuracy can hide catastrophic failure rates on specific document types because standard invoices dominate the volume. The exam tests that you must validate by document type AND field segment before automating.

You should see: An accuracy table showing each document type and field combination separately. Standard invoices should show 95%+ accuracy while handwritten receipts and international documents show 40-70%. The aggregate should look excellent (90%+) despite the poor per-type numbers.

Nudge
Calculate accuracy per document type per field, not just overall. The revealing comparison is between the aggregate and the worst-performing segment.

Guidance
Display the results as a table with document types as rows and fields as columns. Add an aggregate row at the bottom to show how it masks the problems.

3. Build a calibration module that takes a labelled validation set (ground truth) and produces calibrated confidence thresholds per field type per document type
Why: Raw model confidence scores are not calibrated. A model reporting 0.90 confidence might actually be correct 94% of the time on date fields but only 82% on amount fields. Calibration using labelled validation sets is required before confidence scores can drive automated routing decisions.

You should see: A calibration curve for each field type per document type, mapping reported confidence ranges to actual accuracy percentages. The curve should reveal that the same confidence score means different things for different field-document combinations.

Nudge
Group extractions into confidence bands (0.5-0.6, 0.6-0.7, etc.) and calculate actual accuracy within each band for each field-document combination.

Guidance
The calibration output should be a lookup table: given document type, field type, and reported confidence, what is the actual expected accuracy?

4. Implement stratified random sampling that selects high-confidence extractions for ongoing verification, sampling proportionally across all document types
Why: High-confidence extractions are automated and not reviewed. If the model develops a novel error pattern affecting high-confidence items, only stratified sampling will catch it. Sampling only low-confidence items means nobody sees systematic errors in automated extractions.

You should see: A sampling function that selects a representative subset from each stratum (document type and confidence band), including samples from the high-confidence automated extractions. The sample should be proportional to the volume in each stratum.

Nudge
The critical insight is sampling high-confidence items, not just low-confidence ones. Low-confidence items already go to human review. High-confidence items are the blind spot.

Guidance
Sample proportionally across all document types. If 80% of volume is standard invoices, 80% of your sample should be standard invoices, but ensure every document type has minimum representation.

5. Build a review router that prioritises limited reviewer capacity on the highest-uncertainty items, dynamically reordering the review queue as new extractions arrive
Why: Human reviewers are expensive and limited. Spreading capacity evenly across all extractions wastes time on high-confidence items while leaving insufficient capacity for uncertain items that need human judgement. Dynamic priority ordering ensures the most uncertain items are always reviewed first.

You should see: A priority queue that orders items by uncertainty (lowest confidence first), dynamically reorders as new extractions arrive, and serves the next-highest-uncertainty item to each available reviewer. The queue should never serve items in chronological order.

Nudge
Use a priority queue or sorted insertion to maintain uncertainty ordering. When a reviewer finishes one item, the next should be the highest-uncertainty item remaining, not the next in arrival order.

Guidance
Consider using calibrated confidence (from step 3) rather than raw confidence for prioritisation. A raw 0.80 on international documents is actually less reliable than a raw 0.70 on standard invoices.