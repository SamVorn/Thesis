# src/anonymization/detector.py
import re
import json

# Risk weights per PII category (higher = more sensitive)
PII_RISK_WEIGHTS = {
    "EMAIL":             3,
    "PHONE":             3,
    "ADDRESS":           3,
    "SSN":               5,
    "GOVERNMENT_ID":     4,
    "FINANCIAL":         4,
    "HEALTH":            4,
    "BIOMETRIC":         5,
    "DEMOGRAPHIC":       3,
    "CRIMINAL":          4,
    "ONLINE_IDENTIFIER": 3,
    "LOCATION":          2,
    "VEHICLE":           2,
    "DATE":              4,   
                              
    "DATE_KEYWORD":      4,   
                              
    "NAME_KEYWORD":      2,
    "ZIP_CODE":          4,   
                              
    "CONTACT_KEYWORD":   2,
}
DEFAULT_RISK_WEIGHT = 2

SCORE_THRESHOLDS = {
    "suppress":     10,   # score >= 10  direct identifier, highest risk
    "pseudonymize":  5,   # score >=  5  medium risk, tokenize safely
    "generalize":    2,   # score >=  2  low risk, reduce precision
    "none":          0,   # score <   2  clean, no action
}

PER_FIELD_THRESHOLDS = {
    "suppress":      5,  
    "pseudonymize":  4,   
    "generalize":    1,   
    "none":          0,
}


def _recommend_strategy_from_weight(weight_sum: float) -> str:
    """
    ADDED: per-field strategy lookup based on raw weight sum, for use by
    assess_record() (single-response scoring). See PER_FIELD_THRESHOLDS
    comment above for why this is separate from recommend_strategy().
    """
    if weight_sum >= PER_FIELD_THRESHOLDS["suppress"]:
        return "suppress"
    elif weight_sum >= PER_FIELD_THRESHOLDS["pseudonymize"]:
        return "pseudonymize"
    elif weight_sum >= PER_FIELD_THRESHOLDS["generalize"]:
        return "generalize"
    return "none"

SCORE_TO_RISK = {
    "suppress":     "HIGH",
    "pseudonymize": "MEDIUM",
    "generalize":   "LOW",
    "none":         "NONE",
}


MEDICAL_LABELS = {"HEALTH"}

STRICT_LABELS = {
    "ADDRESS",           # home/work/previous address
    "EMAIL",             # all email addresses
    "PHONE",             # all phone numbers
    "NAME_KEYWORD",      # named persons (spouse, children, beneficiary, emergency contact)
    "ONLINE_IDENTIFIER", # LinkedIn, Facebook, Twitter, Instagram, IP address
    "GOVERNMENT_ID",     # SSN, passport, driver's license, student/employee/tax ID
    "CONTACT_KEYWORD",   # emergency contacts, nearest relative, work contact info
    "VEHICLE",           # vehicle registration (slight over-flag on make/model → RELAXED)
    "BIOMETRIC",         # fingerprint, face ID, biometric enrollment
}


MEDICAL_SCORE_TO_RISK = {
    "suppress":     "HIGH",
    "pseudonymize": "MEDICAL_MODERATE",
    "generalize":   "MEDICAL_RELAXED",
    "none":         "NONE",
}


class PIIDetector:


    def __init__(self, patterns_path: str = None, patterns: dict = None):
        if patterns:
            self.patterns = patterns
        elif patterns_path:
            with open(patterns_path, "r", encoding="utf-8") as f:
                self.patterns = json.load(f)
        else:
            raise ValueError("Provide either patterns_path or patterns dict.")

    def detect_in_answer(self, answer: str) -> list:
        # return PII labels found in a text answer
        return [
            label for label, pattern in self.patterns.items()
            if re.search(pattern, str(answer), re.IGNORECASE)
        ]

    def detect_from_question_text(self, question_text: str) -> list:
        # return PII labels found in a question string
        return [
            label for label, pattern in self.patterns.items()
            if re.search(pattern, str(question_text), re.IGNORECASE)
        ]

    def score_field(self, detected_labels: list, hit_count: int, total_responses: int) -> float:
        """
        Score = sum(risk_weights) * (hit_count / total_responses) * 10
        Range: 0 - 50+
        """
        if not detected_labels or total_responses == 0:
            return 0.0
        weight_sum = sum(PII_RISK_WEIGHTS.get(l, DEFAULT_RISK_WEIGHT) for l in detected_labels)
        return round(weight_sum * (hit_count / total_responses) * 10, 2)

    def recommend_strategy(self, score: float) -> str:
        if score >= SCORE_THRESHOLDS["suppress"]:
            return "suppress"
        elif score >= SCORE_THRESHOLDS["pseudonymize"]:
            return "pseudonymize"
        elif score >= SCORE_THRESHOLDS["generalize"]:
            return "generalize"
        return "none"

    # UPDATED: now takes the answer's own flags and the question's flags
    # separately, instead of a merged set. See fix note below.
    def _risk_from_labels(self, answer_labels: list = None, topic_labels: list = None) -> str:

        answer_labels = answer_labels or []
        topic_labels = topic_labels or []

        if answer_labels:

            if any(l in STRICT_LABELS for l in answer_labels) or \
               any(l in STRICT_LABELS for l in topic_labels):
                return "HIGH"

            weight_sum = sum(PII_RISK_WEIGHTS.get(l, DEFAULT_RISK_WEIGHT) for l in answer_labels)
            strategy = _recommend_strategy_from_weight(weight_sum)
            is_medical = any(l in MEDICAL_LABELS for l in answer_labels)
            table = MEDICAL_SCORE_TO_RISK if is_medical else SCORE_TO_RISK
            return table.get(strategy, "NONE")

        if topic_labels:

            if any(l in STRICT_LABELS for l in topic_labels):
                return "HIGH"
            is_medical = any(l in MEDICAL_LABELS for l in topic_labels)
            if is_medical:
                return "MEDICAL_RELAXED"
            weight_sum = sum(PII_RISK_WEIGHTS.get(l, DEFAULT_RISK_WEIGHT) for l in topic_labels)
            strategy = _recommend_strategy_from_weight(weight_sum)
            return SCORE_TO_RISK.get(strategy, "NONE")

        return "NONE"

    def assess_record(
        self,
        record: dict,
        questions: list = None,
        survey_context: dict = None,
    ) -> dict:
        answers = record.get("answers", {})
        respondent_id = record.get("respondent_id", "unknown")

        if not answers:
            return {"respondent_id": respondent_id, "fields": {}, "overall_risk": "NONE"}

        # Build question text map for question-level pattern matching
        q_text_map = {}
        if questions:
            q_text_map = {
                (q.get("question_id") or q.get("id")): (q.get("text") or q.get("question_text") or "")
                for q in questions
                if q.get("question_id") or q.get("id")
            }

        fields = {}
    
        risk_ranks = {
            "NONE": 0,
            "LOW": 1,
            "MEDICAL_RELAXED": 1,
            "MEDIUM": 2,
            "MEDICAL_MODERATE": 2,
            "HIGH": 3,
            "CRITICAL": 4,
        }
        overall_risk = "NONE"

        for qid, answer in answers.items():
            q_text = q_text_map.get(qid, "")

            # Scan both question text and answer text
            q_flags = self.detect_from_question_text(q_text)
            a_flags = self.detect_in_answer(str(answer))
            all_flags = list(set(q_flags + a_flags))  # reported for transparency

            hit_count = 1 if all_flags else 0
            score = self.score_field(all_flags, hit_count, total_responses=1)
            static_risk = self._risk_from_labels(answer_labels=a_flags, topic_labels=q_flags)

            fields[qid] = {
                "static_flags": all_flags,
                "static_risk":  static_risk,
                "ai_risk":      "NONE",   # regex-only: no AI pass
                "ai_pii_types": [],       # regex-only: no AI pass
                "ai_reasoning": "",       # regex-only: no AI pass
                "final_risk":   static_risk,
            }

            if risk_ranks.get(static_risk, 0) > risk_ranks.get(overall_risk, 0):
                overall_risk = static_risk

        return {
            "respondent_id": respondent_id,
            "fields":        fields,
            "overall_risk":  overall_risk,
        }

    def analyse_survey(self, questions: list, responses: list) -> list:
        
        total = len(responses)
        field_data = {}
        for q in questions:
            qid    = q.get("question_id") or q.get("id")
            q_text = q.get("text") or q.get("question_text") or ""
            field_data[qid] = {
                "question_id":     qid,
                "question_text":   q_text,
                "detected_labels": set(self.detect_from_question_text(q_text)),
                "hit_count":       0,
                "sample_hits":     [],
            }

        for resp in responses:
            rid     = resp.get("respondent_id", "?")
            answers = resp.get("answers", {})
            for qid, answer in answers.items():
                if qid not in field_data:
                    field_data[qid] = {
                        "question_id":     qid,
                        "question_text":   "",
                        "detected_labels": set(),
                        "hit_count":       0,
                        "sample_hits":     [],
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