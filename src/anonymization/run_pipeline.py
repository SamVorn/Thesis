# src/anonymization/run_pipeline.py
from .anonymization_pipeline import AnonymizationPipeline
from src.repository.noSQL import DocumentSurveySource

class DocumentAnonymizationPipeline(AnonymizationPipeline):
    """
    Runs anonymization specifically on a document-based source
    and saves the anonymized results to a separate collection.
    """
    def __init__(self, source: DocumentSurveySource, detector, output_collection):
        super().__init__(source, detector)
        self.output_collection = output_collection

    def run(self, survey_id: str):
        """Iterate over responses, anonymize, and save to output collection"""
        for record in self.source.iter_responses(survey_id):
            anon_record = self.anonymize_record(record)
            self.output_collection.insert_one({
                "survey_id": survey_id,
                "_id": record["respondent_id"],
                "answers": anon_record.get("answers", {})
            })
