from src.detector import detect_sensitive_data, detect_from_question
from src.loader import load_rules

# storage-agnostic pipeline
def run_pipeline(data_source, survey_id: str, rules_path: str):
    survey = data_source.get_survey_template(survey_id)
    patterns = load_rules(rules_path)

    if survey is None:
        print(f"No survey found with id {survey_id}")
        return {}

    # Handle surveys where questions are under 'template'
    questions = survey.get("questions") or survey.get("template", {}).get("questions", [])

    results = []

    for response in data_source.iter_responses(survey_id):
        respondent_id = response["respondent_id"]

        for q in questions:
            qid = q.get("question_id") or q.get("id")
            q_text = q.get("text") or q.get("question") or ""
            answer = response["answers"].get(qid, "")

            flags = set()
            flags.update(detect_from_question(q_text, patterns))
            flags.update(detect_sensitive_data(answer, patterns))

            results.append({
                "respondent_id": respondent_id,
                "question_id": qid,
                "flags": list(flags)
            })

    return {
        "survey_id": survey_id,
        "results": results
    }
