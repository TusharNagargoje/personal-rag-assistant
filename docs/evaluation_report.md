# Evaluation report

No benchmark scores are reported yet. The sample set at `backend/eval/test_dataset.json` contains two reference questions for the included sample knowledge base. `backend/eval/evaluate_ragas.py` checks for RAGAS but requires an application adapter to collect model answers and retrieved contexts before metrics can be calculated. This avoids publishing fabricated faithfulness, answer relevancy, or context precision results.

To turn this into a benchmark, run each reference question through the API, save the generated answer and retrieved contexts, and score those columns with RAGAS. Record the provider, model, date, and dataset revision alongside every result.
