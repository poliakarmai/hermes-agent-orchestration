#!/usr/bin/env python3
"""
Skill Validator — Stage 0 CI/CD проверка скилла перед импортом.
Проверяет: YAML frontmatter, обязательные поля, внутренние ссылки, соглашения.
"""
import os
import sys
import re
import json
from pathlib import Path


def validate_frontmatter(content: str) -> dict:
    """Проверяет YAML frontmatter. Возвращает {valid, errors, fields}."""
    errors = []
    fields = {}

    if not content.startswith("---"):
        errors.append("Missing YAML frontmatter (should start with ---)")
        return {"valid": False, "errors": errors, "fields": fields}

    # Extract frontmatter
    parts = content.split("---", 2)
    if len(parts) < 3:
        errors.append("Unclosed YAML frontmatter")
        return {"valid": False, "errors": errors, "fields": fields}

    fm = parts[1].strip()

    # Parse key: value pairs (simple parser)
    for line in fm.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, _, val = line.partition(":")
            fields[key.strip()] = val.strip().strip('"').strip("'")

    # Required fields
    required = ["name", "description"]
    for field in required:
        if field not in fields:
            errors.append(f"Missing required field: {field}")

    # Name validation
    if "name" in fields:
        name = fields["name"]
        if not re.match(r'^[a-z0-9][a-z0-9._-]*$', name):
            errors.append(f"Invalid skill name: '{name}' (use lowercase, hyphens, underscores only)")
        if len(name) > 64:
            errors.append(f"Skill name too long: {len(name)} > 64 chars")

    return {"valid": len(errors) == 0, "errors": errors, "fields": fields}


def validate_references(content: str, skill_dir: Path = None) -> dict:
    """Проверяет внутренние ссылки (references/, templates/, scripts/)."""
    errors = []

    # Find all file references
    refs = re.findall(r'references/([^\s\)\]]+)', content)
    refs += re.findall(r'templates/([^\s\)\]]+)', content)
    refs += re.findall(r'scripts/([^\s\)\]]+)', content)

    if skill_dir and refs:
        for ref in refs:
            ref_path = skill_dir / ref
            if not ref_path.exists():
                errors.append(f"Broken reference: {ref} (file not found)")

    return {"valid": len(errors) == 0, "errors": errors}


def validate_content_quality(content: str) -> dict:
    """Проверяет качество содержимого."""
    errors = []
    warnings = []

    # Minimum content length
    body = content.split("---", 2)[-1].strip() if "---" in content else content
    if len(body) < 50:
        errors.append(f"Skill body too short: {len(body)} chars (min 50)")

    # Check for shell injection patterns
    dangerous = [
        (r'\beval\s*\(', "eval() call detected"),
        (r'\bexec\s*\(', "exec() call detected"),
        (r'rm\s+-rf\s+/', "rm -rf / detected"),
        (r'>\s*/dev/[a-z]+', "Device redirection detected"),
    ]
    for pattern, msg in dangerous:
        if re.search(pattern, content):
            errors.append(f"Security: {msg}")

    # Check for hardcoded paths outside sandbox
    suspicious_paths = re.findall(r'(/home/\w+|/root|/etc/)', content)
    if suspicious_paths:
        warnings.append(f"Hardcoded paths outside sandbox: {', '.join(set(suspicious_paths))}")

    return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}


def validate(skill_file: Path) -> dict:
    """Полная валидация скилла. Возвращает {passed, errors, warnings, score}."""
    if not skill_file.exists():
        return {"passed": False, "errors": [f"File not found: {skill_file}"], "warnings": [], "score": 0}

    content = skill_file.read_text()
    all_errors = []
    all_warnings = []

    # Stage 0a: Frontmatter
    fm = validate_frontmatter(content)
    all_errors.extend(fm["errors"])

    # Stage 0b: References
    ref = validate_references(content, skill_file.parent)
    all_errors.extend(ref["errors"])

    # Stage 0c: Content quality
    cq = validate_content_quality(content)
    all_errors.extend(cq["errors"])
    all_warnings.extend(cq["warnings"])

    score = max(0, 100 - (len(all_errors) * 20))
    passed = len(all_errors) == 0

    return {
        "passed": passed,
        "errors": all_errors,
        "warnings": all_warnings,
        "score": score,
        "skill_name": fm["fields"].get("name", skill_file.parent.name),
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: skill-validate.py <skill_file> [--json]")
        sys.exit(1)

    skill_file = Path(sys.argv[1])
    result = validate(skill_file)

    if "--json" in sys.argv:
        print(json.dumps(result, indent=2))
    else:
        if result["passed"]:
            print(f"✅ {result['skill_name']}: PASSED (score {result['score']})")
        else:
            print(f"❌ {result['skill_name']}: FAILED (score {result['score']})")
        for e in result["errors"]:
            print(f"  ❌ {e}")
        for w in result["warnings"]:
            print(f"  ⚠️ {w}")

    sys.exit(0 if result["passed"] else 1)
