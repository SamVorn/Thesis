# src/repository/file_source.py

import json
from pathlib import Path
from src.repository.interface import SurveyDataSource


class FileSurveySource(SurveyDataSource):
    """
    File-based survey data source.

    - Discovers the survey template and responses by structure, not filename
    - Ignores survey_id (batch-oriented source)
    """

    def __init__(self, folder_path: str):
        self.folder = Path(folder_path)
        self._template = None
        self._responses = []
        self._discover_files()

    def _discover_files(self):
        """
        Discover template and response files based on JSON structure.
        """
        if not self.folder.exists():
            raise FileNotFoundError(f"Dataset folder not found: {self.folder}")

        for f in self.folder.glob("*.json"):
            try:
                data = json.loads(f.read_text())
            except json.JSONDecodeError:
                continue  # Skip malformed JSON files

            # Template heuristic: contains a list of questions
            if (
                isinstance(data, dict)
                and "questions" in data
                and isinstance(data["questions"], list)
            ):
                self._template = {
                    "survey_id": data.get("survey_id", self.folder.name),
                    "questions": data["questions"],  # keep as list of dicts
                }

            # Response heuristic: dict with "responses"/"answers" OR top-level list
            elif isinstance(data, dict) and ("responses" in data or "answers" in data):
                self._responses.append((f, data))
            elif isinstance(data, list):
                self._responses.append((f, data))

                
    def get_survey_template(self, survey_id: str | None = None):
        """
        Return the discovered survey template.
        survey_id is ignored for file-based sources.
        """
        return self._template

    def iter_responses(self, survey_id: str | None = None):
        """
        Iterate over all discovered responses.
        survey_id is ignored for file-based sources.
        """
        for f, data in self._responses:
            # If data is a list, wrap it as responses
            if isinstance(data, list):
                responses = data
                respondent_id = f.stem  # fallback ID from filename
            elif isinstance(data, dict):
                responses = data.get("responses") or data.get("answers", [])
                respondent_id = data.get("respondent_id", f.stem)
            else:
                continue  # skip unknown formats

            yield {
                "respondent_id": respondent_id,
                "answers": {
                    r["question_id"]: r["answer"]
                    for r in responses
                    if isinstance(r, dict) and "question_id" in r and "answer" in r
                },
            }


    def save_flags(self, survey_id, flagged_data):
        """
        Persist anonymization flags.
        survey_id is ignored for file-based sources.
        """
        self.folder.mkdir(parents=True, exist_ok=True)
        flags_path = self.folder / "flags.json"

        with open(flags_path, "w", encoding="utf-8") as f:
            json.dump(list(flagged_data), f, indent=2)
