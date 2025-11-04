import os
import json
import csv
import xml.etree.ElementTree as ET
from openpyxl import load_workbook
import yaml

def load_survey(file_path):
    _, ext = os.path.splitext(file_path)
    ext = ext.lower()

    if ext == ".json":
        with open(file_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
        return _normalize_json(raw_data, file_path)

    elif ext == ".csv":
        return _parse_csv(file_path)

    elif ext in (".yml", ".yaml"):
        return _parse_yaml(file_path)

    elif ext == ".xml":
        return _parse_xml(file_path)

    elif ext == ".xlsx":
        return _parse_xlsx(file_path)

    elif ext == ".txt":
        return _parse_txt(file_path)

    else:
        raise ValueError(f"Unsupported survey file type: {ext}")


def load_rules(file_path):
    _, ext = os.path.splitext(file_path)
    ext = ext.lower()

    with open(file_path, "r", encoding="utf-8") as f:
        if ext in (".json", ".yml", ".yaml"):
            if ext in (".yml", ".yaml"):
                return yaml.safe_load(f)
            return json.load(f)
        elif ext == ".txt":
            # Each line = pattern label and regex separated by ":"
            # Example: email: \b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z]{2,}\b
            rules = {}
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if ":" in line:
                    label, pattern = line.split(":", 1)
                    rules[label.strip()] = pattern.strip()
            return rules
        else:
            raise ValueError(f"Unsupported rule file type: {ext}")

# ---------------------------
# FORMAT PARSERS
# ---------------------------

def _normalize_json(data, file_path):
    """Normalize any JSON schema into standard structure."""
    keys = ["responses", "questions", "items", "entries"]
    responses = []
    response_list = next((data.get(k) for k in keys if k in data), [])

    # Handle nested sections
    if not response_list and "sections" in data:
        for section in data["sections"]:
            response_list.extend(section.get("questions", []))

    for i, r in enumerate(response_list, start=1):
        responses.append({
            "question_id": r.get("question_id") or r.get("id") or i,
            "question_text": r.get("question_text") or r.get("text") or r.get("question") or "",
            "answer": r.get("answer") or r.get("response") or r.get("value") or ""
        })

    survey_id = data.get("survey_id") or data.get("id") or os.path.basename(file_path)
    return {"survey_id": survey_id, "responses": responses}


def _parse_csv(file_path):
    with open(file_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        responses = [
            {
                "question_id": row.get("question_id") or i,
                "question_text": row.get("question_text") or row.get("question") or "",
                "answer": row.get("answer") or row.get("response") or ""
            }
            for i, row in enumerate(reader, start=1)
        ]
    return {"survey_id": os.path.basename(file_path), "responses": responses}


def _parse_yaml(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return _normalize_json(data, file_path)


def _parse_xml(file_path):
    """
    Expected structure:
    <survey id="123">
        <question id="1">
            <text>What is your name?</text>
            <answer>Alice</answer>
        </question>
    </survey>
    """
    tree = ET.parse(file_path)
    root = tree.getroot()
    survey_id = root.attrib.get("id", os.path.basename(file_path))

    responses = []
    for i, q in enumerate(root.findall(".//question"), start=1):
        responses.append({
            "question_id": q.attrib.get("id", i),
            "question_text": q.findtext("text", ""),
            "answer": q.findtext("answer", "")
        })

    return {"survey_id": survey_id, "responses": responses}


def _parse_xlsx(file_path):
    """
    Expects an Excel sheet with columns like:
    | question_id | question_text | answer |
    """
    wb = load_workbook(file_path, read_only=True)
    ws = wb.active

    headers = [str(c.value).strip().lower() for c in next(ws.iter_rows(min_row=1, max_row=1))]
    responses = []
    for i, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=1):
        row_data = dict(zip(headers, row))
        responses.append({
            "question_id": row_data.get("question_id") or i,
            "question_text": row_data.get("question_text") or row_data.get("question") or "",
            "answer": row_data.get("answer") or row_data.get("response") or ""
        })

    return {"survey_id": os.path.basename(file_path), "responses": responses}


def _parse_txt(file_path):
    """
    Handles simple text files:
    Each line may contain 'Question: Answer' or alternating question/answer lines.
    Example:
        What is your name?
        Alice
        What city do you live in?
        New York
    """
    responses = []
    with open(file_path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]

    # Detect simple "Question: Answer" pattern
    for i, line in enumerate(lines, start=1):
        if ":" in line:
            parts = line.split(":", 1)
            responses.append({
                "question_id": i,
                "question_text": parts[0].strip(),
                "answer": parts[1].strip()
            })
        else:
            # Handle alternating lines as question/answer pairs
            if i % 2 == 1 and i < len(lines):
                responses.append({
                    "question_id": i,
                    "question_text": lines[i - 1],
                    "answer": lines[i] if i < len(lines) else ""
                })

    return {"survey_id": os.path.basename(file_path), "responses": responses}
