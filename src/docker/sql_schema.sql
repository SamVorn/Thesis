-- Survey templates table
CREATE TABLE IF NOT EXISTS survey_templates (
    survey_id TEXT PRIMARY KEY,
    template_json JSONB NOT NULL
);

-- Survey responses table
CREATE TABLE IF NOT EXISTS survey_responses (
    respondent_id TEXT,
    survey_id TEXT REFERENCES survey_templates(survey_id),
    answers_json JSONB,
    PRIMARY KEY (respondent_id, survey_id)
);

-- Flags table
CREATE TABLE IF NOT EXISTS pii_flags (
    id SERIAL PRIMARY KEY,
    survey_id TEXT,
    data JSONB
);

CREATE TABLE IF NOT EXISTS survey_responses_anonymized (
   respondent_id TEXT,
    survey_id TEXT REFERENCES survey_templates(survey_id),
    answers_json JSONB,
    PRIMARY KEY (respondent_id, survey_id)
);

-- ADDED: Detector-specific anonymized response tables
-- One table per detector type so results from regex, ai, and hybrid
-- runs are stored separately and never overwrite each other.
CREATE TABLE IF NOT EXISTS survey_responses_anonymized_regex (
    respondent_id TEXT,
    survey_id     TEXT REFERENCES survey_templates(survey_id),
    answers_json  JSONB,
    PRIMARY KEY (respondent_id, survey_id)
);

CREATE TABLE IF NOT EXISTS survey_responses_anonymized_ai (
    respondent_id TEXT,
    survey_id     TEXT REFERENCES survey_templates(survey_id),
    answers_json  JSONB,
    PRIMARY KEY (respondent_id, survey_id)
);

CREATE TABLE IF NOT EXISTS survey_responses_anonymized_hybrid (
    respondent_id TEXT,
    survey_id     TEXT REFERENCES survey_templates(survey_id),
    answers_json  JSONB,
    PRIMARY KEY (respondent_id, survey_id)
);
-- Stores the full field-level detection output for each pipeline run.
-- One row per (survey_id, detector_type) pair — upserted on re-run so results
-- never duplicate. result_json holds the full detection results document as
-- defined in anonymization_pipeline.py (_build_results_document).
-- Used to compare regex, hybrid, and AI detector output against human annotations.
CREATE TABLE IF NOT EXISTS detection_results (
    id              SERIAL PRIMARY KEY,
    survey_id       TEXT NOT NULL REFERENCES survey_templates(survey_id),
    detector_type   TEXT NOT NULL,                  -- "hybrid" | "regex" | "ai"
    run_timestamp   TIMESTAMPTZ,                    -- populated from result_json at insert time
    result_json     JSONB NOT NULL,                 -- full detection results document
    UNIQUE (survey_id, detector_type)               -- enforces one result per detector per survey
);