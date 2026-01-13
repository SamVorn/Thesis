import json
from pathlib import Path
from src.repository.interface import SurveyDataSource

class FileSurveySource(SurveyDataSource):
    def __init__(self, folder_path: str):
        self.folder = Path(folder_path)

    def get_survey_template(self, survey_id: str):
        # Look for a file named like template_<survey_id>.json
        template_file = self.folder / f"template_{survey_id}.json"
        if template_file.exists():
            data = json.loads(template_file.read_text())
            template = {
                "survey_id": survey_id,
                "questions": {q["question_id"]: q["question_text"] for q in data.get("questions", [])}
            }
            return template
        return None

    def iter_responses(self, survey_id: str):
        # Iterate all JSON files that are not templates
        for f in self.folder.glob("*.json"):
            if f.name.startswith("template_"):
                continue
            data = json.loads(f.read_text())
            if data.get("survey_id") == survey_id:
                yield {
                    "respondent_id": data.get("respondent_id", f.stem),
                    "answers": {r["question_id"]: r["answer"] for r in data.get("responses", [])}
                }

    def save_flags(self, survey_id: str, flagged_data):
        flags_path = self.folder / f"{survey_id}_flags.json"
        with open(flags_path, "w") as f:
            json.dump(list(flagged_data), f, indent=2)
