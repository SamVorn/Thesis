from abc import ABC, abstractmethod
 # no mention of sql, mongo, files, json, etc
 # abstract and should be independent 
class SurveyDataSource(ABC):

    @abstractmethod
    def get_survey_template(self, survey_id: str) -> dict:
        """Returns survey metadata and questions"""
        pass

    @abstractmethod
    def iter_responses(self, survey_id: str):
        """Yields responses one at a time"""
        pass

#literally what the fuck is this? VVVVV

# class FileDataSource(SurveyDataSource):
#     def __init__(self, dataset_dir):
#         self.dataset_dir = dataset_dir

#     def get_survey_template(self, survey_id):
#         ...

#     def iter_responses(self, survey_id):
#         yield {
#             "respondent_id": "...",
#             "answers": {...}
#         }

# class SQLDataSource(SurveyDataSource):
#     def __init__(self, connection):
#         self.conn = connection

#     def get_survey_template(self, survey_id):
#         ...

#     def iter_responses(self, survey_id):
#         yield {
#             "respondent_id": response_id,
#             "answers": {...}
#         }

# #check the NoSQL naming consistency and if it is being used rather than the general adapter
# class NoSQLDataSource(SurveyDataSource):
#     def __init__(self, collection):
#         self.collection = collection

#     def get_survey_template(self, survey_id):
#         ...

#     def iter_responses(self, survey_id):
#         yield {
#             "respondent_id": doc["_id"],
#             "answers": doc["answers"]
#         }
