-- src/docker/sql_schema.sql

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
