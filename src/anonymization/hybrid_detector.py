# src/anonymization/hybrid_detector.py
"""
hybrid_detector.py
Combines regex-based detection (PIIDetector) with AI-based contextual
assessment (AIDetector) into a single unified detector.

Detection flow per record:
  1. Regex pass  — PIIDetector scans question text and answer text against
                   pii_patterns.json, producing static flags and a risk score.
                   Fields flagged HEALTH are routed to MEDICAL_MODERATE /
                   MEDICAL_RELAXED instead of plain MEDIUM / LOW.
  2. AI pass     — AIDetector sends the full record to Ollama for contextual
                   risk assessment, producing risk levels and reasoning.
                   This includes medical fields — see note below.
  3. Merge       — static flags and AI risk are combined; the higher of the
                   two risk signals wins (conservative / escalation-only merge)

The hybrid approach catches what regex misses (context, combinations, semantics)
while keeping regex as a fast, reliable baseline that doesn't depend on Ollama.

If Ollama is unavailable, HybridDetector falls back to regex-only and continues
without crashing — making it safe to run in environments without a GPU.


Output of assess_record() matches the shape expected by anonymization_pipeline.py:

"""

import json
import re
from typing import Optional

from src.anonymization.detector import (
    PIIDetector,
    PII_RISK_WEIGHTS,
    DEFAULT_RISK_WEIGHT,
    SCORE_THRESHOLDS,
    PER_FIELD_THRESHOLDS,
    _recommend_strategy_from_weight,
    MEDICAL_LABELS,
    STRICT_LABELS,  
)
from src.anonymization.ai_detector import AIDetector, RISK_LEVELS, risk_rank, OllamaUnavailableError

OLLAMA_BASE_URL = "http://localhost:11434"


def _score_to_risk(answer_labels: list = None, topic_labels: list = None) -> str:
    """
    Convert detected regex labels to a RISK_LEVELS label, medical-aware.
    See fix note above for why answer_labels and topic_labels are separate.
    """
    answer_labels = answer_labels or []
    topic_labels = topic_labels or []

    from src.anonymization.detector import MEDICAL_SCORE_TO_RISK, SCORE_TO_RISK

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


class HybridDetector:


    def __init__(
        self,
        patterns_path: str = None,
        patterns: dict = None,
        use_ai: bool = True,
        model: str = "llama3.1:8b",
        base_url: str = OLLAMA_BASE_URL,
        timeout: int = 120,
        # batch_size passed through to AIDetector so the AI pass
        # chunks large surveys the same way as the standalone AIDetector
        batch_size: int = 20,
    ):

        # Regex detector
        self.regex = PIIDetector(patterns_path=patterns_path, patterns=patterns)

        self.use_ai = use_ai
        self.ai: Optional[AIDetector] = (
            AIDetector(model=model, base_url=base_url, timeout=timeout, batch_size=batch_size)
            if use_ai else None
        )

    def is_available(self) -> bool:
        """Check if Ollama is reachable (mirrors AIDetector.is_available)."""
        if self.ai is None:
            return False
        return self.ai.is_available()

    def assess_record(
        self,
        record: dict,
        questions: list = None,
        survey_context: dict = None,
    ) -> dict:

        answers = record.get("answers", {})
        respondent_id = record.get("respondent_id", "unknown")

        if not answers:
            return {
                "respondent_id": respondent_id,
                "fields": {},
                "overall_risk": "NONE",
            }

        # Build question text map for regex question-level detection
        q_text_map = self._build_q_text_map(questions)
        total_responses = 1  # per-record scoring; pipeline aggregates across records

        regex_results = {}
        for qid, answer in answers.items():
            q_text = q_text_map.get(qid, "")

            # Detect from question text and answer text separately
            q_flags  = self.regex.detect_from_question_text(q_text)
            a_flags  = self.regex.detect_in_answer(str(answer))
            all_flags = list(set(q_flags + a_flags))  # reported for transparency

            hit_count = 1 if all_flags else 0
            score = self.regex.score_field(all_flags, hit_count, total_responses)
            static_risk = _score_to_risk(answer_labels=a_flags, topic_labels=q_flags)

            regex_results[qid] = {
                "static_flags": all_flags,
                "static_risk":  static_risk,
                "score":        score,
            }

        ai_results = {}
        if self.use_ai and self.ai is not None:
            try:
                ai_response = self.ai.assess_record(
                    record, questions=questions, survey_context=survey_context
                )
                ai_results = ai_response.get("assessments", {})
            except OllamaUnavailableError as e:
                print(f"[HybridDetector] Ollama unavailable, using regex only: {e}")
            except Exception as e:
                print(f"[HybridDetector] AI pass error, using regex only: {e}")

        fields = {}
        for qid, regex_data in regex_results.items():
            static_risk = regex_data["static_risk"]
            ai_entry    = ai_results.get(qid, {})
            ai_risk     = ai_entry.get("risk_level", "NONE")

            # Take whichever is higher
            final_risk = (
                static_risk if risk_rank(static_risk) >= risk_rank(ai_risk)
                else ai_risk
            )

            fields[qid] = {
                "static_flags": regex_data["static_flags"],
                "static_risk":  static_risk,
                "ai_risk":      ai_risk,
                "ai_pii_types": ai_entry.get("pii_types", []),
                "ai_reasoning": ai_entry.get("reasoning", ""),
                "final_risk":   final_risk,
            }

        overall_risk = max(
            (f["final_risk"] for f in fields.values()),
            key=risk_rank,
            default="NONE",
        )

        return {
            "respondent_id": respondent_id,
            "fields":        fields,
            "overall_risk":  overall_risk,
        }


    @staticmethod
    def _build_q_text_map(questions: Optional[list]) -> dict:
        if not questions:
            return {}
        return {
            (q.get("question_id") or q.get("id")): (q.get("text") or q.get("question_text") or "")
            for q in questions
            if q.get("question_id") or q.get("id")
        }