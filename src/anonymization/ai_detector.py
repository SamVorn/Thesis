# src/anonymization/ai_detector.py
"""
AI-powered PII detector using a local Ollama model for contextual risk assessment.

Runs entirely on-premise — no data leaves the machine.

Recommended models (run `ollama pull <model>` to install):
  - llama3.1:8b      → best balance of quality vs. speed (default)
  - mistral:7b       → slightly faster, slightly weaker reasoning
  - llama3.1:70b     → best quality, requires ~40GB RAM or a GPU

Complements static regex detection with semantic understanding:
  - Understands context (e.g. "John" in a fiction survey vs. a medical survey)
  - Detects re-identification risk from field combinations
  - Assigns risk levels: NONE, LOW, MEDIUM, HIGH, CRITICAL
  - Recommends anonymization action per field
"""

import json
import re
import urllib.request
import urllib.error
from typing import Optional


# Risk level ordering for comparisons
RISK_LEVELS = ["NONE", "LOW", "MEDIUM", "HIGH", "CRITICAL"]

# Default Ollama endpoint — change if running Ollama on a different port
OLLAMA_BASE_URL = "http://localhost:11434"


def risk_rank(level: str) -> int:
    """Return numeric rank of a risk level string (higher = more risky)."""
    try:
        return RISK_LEVELS.index(level.upper())
    except ValueError:
        return 0


class AIDetector:
    """
    Uses a local Ollama model to contextually evaluate PII risk in survey responses.

    All inference runs locally — no API keys, no external calls, no data egress.

    Example:
        detector = AIDetector(model="llama3.1:8b")
        result = detector.assess_record(record, questions=questions)
    """

    def __init__(
        self,
        model: str = "llama3.1:8b",
        base_url: str = OLLAMA_BASE_URL,
        timeout: int = 120,
    ):
        """
        :param model:    Ollama model tag. Run `ollama list` to see installed models.
        :param base_url: Ollama server URL (default: http://localhost:11434)
        :param timeout:  Request timeout in seconds. Increase for large/slow models.
        """
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def assess_record(
        self,
        record: dict,
        questions: list = None,
        survey_context: dict = None,
    ) -> dict:
        """
        Assess all answers in a record in a single model call.

        Passing all fields together lets the model detect re-identification risk
        from field *combinations* (e.g. age + city + job title together are
        more dangerous than any single field alone).

        Returns:
        {
            "respondent_id": str,
            "assessments": {
                "<question_id>": {
                    "risk_level":         "NONE|LOW|MEDIUM|HIGH|CRITICAL",
                    "pii_types":          ["NAME", "EMAIL", ...],
                    "reasoning":          str,
                    "recommended_action": "keep|generalize|pseudonymize|suppress"
                }
            },
            "overall_risk": "NONE|LOW|MEDIUM|HIGH|CRITICAL"
        }
        """
        answers = record.get("answers", {})
        respondent_id = record.get("respondent_id", "unknown")

        if not answers:
            return {"respondent_id": respondent_id, "assessments": {}, "overall_risk": "NONE"}

        q_text_map = self._build_q_text_map(questions)
        prompt = self._build_batch_prompt(answers, q_text_map, survey_context)

        try:
            raw = self._call_ollama(prompt)
            assessments = self._parse_batch_response(raw, answers)
        except OllamaUnavailableError as e:
            print(f"[AIDetector] Ollama unavailable: {e}")
            assessments = self._fallback_assessments(answers, reason=str(e))
        except Exception as e:
            print(f"[AIDetector] Unexpected error during assessment: {e}")
            assessments = self._fallback_assessments(answers, reason=str(e))

        overall_risk = max(
            (v.get("risk_level", "NONE") for v in assessments.values()),
            key=risk_rank,
            default="NONE",
        )

        return {
            "respondent_id": respondent_id,
            "assessments": assessments,
            "overall_risk": overall_risk,
        }

    def assess_pii_risk(
        self,
        question_text: str,
        answer: str,
        question_id: str = "",
        survey_context: dict = None,
        all_answers: dict = None,
    ) -> dict:
        """
        Assess a single question/answer pair.
        For processing full records, prefer assess_record() — it gives the model
        cross-field context in a single call.

        Returns:
        {
            "question_id": str,
            "risk_level": str,
            "pii_types": list,
            "reasoning": str,
            "recommended_action": str
        }
        """
        prompt = self._build_single_prompt(
            question_text, answer, question_id, survey_context, all_answers
        )

        try:
            raw = self._call_ollama(prompt)
            return self._parse_single_response(raw, question_id)
        except OllamaUnavailableError as e:
            return self._fallback_single(question_id, reason=str(e))
        except Exception as e:
            return self._fallback_single(question_id, reason=str(e))

    def is_available(self) -> bool:
        """Check whether the Ollama server is reachable before running the pipeline."""
        try:
            req = urllib.request.Request(f"{self.base_url}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=5):
                return True
        except Exception:
            return False

    # ------------------------------------------------------------------ #
    # Prompt builders
    # ------------------------------------------------------------------ #

    def _build_batch_prompt(
        self, answers: dict, q_text_map: dict, survey_context: Optional[dict]
    ) -> str:
        context_block = ""
        if survey_context:
            context_block = f"\nSurvey context: {json.dumps(survey_context)}\n"

        qa_lines = []
        for qid, ans in answers.items():
            qtext = q_text_map.get(qid, qid)
            safe_ans = str(ans).replace('"', "'")
            qa_lines.append(f'  "{qid}": {{ "question": "{qtext}", "answer": "{safe_ans}" }}')
        qa_block = "{\n" + ",\n".join(qa_lines) + "\n}"

        return f"""You are a privacy and data protection expert. Your job is to assess PII risk in survey responses.
{context_block}
Analyze ALL of the following question-answer pairs TOGETHER. Cross-field context matters — a combination of fields can create re-identification risk even when individual fields seem harmless (e.g. age + city + occupation together may uniquely identify someone).

{qa_block}

Return ONLY a valid JSON object. No markdown formatting, no explanation outside the JSON, no preamble.

The JSON must map each question_id key to an assessment object:
{{
  "<question_id>": {{
    "risk_level": "<NONE|LOW|MEDIUM|HIGH|CRITICAL>",
    "pii_types": ["<list of PII category strings>"],
    "reasoning": "<one sentence explanation>",
    "recommended_action": "<keep|generalize|pseudonymize|suppress>"
  }}
}}

Definitions:
  risk_level:
    NONE     — no personal information present
    LOW      — generic, non-identifying (e.g. "I enjoy hiking")
    MEDIUM   — could identify in combination with other fields (e.g. job title, city, age)
    HIGH     — directly identifying on its own (full name, email, phone number)
    CRITICAL — sensitive category + identifying (SSN, health condition, financial account, government ID)

  recommended_action:
    keep          — safe to store as-is
    generalize    — replace with range or category (e.g. age 34 → "30-39")
    pseudonymize  — replace with a consistent opaque token (e.g. name → hashed ID)
    suppress      — remove entirely

  pii_types examples: NAME, EMAIL, PHONE, ADDRESS, DATE_OF_BIRTH, AGE, LOCATION,
                      OCCUPATION, HEALTH, FINANCIAL, GOVERNMENT_ID, RACE_ETHNICITY,
                      RELIGION, POLITICAL_OPINION"""

    def _build_single_prompt(
        self,
        question_text: str,
        answer: str,
        question_id: str,
        survey_context: Optional[dict],
        all_answers: Optional[dict],
    ) -> str:
        context_block = ""
        if survey_context:
            context_block += f"\nSurvey context: {json.dumps(survey_context)}"
        if all_answers:
            context_block += f"\nOther answers from this respondent: {json.dumps(all_answers)}"

        return f"""You are a privacy and data protection expert assessing PII risk in a survey response.
{context_block}

Question ID: {question_id}
Question: {question_text}
Answer: {answer}

Return ONLY a valid JSON object. No markdown, no preamble:
{{
  "risk_level": "<NONE|LOW|MEDIUM|HIGH|CRITICAL>",
  "pii_types": ["<PII categories found>"],
  "reasoning": "<one sentence explanation>",
  "recommended_action": "<keep|generalize|pseudonymize|suppress>"
}}

risk_level: NONE=no PII, LOW=generic, MEDIUM=identifying in combination, HIGH=directly identifying, CRITICAL=sensitive+identifying
recommended_action: keep=safe, generalize=bucket/range, pseudonymize=opaque token, suppress=remove"""

    # ------------------------------------------------------------------ #
    # Ollama API call
    # ------------------------------------------------------------------ #

    def _call_ollama(self, prompt: str) -> str:
        """
        POST to Ollama's /api/generate endpoint and return the full response string.
        Uses stream=false for simpler response handling.
        """
        payload = json.dumps({
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,  # Low temp = more deterministic JSON
                "top_p": 0.9,
            },
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("response", "")
        except urllib.error.URLError as e:
            raise OllamaUnavailableError(
                f"Cannot reach Ollama at {self.base_url}. "
                f"Make sure Ollama is running (`ollama serve`) — {e}"
            )

    # ------------------------------------------------------------------ #
    # Response parsers
    # ------------------------------------------------------------------ #

    def _parse_batch_response(self, text: str, answers: dict) -> dict:
        """
        Parse batch model output into per-field assessments.
        Handles common local model quirks: markdown fences, trailing commas, extra prose.
        """
        cleaned = self._extract_json_block(text)

        parsed = self._try_parse_json(cleaned)
        if parsed is None:
            print(f"[AIDetector] Could not parse batch response. Raw output:\n{text[:500]}")
            return self._fallback_assessments(answers, reason="JSON parse error")

        result = {}
        for qid in answers:
            if qid in parsed:
                entry = parsed[qid]
                result[qid] = {
                    "risk_level":         self._safe_risk(entry.get("risk_level")),
                    "pii_types":          entry.get("pii_types", []),
                    "reasoning":          entry.get("reasoning", ""),
                    "recommended_action": self._safe_action(entry.get("recommended_action")),
                }
            else:
                # Model skipped this field — default to NONE (safe assumption)
                result[qid] = {
                    "risk_level": "NONE",
                    "pii_types": [],
                    "reasoning": "Not assessed by model",
                    "recommended_action": "keep",
                }
        return result

    def _parse_single_response(self, text: str, question_id: str) -> dict:
        cleaned = self._extract_json_block(text)
        parsed = self._try_parse_json(cleaned)

        if parsed is None:
            return self._fallback_single(question_id, reason="JSON parse error")

        return {
            "question_id":        question_id,
            "risk_level":         self._safe_risk(parsed.get("risk_level")),
            "pii_types":          parsed.get("pii_types", []),
            "reasoning":          parsed.get("reasoning", ""),
            "recommended_action": self._safe_action(parsed.get("recommended_action")),
        }

    # ------------------------------------------------------------------ #
    # Utilities
    # ------------------------------------------------------------------ #

    @staticmethod
    def _build_q_text_map(questions: Optional[list]) -> dict:
        if not questions:
            return {}
        return {
            (q.get("question_id") or q.get("id")): (q.get("text") or q.get("question_text") or "")
            for q in questions
            if q.get("question_id") or q.get("id")
        }

    @staticmethod
    def _extract_json_block(text: str) -> str:
        """Strip markdown fences and extract the outermost JSON object from model output."""
        text = re.sub(r"```(?:json)?", "", text).replace("```", "").strip()
        match = re.search(r"\{.*\}", text, re.DOTALL)
        return match.group(0) if match else text

    @staticmethod
    def _try_parse_json(text: str) -> Optional[dict]:
        """Try to parse JSON; attempt trailing-comma fix on failure."""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            fixed = re.sub(r",\s*([}\]])", r"\1", text)
            try:
                return json.loads(fixed)
            except json.JSONDecodeError:
                return None

    @staticmethod
    def _safe_risk(value) -> str:
        if isinstance(value, str) and value.upper() in RISK_LEVELS:
            return value.upper()
        return "LOW"

    @staticmethod
    def _safe_action(value) -> str:
        valid = {"keep", "generalize", "pseudonymize", "suppress"}
        if isinstance(value, str) and value.lower() in valid:
            return value.lower()
        return "keep"

    @staticmethod
    def _fallback_assessments(answers: dict, reason: str = "") -> dict:
        return {
            qid: {
                "risk_level": "LOW",
                "pii_types": [],
                "reasoning": f"AI assessment unavailable: {reason}",
                "recommended_action": "keep",
            }
            for qid in answers
        }

    @staticmethod
    def _fallback_single(question_id: str, reason: str = "") -> dict:
        return {
            "question_id": question_id,
            "risk_level": "LOW",
            "pii_types": [],
            "reasoning": f"AI assessment unavailable: {reason}",
            "recommended_action": "keep",
        }


class OllamaUnavailableError(RuntimeError):
    """Raised when the Ollama server cannot be reached."""
    pass