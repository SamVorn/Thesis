import json
from pathlib import Path
from typing import Dict, Generator
from .interface import SurveyDataSource

class FileDataSource(SurveyDataSource):
    def __init__(self, dataset_dir: str):
        self.dataset_dir = Path(dataset_dir)

    def get_survey_template(self, survey_id: str) -> Dict | None:
        template_path = self.dataset_dir / f"{survey_id}_template.json"
        if template_path.exists():
            with open(template_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return None

    def iter_responses(self, survey_id: str) -> Generator[Dict, None, None]:
        for file_path in self.dataset_dir.glob("*.json"):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except json.JSONDecodeError:
                continue  # skip invalid JSON

            if data.get("survey_id") != survey_id:
                continue

            yield {
                "respondent_id": data.get("respondent_id", "unknown"),
                "answers": data.get("answers", {})
            }
