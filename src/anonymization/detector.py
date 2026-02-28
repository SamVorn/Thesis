# src/anonymization/detector.py
import re
import json

# Risk weights per PII category (higher = more sensitive)
PII_RISK_WEIGHTS = {
    "EMAIL":        3,
    "PHONE":        3,
    "ADDRESS":      3,
    "DATE":         2,
    "NAME_KEYWORD": 2,
}
DEFAULT_RISK_WEIGHT = 2

# Score to strategy thresholds
SCORE_THRESHOLDS = {
    "suppress":     10,   # score >= 10  direct identifier, highest risk
    "pseudonymize":  5,   # score >=  5  medium risk, tokenize safely
    "generalize":    2,   # score >=  2  low risk, reduce precision
    "none":          0,   # score <   2  clean, no action
}


class PIIDetector:
    """
    Objective:
    Detect PII in survey responses
    Score each field by risk and its frequency
    recommend an anonymization strategy.
    """

    def __init__(self, patterns_path: str = None, patterns: dict = None):
        if patterns:
            self.patterns = patterns
        elif patterns_path:
            with open(patterns_path, "r", encoding="utf-8") as f:
                self.patterns = json.load(f)
        else:
            raise ValueError("Provide either patterns_path or patterns dict.")

    # detection
    def detect_in_answer(self, answer: str) -> list:
        # return PII labels found in a text answer
        return [
            label for label, pattern in self.patterns.items()
            if re.search(pattern, str(answer), re.IGNORECASE)
        ]

    def detect_from_question_text(self, question_text: str) -> list:
        # return PII labels from question
        return [
            label for label, pattern in self.patterns.items()
            if re.search(pattern, str(question_text), re.IGNORECASE)
        ]

    # scoring
    def score_field(self, detected_labels: list, hit_count: int, total_responses: int) -> float:
        """
        Score = sum(risk_weights) * (hit_count / total_responses) * 10
        Range: 0 - 30+
        """
        if not detected_labels or total_responses == 0:
            return 0.0
        weight_sum = sum(PII_RISK_WEIGHTS.get(l, DEFAULT_RISK_WEIGHT) for l in detected_labels)
        return round(weight_sum * (hit_count / total_responses) * 10, 2)

    # recs
    def recommend_strategy(self, score: float) -> str:
        if score >= SCORE_THRESHOLDS["suppress"]:
            return "suppress"
        elif score >= SCORE_THRESHOLDS["pseudonymize"]:
            return "pseudonymize"
        elif score >= SCORE_THRESHOLDS["generalize"]:
            return "generalize"
        return "none"

    # analysis
    def analyse_survey(self, questions: list, responses: list) -> list:
        """
        Obj:
        Detect + score + recommend across all questions and responses
        """
        total = len(responses)
        field_data = {}
        for q in questions:
            qid    = q.get("question_id") or q.get("id")
            q_text = q.get("text") or q.get("question_text") or ""
            field_data[qid] = {
                "question_id":    qid,
                "question_text":  q_text,
                "detected_labels": set(self.detect_from_question_text(q_text)),
                "hit_count":      0,
                "sample_hits":    [],
            }

        # scan responses
        for resp in responses:
            rid     = resp.get("respondent_id", "?")
            answers = resp.get("answers", {})
            for qid, answer in answers.items():
                if qid not in field_data:
                    field_data[qid] = {
                        "question_id":    qid,
                        "question_text":  "",
                        "detected_labels": set(),
                        "hit_count":      0,
                        "sample_hits":    [],
                    }
                found = self.detect_in_answer(str(answer))
                if found:
                    field_data[qid]["detected_labels"].update(found)
                    field_data[qid]["hit_count"] += 1
                    if len(field_data[qid]["sample_hits"]) < 3:
                        field_data[qid]["sample_hits"].append((rid, str(answer)))

        results = []
        for fd in field_data.values():
            labels = list(fd["detected_labels"])
            score  = self.score_field(labels, fd["hit_count"], total)
            results.append({
                "question_id":          fd["question_id"],
                "question_text":        fd["question_text"],
                "detected_labels":      labels,
                "hit_count":            fd["hit_count"],
                "total_responses":      total,
                "score":                score,
                "recommended_strategy": self.recommend_strategy(score),
                "sample_hits":          fd["sample_hits"],
            })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results

# keeping the simple detector from old tests in case 
class SimpleDetector:
    PII_KEYWORDS = ["name", "email", "phone", "age", "address"]

    def detect_pii(self, answers: dict) -> list:
        return [k for k in answers if any(kw in k.lower() for kw in self.PII_KEYWORDS)]