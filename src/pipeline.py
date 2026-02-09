# src/pipeline.py

from src.detector import detect_sensitive_data, detect_from_question
from src.loader import load_rules
from typing import Optional

def run_pipeline(data_source, rules_path: str, survey_id: Optional[str] = None):
    """
    Storage-agnostic PII detection pipeline.

    - survey_id is optional for file-based batch sources
    - For database sources, survey_id may be required
    """

    # Load the survey template
    survey = data_source.get_survey_template(survey_id)

    if survey is None:
        if survey_id:
            print(f"No survey found with id {survey_id}")
        else:
            print("No survey template found")
        return {"results": []}

    # Load PII detection rules (keep as raw strings)
    patterns = load_rules(rules_path)

    # Extract questions
    questions = survey.get("questions") or survey.get("template", {}).get("questions", [])

    results = []

    # Iterate over all responses
    for response in data_source.iter_responses(survey_id):
        respondent_id = response.get("respondent_id")
        answers = response.get("answers", {})

        for q in questions:
            # Handle different key names in template
            qid = q.get("question_id") or q.get("id")
            q_text = q.get("question_text") or q.get("text") or q.get("question") or ""

            # Normalize the answer
            answer = str(answers.get(qid, "")).strip()

            flags = set()
            if q_text:
                flags.update(detect_from_question(q_text, patterns))
            if answer:
                flags.update(detect_sensitive_data(answer, patterns))

            if flags:
                results.append({
                    "respondent_id": respondent_id,
                    "question_id": qid,
                    "flags": list(flags)
                })

    return {
        "survey_id": survey.get("survey_id", "unknown"),
        "results": results
    }
