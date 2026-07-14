# src/anonymization/anonymization_pipeline.py
"""
anonymization_pipeline.py
    Five Phases:
        1. detect()                 detect PII and apply scoring to every field
        2. review()                 print to the terminal for review
        3. confirm()                accept or override each field anonymization through terminal
        4. run()                    apply anonymization and store anonymized responses
        5. save_detection_results() persist full detection output alongside surveys + anonymized data

Base pipeline class used by all three backends (Mongo, SQL, File).

two detector types
  1 HybridDetector: uses assess_record() for full static + AI assessment
  2 SimpleDetector: falls back to detect_pii() for backward compatibility
"""



import hashlib
import re
from datetime import datetime, timezone
from typing import Optional

from src.anonymization.anonymizer import (
    apply_strategy,
    STRATEGY_SUPPRESS,
    STRATEGY_PSEUDONYMIZE,
    STRATEGY_GENERALIZE,
    STRATEGY_NONE,
)


RISK_TO_STRATEGY = {
    "CRITICAL":         STRATEGY_SUPPRESS,
    "HIGH":             STRATEGY_SUPPRESS,
    "MEDICAL_MODERATE": STRATEGY_PSEUDONYMIZE,
    "MEDIUM":           STRATEGY_GENERALIZE,
    "MEDICAL_RELAXED":  STRATEGY_GENERALIZE,
    "LOW":              STRATEGY_NONE,
    "NONE":             STRATEGY_NONE,
}

RISK_DISPLAY_ORDER = [
    "CRITICAL",
    "HIGH",
    "MEDICAL_MODERATE",
    "MEDIUM",
    "MEDICAL_RELAXED",
    "LOW",
    "NONE",
]


class AnonymizationPipeline:

    def __init__(self, source, detector):
        self.source = source
        self.detector = detector

    # infers a short label ("hybrid" | "ai" | "regex") from the detector class name
    # used to tag each detection results document so experiment runs are distinguishable in storage
    def _detector_type(self) -> str:
        name = type(self.detector).__name__.lower()
        if "hybrid" in name:
            return "hybrid"
        if "ai" in name:
            return "ai"
        if "simple" in name:
            return "regex"
        if "pii" in name:
            return "regex"
        return name

    def detect(self, survey_id: str = None) -> list:
        # Load the survey template + all responses, run the detector across
        # all responses, aggregate field-level risk, and return a results list.
        template = self.source.get_survey_template(survey_id)
        if not template:
            return []

        questions = template.get("questions", [])
        responses = list(self.source.iter_responses(survey_id))

        if not responses:
            return []

        # Initialise per-field accumulators keyed by question_id
        field_data = {}
        for q in questions:
            qid = q.get("question_id") or q.get("id")
            if qid:
                field_data[qid] = {
                    "question_id":   qid,
                    "question_text": q.get("text") or q.get("question_text") or "",
                    "static_flags":  set(),
                    "static_risk":   "NONE",
                    "ai_risk":       "NONE",
                    "ai_pii_types":  [],
                    "ai_reasoning":  "",
                    "final_risk":    "NONE",
                    "hit_count":     0,
                    "total":         len(responses),
                    "sample_hits":   [],
                }

        from src.anonymization.ai_detector import risk_rank

        for response in responses:
            rid = response.get("respondent_id", "?")

            if hasattr(self.detector, "assess_record"):
                raw = self.detector.assess_record(response, questions=questions)

                normalised = self._normalise_assessment(raw)

                for qid, field_info in normalised.items():
                    if qid not in field_data:
                        field_data[qid] = {
                            "question_id":   qid,
                            "question_text": "",
                            "static_flags":  set(),
                            "static_risk":   "NONE",
                            "ai_risk":       "NONE",
                            "ai_pii_types":  [],
                            "ai_reasoning":  "",
                            "final_risk":    "NONE",
                            "hit_count":     0,
                            "total":         len(responses),
                            "sample_hits":   [],
                        }

                    fd = field_data[qid]
                    fr = field_info.get("final_risk", "NONE")

                    # Escalate stored risk if this response is higher.
                    if risk_rank(fr) > risk_rank(fd["final_risk"]):
                        fd["final_risk"]   = fr
                        fd["static_risk"]  = field_info.get("static_risk", "NONE")
                        fd["ai_risk"]      = field_info.get("ai_risk", "NONE")
                        fd["ai_pii_types"] = field_info.get("ai_pii_types", [])
                        fd["ai_reasoning"] = field_info.get("ai_reasoning", "")

                    fd["static_flags"].update(field_info.get("static_flags", []))

                    if fr != "NONE":
                        fd["hit_count"] += 1
                        answer_val = response.get("answers", {}).get(qid, "")
                        if len(fd["sample_hits"]) < 3:
                            fd["sample_hits"].append((rid, str(answer_val)))

        # Build final results list
        results = []
        for fd in field_data.values():
            final_risk = fd["final_risk"]
            results.append({
                "question_id":          fd["question_id"],
                "question_text":        fd["question_text"],
                "static_flags":         list(fd["static_flags"]),
                "static_risk":          fd["static_risk"],
                "ai_risk":              fd["ai_risk"],
                "ai_pii_types":         fd["ai_pii_types"],
                "ai_reasoning":         fd["ai_reasoning"],
                "final_risk":           final_risk,
                "recommended_strategy": RISK_TO_STRATEGY.get(final_risk, STRATEGY_NONE),
                "hit_count":            fd["hit_count"],
                "total_responses":      fd["total"],
                "sample_hits":          fd["sample_hits"],
            })

        return results

    @staticmethod
    def _normalise_assessment(raw: dict) -> dict:
        # HybridDetector shape return as-is
        if "fields" in raw:
            return raw["fields"]

        # AIDetector shape — remap keys to match HybridDetector field names
        if "assessments" in raw:
            normalised = {}
            for qid, entry in raw["assessments"].items():
                ai_risk = entry.get("risk_level", "NONE")
                normalised[qid] = {
                    "static_flags": [],         # AI-only: no regex flags available
                    "static_risk":  "NONE",     # AI-only: no regex score available
                    "ai_risk":      ai_risk,
                    "ai_pii_types": entry.get("pii_types", []),
                    "ai_reasoning": entry.get("reasoning", ""),
                    "final_risk":   ai_risk,    # AI-only: final = ai since no static
                }
            return normalised

        
        return {}

    def review(self, analysis: list) -> None:
        # Print a summary of detected PII fields
        print("\n PII Detection Results")
        if not analysis:
            print("  No PII detected.")
            return

        for field in analysis:
            risk  = field.get("final_risk", "NONE")
            strat = field.get("recommended_strategy", "none")
            qid   = field.get("question_id", "?")
            qtext = field.get("question_text", "")
            hits  = field.get("hit_count", 0)
            total = field.get("total_responses", 0)

            print(f"\n  [{risk:17s}]  {qid}  —  \"{qtext}\"")
            print(f"             Static flags : {field.get('static_flags') or 'none'}")
            print(f"             AI types     : {field.get('ai_pii_types') or 'none'}")
            print(f"             AI reasoning : {field.get('ai_reasoning') or '—'}")
            print(f"             Responses    : {hits}/{total} flagged")
            print(f"             Recommended  : {strat}")

            for rid, sample in field.get("sample_hits", []):
                print(f"               sample → respondent {rid}: {sample!r}")

    def confirm(self, analysis: list) -> list:

        # Interactively ask the user to accept or override the recommended strategy for each flagged field

        valid = {"suppress", "pseudonymize", "generalize", "none", ""}
        confirmed = []

        print("\n Strategy Confirmation")
        print("  Press ENTER to accept recommendation, or type an alternative:")
        print("  Options: suppress | pseudonymize | generalize | none\n")

        for field in analysis:
            rec  = field.get("recommended_strategy", "none")
            qid  = field.get("question_id", "?")
            risk = field.get("final_risk", "NONE")

            while True:
                raw = input(f"  [{risk}] {qid}  (recommended: {rec}): ").strip().lower()
                if raw == "":
                    chosen = rec
                    break
                if raw in valid - {""}:
                    chosen = raw
                    break
                print(f"    Invalid. Choose from: suppress, pseudonymize, generalize, none")

            confirmed.append({**field, "chosen_strategy": chosen})
        return confirmed

    def run(self, survey_id: str = None, confirmed_analysis: list = None) -> list:

        # Apply anonymization to all responses using the confirmed strategies.
        if not confirmed_analysis:
            return []

        # chosen strategy map
        strategy_map = {
            f["question_id"]: f.get("chosen_strategy", "none")
            for f in confirmed_analysis
        }

        # static_flags map for apply_strategy label hints
        flags_map = {
            f["question_id"]: f.get("static_flags", [])
            for f in confirmed_analysis
        }

        anonymized_records = []

        for response in self.source.iter_responses(survey_id):
            rid     = response.get("respondent_id")
            answers = response.get("answers", {}).copy()

            for qid, value in answers.items():
                strategy = strategy_map.get(qid, "none")
                labels   = flags_map.get(qid, [])
                answers[qid] = apply_strategy(qid, value, strategy, detected_labels=labels)

            anonymized_records.append({
                "respondent_id": rid,
                "answers":       answers,
            })

        self.save_detection_results(survey_id, confirmed_analysis)

        return anonymized_records

    def save_detection_results(self, survey_id: str, confirmed_analysis: list) -> None:
        pass  # overridden per backend in run_pipeline.py

    # shared document builder called by every backend's save_detection_results()
    # centralises the serialisation logic so all three backends store identical document shapes
    def _build_results_document(
        self, survey_id: str, confirmed_analysis: list
    ) -> dict:
        """
        Build the standardised detection results document.
        Called by subclass save_detection_results() implementations.
        """
        total = confirmed_analysis[0].get("total_responses", 0) if confirmed_analysis else 0

        fields = []
        for field in confirmed_analysis:
            # sample_hits contains (respondent_id, answer) tuples — serialise to dicts
            raw_hits = field.get("sample_hits", [])
            sample_hits = [
                {"respondent_id": str(h[0]), "answer": str(h[1])}
                if isinstance(h, (list, tuple)) else h
                for h in raw_hits
            ]

            fields.append({
                "question_id":          field.get("question_id"),
                "question_text":        field.get("question_text", ""),
                "static_flags":         field.get("static_flags", []),
                "static_risk":          field.get("static_risk", "NONE"),
                "ai_risk":              field.get("ai_risk", "NONE"),
                "ai_pii_types":         field.get("ai_pii_types", []),
                "ai_reasoning":         field.get("ai_reasoning", ""),
                "final_risk":           field.get("final_risk", "NONE"),
                "recommended_strategy": field.get("recommended_strategy", "none"),
                "chosen_strategy":      field.get("chosen_strategy", "none"),
                "hit_count":            field.get("hit_count", 0),
                "total_responses":      field.get("total_responses", total),
                "sample_hits":          sample_hits,
            })

        return {
            "survey_id":       survey_id,
            "detector_type":   self._detector_type(),
            "run_timestamp":   datetime.now(timezone.utc).isoformat(),
            "total_responses": total,
            "fields":          fields,
        }