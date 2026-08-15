#!/usr/bin/env python3
"""Find log file locations based on framework detection."""

import os, re, glob


def find_log_locations(project_path: str, framework: str) -> list:
    """Find log file locations based on framework.

    Returns:
        list of dict with keys: path, type, confidence, reason
    """
    results = []
    project_path = os.path.expanduser(os.path.expandvars(project_path))

    if framework in ("python", "Python Standard Logging", "standard"):
        results.extend(_find_python_logging(project_path))
    elif framework in ("loguru", "Loguru"):
        results.extend(_find_loguru(project_path))
    elif framework in ("structlog", "Structlog"):
        results.extend(_find_structlog(project_path))
    elif framework in ("json", "JSON Logging"):
        results.extend(_find_json_logging(project_path))

    results.extend(_general_scan(project_path))

    seen = set()
    unique_results = []
    for r in results:
        if r["path"] not in seen:
            seen.add(r["path"])
            unique_results.append(r)

    return unique_results


def _find_python_logging(project_path):
    results = []
    handler_patterns = [
        r'FileHandler\s*\(\s*["\']([^"\']+)["\']',
        r'TimedRotatingFileHandler\s*\(\s*["\']([^"\']+)["\']',
        r'RotatingFileHandler\s*\(\s*["\']([^"\']+)["\']',
        r'basicConfig\s*\([^)]*filename\s*=\s*["\']([^"\']+)["\']',
    ]

    for root, dirs, files in os.walk(project_path):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for file in files:
            filepath = os.path.join(root, file)
            rel_path = os.path.relpath(filepath, project_path)
            try:
                content = Path(filepath).read_text(errors="ignore")
                for pattern in handler_patterns:
                    for match in re.finditer(pattern, content):
                        log_path = match.group(1)
                        if not os.path.isabs(log_path):
                            log_path = os.path.join(project_path, log_path)
                        log_path = os.path.expanduser(os.path.expandvars(log_path))
                        results.append({"path": log_path, "type": "file", "confidence": "high", "reason": f"Found FileHandler in {rel_path}"})
            except (PermissionError, OSError):
                continue
    return results


def _find_loguru(project_path):
    results = []
    add_pattern = r'logger\.add\s*\(\s*["\']([^"\']+)["\']'

    for root, dirs, files in os.walk(project_path):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for file in files:
            filepath = os.path.join(root, file)
            rel_path = os.path.relpath(filepath, project_path)
            try:
                content = Path(filepath).read_text(errors="ignore")
                for match in re.finditer(add_pattern, content):
                    log_path = match.group(1).split(",")[0].strip()
                    if not os.path.isabs(log_path):
                        log_path = os.path.join(project_path, log_path)
                    log_path = os.path.expanduser(os.path.expandvars(log_path))
                    results.append({"path": log_path, "type": "file", "confidence": "high", "reason": f"Found logger.add() in {rel_path}"})
            except (PermissionError, OSError):
                continue
    return results


def _find_structlog(project_path):
    results = []
    config_patterns = [
        r'structlog\.configure\s*\([^)]*output\s*=\s*["\']([^"\']+)["\']',
        r'structlog\.configure\s*\([^)]*filename\s*=\s*["\']([^"\']+)["\']',
        r'FileWriter\s*\(\s*["\']([^"\']+)["\']',
    ]
    for root, dirs, files in os.walk(project_path):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for file in files:
            filepath = os.path.join(root, file)
            rel_path = os.path.relpath(filepath, project_path)
            try:
                content = Path(filepath).read_text(errors="ignore")
                for pattern in config_patterns:
                    for match in re.finditer(pattern, content):
                        log_path = match.group(1)
                        if not os.path.isabs(log_path):
                            log_path = os.path.join(project_path, log_path)
                        log_path = os.path.expanduser(os.path.expandvars(log_path))
                        results.append({"path": log_path, "type": "file", "confidence": "high", "reason": f"Found structlog config in {rel_path}"})
            except (PermissionError, OSError):
                continue
    return results


def _find_json_logging(project_path):
    results = []
    for pattern in ["*.json.log", "*.log.json", "*.jsonl", "*.ndjson"]:
        for filepath in glob.glob(os.path.join(project_path, pattern)):
            results.append({"path": filepath, "type": "file", "confidence": "high", "reason": f"Found JSON log: {pattern}"})
    return results


def _general_scan(project_path):
    results = []
    for name in ["logs", "log"]:
        path = os.path.join(project_path, name)
        if os.path.exists(path):
            results.append({"path": path, "type": "directory", "confidence": "medium", "reason": f"Common directory: {name}"})
    for pattern in ["*.log", "*.log.*"]:
        for filepath in glob.glob(os.path.join(project_path, pattern)):
            results.append({"path": filepath, "type": "file", "confidence": "medium", "reason": f"Log file: {pattern}"})
    for var in ["LOG_DIR", "LOG_PATH", "LOG_FILE", "APP_LOG_DIR", "APP_LOG_PATH"]:
        value = os.environ.get(var)
        if value:
            expanded = os.path.expanduser(os.path.expandvars(value))
            if os.path.exists(expanded):
                results.append({"path": expanded, "type": "file" if os.path.isfile(expanded) else "directory", "confidence": "medium", "reason": f"Via env var {var}"})
    return results


if __name__ == "__main__":
    import sys
    from pathlib import Path

    if len(sys.argv) < 2:
        print("Usage: find_log_locations.py <project_path> [framework]")
        sys.exit(1)

    proj_path = sys.argv[1]
    framework = sys.argv[2] if len(sys.argv) > 2 else "python"

    locations = find_log_locations(proj_path, framework)
    print(f"Found {len(locations)} log location(s):\n")
    for loc in locations:
        print(f"  [{loc['confidence'].upper()}] {loc['path']}")
        print(f"    Type: {loc['type']} | Reason: {loc['reason']}")
        print()