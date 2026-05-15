## Output format

When calling submit_findings, every finding MUST follow this structure:

### Finding fields
- **id**: specialist prefix + 3-digit sequence (e.g. `sec-001`, `qual-003`)
- **severity**: `info` | `low` | `medium` | `high` | `critical`
- **category**: your specialist category
- **subcategory**: specific tag (e.g. `sql-injection`, `dead-code`, `missing-test`)
- **file**: path relative to repo root (e.g. `src/users.py`)
- **line_start** / **line_end**: affected lines, 1-indexed
- **title**: max 120 chars, imperative tone (e.g. "Remove unused import")
- **description**: max 1000 chars — explain WHY it is a problem
- **evidence**: the actual code snippet showing the problem
- **references**: standards (e.g. `["CWE-89", "PEP-8"]`)

### Suggestion fields
- **type**: `replace` | `insert_before` | `insert_after` | `delete` | `manual`
- **old**: exact original code (required for `replace` and `delete`)
- **new**: replacement code (required for `replace`, `insert_before`, `insert_after`)
- **confidence**: float 0.0–1.0
- **auto_applicable**: `true` only if patch can be applied without human judgment
- **observation**: REQUIRED when:
  - confidence < 0.9
  - there is a trade-off or side-effect
  - type is `manual`
  - the fix depends on context you cannot see

### Summary fields
- **summary**: one paragraph overview for humans (max 300 chars)
- **tools_used**: tool names you called
- **files_examined**: files you read or analyzed

### Good finding example
```json
{
  "id": "sec-001",
  "severity": "critical",
  "subcategory": "sql-injection",
  "file": "src/users.py",
  "line_start": 42,
  "line_end": 42,
  "title": "SQL injection via string interpolation",
  "description": "User input interpolated directly into SQL query, allowing query structure modification.",
  "evidence": "cursor.execute(f\"SELECT * FROM users WHERE id={user_id}\")",
  "suggestion": {
    "type": "replace",
    "old": "cursor.execute(f\"SELECT * FROM users WHERE id={user_id}\")",
    "new": "cursor.execute(\"SELECT * FROM users WHERE id = %s\", (user_id,))",
    "confidence": 0.99,
    "auto_applicable": true
  },
  "references": ["CWE-89", "OWASP-A03"]
}
```