import json
from pathlib import Path
from .interface import SurveyDataSource

class FileSurveySource(SurveyDataSource):
    def __init__(self, folder_path: str):
        self.folder = Path(folder_path)

    def get_survey_template(self, survey_id: str):
        template_path = self.folder / f"{survey_id}_template.json"
        with open(template_path) as f:
            return json.load(f)

    def iter_responses(self, survey_id: str):
        responses_path = self.folder / f"{survey_id}_responses.json"
        with open(responses_path) as f:
            for r in json.load(f):
                yield r

    def save_flags(self, survey_id: str, flagged_data):
        flags_path = self.folder / f"{survey_id}_flags.json"
        with open(flags_path, "w") as f:
            json.dump(list(flagged_data), f, indent=2)
