from abc import ABC, abstractmethod
from typing import Optional, Iterator

# Abstract and database-agnostic — no mention of SQL, Mongo, files, JSON, etc.
class SurveyDataSource(ABC):

    @abstractmethod
    def get_survey_template(self, survey_id: Optional[str] = None) -> Optional[dict]:
        # returns survey metadata and questions.
        pass

    @abstractmethod
    def iter_responses(self, survey_id: Optional[str] = None) -> Iterator[dict]:
        # Yields responses one at a time.
        pass

    @abstractmethod
    def save_flags(self, survey_id: Optional[str], flagged_data) -> None:
        # Persists anonymization flags for a given survey.
        pass