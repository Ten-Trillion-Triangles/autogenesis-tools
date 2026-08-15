#!/usr/bin/env python3
"""Detect logging framework used in a Python project."""

import re
from pathlib import Path
from typing import Dict, List


FRAMEWORK_PATTERNS = {
    "python-logging": {
        "imports": [re.compile(r"import\s+logging\b"), re.compile(r"from\s+logging\s+import")],
        "configs": [re.compile(r"logging\.basicConfig"), re.compile(r"logging\.getLogger"), re.compile(r"FileHandler\("), re.compile(r"RotatingFileHandler\("), re.compile(r"TimedRotatingFileHandler\(")],
    },
    "loguru": {
        "imports": [re.compile(r"from\s+loguru\s+import"), re.compile(r"import\s+loguru\b")],
        "configs": [re.compile(r"logger\.add\("), re.compile(r"logger\.remove\(")],
    },
    "structlog": {
        "imports": [re.compile(r"import\s+structlog\b"), re.compile(r"from\s+structlog\s+import")],
        "configs": [re.compile(r"structlog\.configure\("), re.compile(r"structlog\.get_logger")],
    },
    "json-logging": {
        "imports": [re.compile(r"from\s+pythonjsonlogger"), re.compile(r"import\s+pythonjsonlogger")],
        "configs": [re.compile(r"JsonFormatter\(")],
    },
    "coloredlogs": {
        "imports": [re.compile(r"import\s+coloredlogs\b"), re.compile(r"from\s+coloredlogs\s+import")],
        "configs": [re.compile(r"coloredlogs\.install\(")],
    },
    "logbook": {
        "imports": [re.compile(r"import\s+logbook\b"), re.compile(r"from\s+logbook\s+import")],
        "configs": [re.compile(r"logbook\.Logger\("), re.compile(r"logbook\.FileHandler\(")],
    },
}

IMPORT_WEIGHT = 1
CONFIG_WEIGHT = 2


def scan_file_for_logging(file_path: str) -> Dict:
    """Scan a single Python file for logging patterns."""
    result = {"file": file_path, "patterns_found": [], "framework_scores": {}, "has_logging": False}

    try:
        content = Path(file_path).read_text(errors="ignore")
    except Exception:
        return result

    for framework in FRAMEWORK_PATTERNS:
        result["framework_scores"][framework] = 0

    for framework, rules in FRAMEWORK_PATTERNS.items():
        for pattern in rules["imports"]:
            if pattern.search(content):
                result["patterns_found"].append(f"import:{framework}")
                result["framework_scores"][framework] += IMPORT_WEIGHT

        for pattern in rules["configs"]:
            if pattern.search(content):
                result["patterns_found"].append(f"config:{framework}")
                result["framework_scores"][framework] += CONFIG_WEIGHT

    result["has_logging"] = any(score > 0 for score in result["framework_scores"].values())
    return result


def detect_logging_framework(project_path: str) -> Dict:
    """Scan project files to detect logging framework.

    Returns:
        dict with keys: framework, confidence, evidence
    """
    project = Path(project_path)

    if not project.exists():
        return {"framework": "unknown", "confidence": "low", "evidence": [f"Path does not exist: {project_path}"]}

    if not project.is_dir():
        return {"framework": "unknown", "confidence": "low", "evidence": [f"Path is not a directory: {project_path}"]}

    py_files = list(project.rglob("*.py"))
    if not py_files:
        return {"framework": "unknown", "confidence": "low", "evidence": ["No Python files found in project"]}

    total_scores: Dict[str, int] = {framework: 0 for framework in FRAMEWORK_PATTERNS}
    config_scores: Dict[str, int] = {framework: 0 for framework in FRAMEWORK_PATTERNS}
    dedicated_files: Dict[str, int] = {framework: 0 for framework in FRAMEWORK_PATTERNS}
    evidence: List[str] = []

    for py_file in py_files:
        file_result = scan_file_for_logging(str(py_file))
        if file_result["has_logging"]:
            frameworks_in_file = set()
            for pattern_info in file_result["patterns_found"]:
                evidence.append(f"{py_file.name}: {pattern_info}")
                if pattern_info.startswith("config:"):
                    fw = pattern_info.split(":")[1]
                    config_scores[fw] += 1
                    frameworks_in_file.add(fw)
                elif pattern_info.startswith("import:"):
                    frameworks_in_file.add(pattern_info.split(":")[1])
            for framework, score in file_result["framework_scores"].items():
                total_scores[framework] += score
            if len(frameworks_in_file) == 1 and "python-logging" not in frameworks_in_file:
                dedicated_files[frameworks_in_file.pop()] += 1

    if not any(scores > 0 for scores in total_scores.values()):
        return {"framework": "unknown", "confidence": "low", "evidence": ["No logging patterns detected"]}

    def framework_sort_key(item):
        fw, score = item
        return (score, config_scores[fw], dedicated_files[fw])

    sorted_frameworks = sorted(total_scores.items(), key=framework_sort_key, reverse=True)
    primary_framework = sorted_frameworks[0][0]
    primary_score = sorted_frameworks[0][1]
    secondary_score = sorted_frameworks[1][1] if len(sorted_frameworks) > 1 else 0

    if primary_score == 0:
        framework, confidence = "unknown", "low"
    elif secondary_score == 0 or primary_score >= secondary_score * 3:
        confidence = "high" if primary_score >= 10 else ("medium" if primary_score >= 4 else "low")
        framework = primary_framework
    elif primary_score > secondary_score:
        confidence = "medium" if primary_score >= 4 else "low"
        framework = primary_framework
    else:
        framework, confidence = primary_framework, "low"

    unique_evidence = list(dict.fromkeys(evidence))[:50]
    return {"framework": framework, "confidence": confidence, "evidence": unique_evidence}


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python detect_framework.py <project_path>")
        sys.exit(1)

    result = detect_logging_framework(sys.argv[1])
    print(f"Framework: {result['framework']}")
    print(f"Confidence: {result['confidence']}")
    print(f"Evidence ({len(result['evidence'])} items):")
    for e in result["evidence"]:
        print(f"  - {e}")