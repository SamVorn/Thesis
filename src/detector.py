import re

def detect_sensitive_data(answer: str, patterns: dict) -> list:
    flags = []
    for label, pattern in patterns.items():
        if re.search(pattern, answer, re.IGNORECASE):
            flags.append(label)
    return flags

def detect_from_question(question: str, keywords: dict) -> list:
    flags = []
    for label, pattern in keywords.items():
        if re.search(pattern, question, re.IGNORECASE):
            flags.append(label)
    return flags
