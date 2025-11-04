import os
from src.loader import load_survey, load_rules
from src.detector import detect_sensitive_data, detect_from_question

def run_pipeline(survey_path: str, rules_path: str):
    base_dir = os.path.dirname(os.path.dirname(__file__))
    survey_path = os.path.join(base_dir, survey_path)
    rules_path = os.path.join(base_dir, rules_path)

    survey = load_survey(survey_path)
    patterns = load_rules(rules_path)

    results = []

    for i, response in enumerate(survey.get("responses", []), start=1):
        q_text = response.get("question_text", "")
        answer = response.get("answer", "")
        q_id = response.get("question_id", i)

        flags = set()
        flags.update(detect_from_question(q_text, patterns))
        flags.update(detect_sensitive_data(answer, patterns))

        results.append({
            "question_id": q_id,
            "question_text": q_text,
            "answer": answer,
            "flags": list(flags)
        })

    return {
        "survey_id": survey.get("survey_id", "unknown"),
        "results": results
    }
