# src/anonymization/hybrid_detector.py
"""
hybrid_detector.py

combines the regex PII detector with the AI detector into a single unified assessment per field

Static layer: fast, deterministic, catches known patterns (email, phone, etc.)
AI layer: semantic, context-aware, catches risk from field combinations and things regex can't see (e.g. "nurse in Manchester, age 42")

The merged result always takes the HIGHER risk level of the two assessments, so neither layer can silently under-report PII.
"""

import json
import re
from typing import Optional

from src.anonymization.ai_detector import AIDetector, RISK_LEVELS, risk_rank


# Map static PII labels and their default risk level with recommended action
# These are the floors, AI assessment can only raise them, never lower
STATIC_RISK_MAP = {
    "EMAIL":        {"risk_level": "HIGH",   "recommended_action": "pseudonymize"},
    "PHONE":        {"risk_level": "HIGH",   "recommended_action": "pseudonymize"},
    "ADDRESS":      {"risk_level": "HIGH",   "recommended_action": "suppress"},
    "NAME_KEYWORD": {"risk_level": "MEDIUM", "recommended_action": "pseudonymize"},
    "DATE":         {"risk_level": "MEDIUM", "recommended_action": "generalize"},
}

DEFAULT_STATIC = {"risk_level": "NONE", "recommended_action": "keep"}


class HybridDetector:
    def __init__(
        self,
        patterns_path: str = None,
        patterns: dict = None,
        ai_detector: Optional[AIDetector] = None,
        use_ai: bool = True,
        model: str = "llama3.1:8b",
    ):
        """
        :param patterns_path: Path to pii_patterns.json
        :param patterns:      Patterns dict (alternative to patterns_path)
        :param ai_detector:   Pre-built AIDetector instance (optional)
        :param use_ai:        Set False to run static-only (useful for testing)
        :param model:         Ollama model to use if ai_detector is not provided
        """
        if patterns:
            self.patterns = patterns
        elif patterns_path:
            with open(patterns_path, "r", encoding="utf-8") as f:
                self.patterns = json.load(f)
        else:
            raise ValueError("Provide either patterns_path or patterns dict.")

        self.use_ai = use_ai
        self.ai = ai_detector if ai_detector is not None else AIDetector(model=model)

    def assess_record(
        self,
        record: dict,
        questions: list = None,
        survey_context: dict = None,
    ) -> dict:
        
        # hybrid assessment of a single survey response record.
        answers = record.get("answers", {})
        respondent_id = record.get("respondent_id", "unknown")

        # static pass, should always run
        static_results = self._run_static(answers, questions)

        # ai pass, should only run when enabled
        ai_assessments = {}
        if self.use_ai and answers:
            ai_result = self.ai.assess_record(
                record,
                questions=questions,
                survey_context=survey_context,
            )
            ai_assessments = ai_result.get("assessments", {})

        # merging static and ai fields
        fields = {}
        for qid in answers:
            static = static_results.get(qid, {
                "flags": [], "risk_level": "NONE", "recommended_action": "keep"
            })
            ai = ai_assessments.get(qid, {
                "risk_level": "NONE", "pii_types": [], "reasoning": "", "recommended_action": "keep"
            })

            s_risk = static.get("risk_level", "NONE")
            a_risk = ai.get("risk_level", "NONE")

            # Take the higher of the two risk levels
            if risk_rank(s_risk) >= risk_rank(a_risk):
                final_risk = s_risk
                action = static.get("recommended_action", "keep")
            else:
                final_risk = a_risk
                action = ai.get("recommended_action", "keep")

            fields[qid] = {
                "static_flags":       static.get("flags", []),
                "static_risk":        s_risk,
                "ai_risk":            a_risk,
                "ai_pii_types":       ai.get("pii_types", []),
                "ai_reasoning":       ai.get("reasoning", ""),
                "final_risk":         final_risk,
                "recommended_action": action,
            }

        overall_risk = max(
            (f["final_risk"] for f in fields.values()),
            key=risk_rank,
            default="NONE",
        )

        return {
            "respondent_id": respondent_id,
            "overall_risk":  overall_risk,
            "fields":        fields,
        }

    def _run_static(self, answers: dict, questions: list = None) -> dict:
        q_text_map = {}
        if questions:
            for q in questions:
                qid = q.get("question_id") or q.get("id")
                qtext = q.get("text") or q.get("question_text") or ""
                if qid:
                    q_text_map[qid] = qtext

        results = {}
        for qid, value in answers.items():
            flags = set()
            value_str = str(value) if value is not None else ""

            # match against answer value
            for label, pattern in self.patterns.items():
                if re.search(pattern, value_str, re.IGNORECASE):
                    flags.add(label)

            # match against question text (catches "What is your name?" etc.)
            qtext = q_text_map.get(qid, "")
            for label, pattern in self.patterns.items():
                if re.search(pattern, qtext, re.IGNORECASE):
                    flags.add(label)

            # derive static risk from the highest-risk flag found
            best_risk = "NONE"
            best_action = "keep"
            for flag in flags:
                mapping = STATIC_RISK_MAP.get(flag, DEFAULT_STATIC)
                if risk_rank(mapping["risk_level"]) > risk_rank(best_risk):
                    best_risk = mapping["risk_level"]
                    best_action = mapping["recommended_action"]

            results[qid] = {
                "flags":              list(flags),
                "risk_level":         best_risk,
                "recommended_action": best_action,
            }

        return results