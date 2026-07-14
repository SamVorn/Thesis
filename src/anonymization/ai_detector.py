# src/anonymization/ai_detector.py
"""
AI-powered PII detector using a local Ollama model for PII detection.

should run entirely on premise with no data leaving the machine

Recommended models (run `ollama pull <model>` to install):
  - llama3.1:8b       best balance of quality vs. speed
  - mistral:7b        faster, weaker reasoning
  - llama3.1:70b      best quality, requires ~40GB RAM or a GPU

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
   
    # Uses a local Ollama model to contextually evaluate PII risk in survey responses.

    def __init__(
        self,
        model: str = "llama3.1:8b",
        base_url: str = OLLAMA_BASE_URL,
        timeout: int = 120,
        batch_size: int = 20,
    ):
        """
        :param model:      Ollama model tag. Run `ollama list` to see installed models.
        :param base_url:   Ollama server URL (default: http://localhost:11434)
        :param timeout:    Request timeout in seconds. Increase for large/slow models.
        :param batch_size: Max question/answer pairs per Ollama call. Reduce to 10
                           if you see truncated JSON on slower hardware (default: 20).
        """
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.batch_size = batch_size

    def assess_record(
        self,
        record: dict,
        questions: list = None,
        survey_context: dict = None,
    ) -> dict:
        
        # Assess all answers in a record in a single model call.

        answers = record.get("answers", {})
        respondent_id = record.get("respondent_id", "unknown")

        if not answers:
            return {"respondent_id": respondent_id, "assessments": {}, "overall_risk": "NONE"}

        q_text_map = self._build_q_text_map(questions)

        # Chunk answers into batches of self.batch_size to avoid overflowing
        # the model's context window on large surveys.
        all_items  = list(answers.items())
        chunks     = [
            dict(all_items[i : i + self.batch_size])
            for i in range(0, len(all_items), self.batch_size)
        ]

        assessments: dict = {}
        for chunk in chunks:
            prompt = self._build_batch_prompt(chunk, q_text_map, survey_context)
            try:
                raw    = self._call_ollama(prompt)
                chunk_assessments = self._parse_batch_response(raw, chunk)
            except OllamaUnavailableError as e:
                print(f"[AIDetector] Ollama unavailable: {e}")
                chunk_assessments = self._fallback_assessments(chunk, reason=str(e))
            except Exception as e:
                print(f"[AIDetector] Unexpected error during assessment: {e}")
                chunk_assessments = self._fallback_assessments(chunk, reason=str(e))
            assessments.update(chunk_assessments)

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
    NONE     — no personal information present. Use this for: yes/no answers, ratings,
               preferences, opinions, satisfaction responses, lifestyle choices, hobbies,
               and anything that cannot narrow down who a person is even in combination
               with other answers. Examples: "Yes", "No", "Blue", "Jazz", "I enjoy hiking",
               "I prefer mornings", "I work in retail", "Coffee", "Mountains", "3 out of 5",
               "I cook at home", "Introvert", "Summer", "Cats". If the answer reveals
               nothing that could contribute to identifying a real individual, it is NONE.
    LOW      — reveals a specific, stable personal attribute that, combined with several
               other LOW fields from the SAME record, could narrow identification.
               Requires actual specificity: a named city of residence, a specific niche
               occupation, a unique hobby description, or an age. Generic lifestyle
               statements ("I enjoy hiking", "I like coffee") are NONE, not LOW.
               Example LOW answers: "I live in Burlington, VT", "I'm a pediatric oncologist",
               "I was born in 1987".
    MEDIUM   — meaningfully contributes to re-identification when combined with other fields
               (e.g. exact age + named city + specific job title together in one record)
    HIGH     — directly identifying on its own (full name, email, phone number, exact address)
    CRITICAL — sensitive category + identifying (SSN, health diagnosis, financial account,
               government ID, biometric data)

  recommended_action:
    keep          — safe to store as-is
    generalize    — replace with range or category (e.g. age 34 → "30-39")
    pseudonymize  — replace with a consistent opaque token (e.g. name → hashed ID)
    suppress      — remove entirely

  pii_types examples: NAME, EMAIL, PHONE, ADDRESS, DATE_OF_BIRTH, AGE, LOCATION,
                      OCCUPATION, HEALTH, FINANCIAL, GOVERNMENT_ID, RACE_ETHNICITY,
                      RELIGION, POLITICAL_OPINION

Bias strongly toward NONE. Generic lifestyle preferences, hobbies, opinions, and
yes/no answers are almost always NONE. Only assign LOW when the answer contains a
specific, stable, personally attributable fact. Only escalate to MEDIUM or above when
there is clear identifying information or a genuine re-identification risk from the
combination of fields in this record. When in doubt, choose NONE."""

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

risk_level:
  NONE=no PII — yes/no, opinions, ratings, preferences, hobbies, lifestyle choices,
       generic statements. If it could apply to millions of people without narrowing
       down who this person is, it is NONE. ("I enjoy hiking", "Coffee", "Blue", "Yes")
  LOW=specific stable personal attribute that could contribute to ID in combination
      with other LOW fields (named city, niche occupation, birth year). Generic
      lifestyle statements are NONE, not LOW.
  MEDIUM=meaningfully identifying in combination with other fields in this record
  HIGH=directly identifying alone (name, email, phone, exact address)
  CRITICAL=sensitive category + identifying (SSN, health, financial, govt ID)
recommended_action: keep=safe, generalize=bucket/range, pseudonymize=opaque token, suppress=remove
Bias strongly toward NONE. Generic preferences and opinions are almost always NONE.
Only escalate when the answer contains a specific personally attributable fact."""

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

    def _parse_batch_response(self, text: str, answers: dict) -> dict:
        cleaned = self._extract_json_block(text)

        parsed = self._try_parse_json(cleaned)
        if parsed is None:
            print(f"[AIDetector] Could not parse batch response. Raw output:\n{text[:500]}")
            return self._fallback_assessments(answers, reason="JSON parse error")

        result = {}
        for qid in answers:
            if qid in parsed:
                entry = parsed[qid]
                risk   = self._safe_risk(entry.get("risk_level"))
                action = self._safe_action(entry.get("recommended_action"))
                answer_str = str(answers[qid])

                # Post-processing clamp: downgrade LOW→NONE for answers that
                # match known-harmless shapes regardless of model output.
                # This catches the model's tendency to assign LOW to generic
                # lifestyle preferences, yes/no answers, and short opinions.
                if risk == "LOW" and self._clamp_harmless(answer_str):
                    risk   = "NONE"
                    action = "keep"

                result[qid] = {
                    "risk_level":         risk,
                    "pii_types":          entry.get("pii_types", []),
                    "reasoning":          entry.get("reasoning", ""),
                    "recommended_action": action,
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
        return "NONE"

    @staticmethod
    def _safe_action(value) -> str:
        valid = {"keep", "generalize", "pseudonymize", "suppress"}
        if isinstance(value, str) and value.lower() in valid:
            return value.lower()
        return "keep"

    # Regex patterns that reliably signal a harmless answer.
    # Any answer fully matched by one of these is structurally incapable of
    # contributing to re-identification and should be clamped to NONE.
    # Only applied to LOW-rated answers — MEDIUM and above are never downgraded.
    _HARMLESS_PATTERNS = re.compile(
        r"""^(
            # Pure yes/no/maybe/other single-word responses
            yes|no|maybe|sometimes|often|rarely|never|always|n\/a|none|other
            # Numeric counts and simple ratings (e.g. "3", "5", "2 hours")
            |\d+(\s*(hours?|times?|days?|cups?|years?|minutes?|per\s+week|per\s+day))?
            # Short colour/size/type answers
            |[a-z]+\s*(and\s+[a-z]+)?  # catches "blue", "red and blue", etc.
        )$""",
        re.IGNORECASE | re.VERBOSE,
    )

    # Longer pattern for generic lifestyle phrases that are never identifying.
    # These are full-phrase matches, not anchored to start/end, because the
    # model generates varied phrasing around these concepts.
    _HARMLESS_PHRASES = re.compile(
        r"""(
            i\s+(enjoy|love|like|prefer|hate|dislike|cook|eat|watch|read|listen|play|follow)
            |i\s+(consider\s+myself|would\s+(say|describe)|am\s+(an?\s+)?(introvert|extrovert))
            |my\s+favorite
            |i\s+usually|i\s+tend\s+to|i\s+try\s+to
            |at\s+home|eating\s+out|in.store|online\s+shopping
        )""",
        re.IGNORECASE | re.VERBOSE,
    )

    @staticmethod
    def _clamp_harmless(answer: str) -> bool:
        stripped = answer.strip()
        if not stripped:
            return True  # empty answer is always NONE

        words = stripped.split()

        # Very short answers (1-3 words) without proper nouns or years → harmless
        if len(words) <= 3:
            # A 4-digit year suggests DOB / graduation / event → don't clamp
            if re.search(r"\b(19|20)\d{2}\b", stripped):
                return False
            # Proper-noun heuristic only applies to multi-word answers:
            # single words are almost always capitalized by convention (sentence start,
            # colour names, etc.) and are not proper nouns.
            # For 2-3 word answers, a Title-Cased word ≥ 4 chars that is not a common
            # English word suggests a place name or personal name → don't clamp.
            if len(words) >= 2:
                _COMMON = {"yes", "no", "the", "and", "but", "for", "not", "with",
                           "blue", "red", "green", "yellow", "black", "white", "brown",
                           "jazz", "rock", "pop", "folk", "soul", "country", "classical",
                           "coffee", "tea", "water", "mountains", "beaches", "summer",
                           "winter", "spring", "autumn", "fall", "sometimes", "never",
                           "always", "often", "rarely", "maybe", "both", "either"}
                if any(
                    w[0].isupper() and len(w) >= 4 and w.lower() not in _COMMON
                    for w in words if w.isalpha()
                ):
                    return False
            return True  # short, no proper noun, no year → harmless

        # Longer answers: only clamp if they match a known-harmless phrase pattern
        if AIDetector._HARMLESS_PHRASES.search(stripped):
            # Still don't clamp if a proper noun or year appears anywhere
            if re.search(r"\b(19|20)\d{2}\b", stripped):
                return False
            if any(w[0].isupper() and len(w) >= 4 for w in words if w.isalpha()):
                return False
            return True

        return False

    @staticmethod
    def _fallback_assessments(answers: dict, reason: str = "") -> dict:
        return {
            qid: {
                "risk_level": "NONE",
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
            "risk_level": "NONE",
            "pii_types": [],
            "reasoning": f"AI assessment unavailable: {reason}",
            "recommended_action": "keep",
        }


class OllamaUnavailableError(RuntimeError):
    """Raised when the Ollama server cannot be reached."""
    pass