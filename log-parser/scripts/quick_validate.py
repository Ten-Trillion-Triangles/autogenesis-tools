#!/usr/bin/env python3
"""Validate SKILL.md YAML frontmatter and structure."""

import sys, re
from pathlib import Path


def validate_skill_md(file_path: str) -> tuple:
    """Validate SKILL.md file structure.

    Returns: (valid: bool, message: str)
    """
    content = Path(file_path).read_text()

    if not content.startswith('---'):
        return False, "Missing YAML frontmatter start '---'"

    lines = content.split('\n')
    end_idx = None
    for i, line in enumerate(lines[1:], 1):
        if line.strip() == '---':
            end_idx = i
            break

    if end_idx is None:
        return False, "Missing YAML frontmatter end '---'"

    frontmatter_lines = lines[1:end_idx]
    frontmatter = {}
    for line in frontmatter_lines:
        if ':' in line:
            key, val = line.split(':', 1)
            frontmatter[key.strip()] = val.strip()

    if 'name' not in frontmatter:
        return False, "Missing required field: name"
    if 'description' not in frontmatter:
        return False, "Missing required field: description"

    name = frontmatter['name']
    if not re.match(r'^[a-z0-9]+(-[a-z0-9]+)*$', name):
        return False, f"Invalid name '{name}': must be lowercase hyphen-case"
    if len(name) > 64:
        return False, f"Name '{name}' exceeds 64 characters"
    if '--' in name:
        return False, f"Name '{name}' contains consecutive hyphens"
    if name.startswith('-') or name.endswith('-'):
        return False, f"Name '{name}' cannot start or end with hyphen"

    desc = frontmatter['description']
    if len(desc) > 1024:
        return False, "Description exceeds 1024 characters"

    return True, "Valid"


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: quick_validate.py <path-to-SKILL.md>")
        sys.exit(1)

    file_path = Path(sys.argv[1])
    if not file_path.exists():
        print(f"Error: File not found: {file_path}")
        sys.exit(1)

    valid, msg = validate_skill_md(file_path)
    if valid:
        print(f"OK: {msg}")
        sys.exit(0)
    else:
        print(f"FAIL: {msg}")
        sys.exit(1)