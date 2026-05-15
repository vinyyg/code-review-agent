from code_review_agent.schema.report import SpecialistReport

SUBMIT_FINDINGS = {
    "name": "submit_findings",
    "description": (
        "Submit your final review findings. Call this exactly once when your "
        "investigation is complete. If you found no issues, submit with an "
        "empty findings list and explain in the summary."
    ),
    "input_schema": SpecialistReport.model_json_schema(),
}

READ_FILE = {
    "name": "read_file",
    "description": (
        "Read a file from the repository, optionally limited to a line range. "
        "Always prefer reading specific ranges over entire files to save context. "
        "Output includes 1-indexed line numbers prefixed to each line."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path relative to repo root"},
            "start_line": {"type": "integer", "minimum": 1},
            "end_line": {"type": "integer", "minimum": 1},
        },
        "required": ["path"],
    },
}

LIST_FILES = {
    "name": "list_files",
    "description": (
        "List files in a directory, optionally filtered by glob pattern. "
        "Respects .gitignore. Use to understand project structure or find related files."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Directory relative to repo root. Use '.' for root."},
            "pattern": {"type": "string", "description": "Optional glob like '**/*.py'"},
            "max_results": {"type": "integer", "minimum": 1, "maximum": 200, "default": 100},
        },
        "required": ["path"],
    },
}

GET_DIFF = {
    "name": "get_diff",
    "description": (
        "Get the diff being reviewed. Without arguments, returns the full diff. "
        "With a file argument, returns only that file's diff."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "file": {"type": "string"},
            "context_lines": {"type": "integer", "minimum": 0, "maximum": 20, "default": 3},
        },
    },
}

RUN_RUFF = {
    "name": "run_ruff",
    "description": (
        "Run ruff linter. Returns structured violations: style, unused imports, "
        "code smells, PEP-8. Prefer this over reading files manually for style checks."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "paths": {"type": "array", "items": {"type": "string"}},
            "select": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["paths"],
    },
}

RUN_BANDIT = {
    "name": "run_bandit",
    "description": (
        "Run bandit security scanner. Detects hardcoded passwords, SQL injection "
        "patterns, insecure deserialization, weak cryptography."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "paths": {"type": "array", "items": {"type": "string"}},
            "severity_threshold": {
                "type": "string",
                "enum": ["low", "medium", "high"],
                "default": "low",
            },
        },
        "required": ["paths"],
    },
}

RUN_RADON = {
    "name": "run_radon",
    "description": (
        "Compute complexity metrics: cyclomatic complexity per function and "
        "maintainability index per file. Use to identify overly complex code."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "paths": {"type": "array", "items": {"type": "string"}},
            "min_complexity": {"type": "integer", "default": 10},
        },
        "required": ["paths"],
    },
}