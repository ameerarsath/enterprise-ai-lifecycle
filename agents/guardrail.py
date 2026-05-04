"""
GuardRail — Input sanitization and output validation.

Solves: [25] Secrets · [28] Injection · [05] Hallucination · [15] Code quality · [29] Compliance · [13] Style
"""

import re
from typing import Any, Dict, List, Tuple


class SecretScanner:
    """Scans agent output for hardcoded secrets. [25]"""

    PATTERNS = [
        (r'(?i)(api[_-]?key|secret[_-]?key|password|token)\s*[=:]\s*["\'][A-Za-z0-9+/=_\-]{8,}["\']', "Generic secret"),
        (r'sk-[a-zA-Z0-9]{20,}', "OpenAI key"),
        (r'sk-ant-[a-zA-Z0-9\-]{20,}', "Anthropic key"),
        (r'ghp_[a-zA-Z0-9]{36}', "GitHub PAT"),
        (r'AKIA[0-9A-Z]{16}', "AWS key"),
        (r'-----BEGIN (RSA |EC )?PRIVATE KEY-----', "Private key"),
        (r'(?i)(postgres|mysql|mongodb)://[^\s"\']+:[^\s"\']+@', "DB connection string"),
        (r'eyJ[a-zA-Z0-9_-]{10,}\.eyJ[a-zA-Z0-9_-]{10,}', "JWT token"),
    ]

    @classmethod
    def scan(cls, text: str) -> List[Dict[str, str]]:
        findings = []
        for pattern, desc in cls.PATTERNS:
            for m in re.finditer(pattern, text):
                findings.append({"type": desc, "match": m.group()[:50], "pos": m.start()})
        return findings

    @classmethod
    def redact(cls, text: str) -> str:
        for pattern, _ in cls.PATTERNS:
            text = re.sub(pattern, "[REDACTED]", text)
        return text

    @classmethod
    def has_secrets(cls, text: str) -> bool:
        return len(cls.scan(text)) > 0


class InputSanitizer:
    """Prompt injection defense. [28]"""

    INJECTION_PATTERNS = [
        (r'(?i)ignore\s+(?:all\s+)?(?:previous|above|prior)\s+(?:instructions?|prompts?)', "Instruction override"),
        (r'(?i)ignore\s+all\s+(?:instructions?|prompts?)', "Instruction override"),
        (r'(?i)you\s+are\s+now\s+a', "Role hijacking"),
        (r'(?i)forget\s+(?:everything|all)', "Memory wipe"),
        (r'(?i)system\s*:\s*', "System prompt injection"),
        (r'<\|[^|]*\|>', "Control token injection"),
        (r'\[INST\]|\[/INST\]', "Instruction tag injection"),
        (r'(?i)reveal\s+(?:your|the)\s+(?:system|hidden|initial)\s+(?:prompt|instructions?)', "Prompt extraction"),
    ]

    @classmethod
    def detect_injection(cls, text: str) -> List[Dict[str, str]]:
        findings = []
        for pattern, desc in cls.INJECTION_PATTERNS:
            for m in re.finditer(pattern, text):
                findings.append({"type": desc, "match": m.group(), "pos": m.start()})
        return findings

    @classmethod
    def sanitize(cls, text: str) -> str:
        result = text
        for pattern, _ in cls.INJECTION_PATTERNS:
            result = re.sub(pattern, "[FILTERED]", result)
        return result

    @classmethod
    def is_safe(cls, text: str) -> bool:
        return len(cls.detect_injection(text)) == 0


class OutputValidator:
    """Prevents agent hallucinated completions. [05]"""

    EXPECTED_ARTIFACTS = {
        "business_analyst": "prd",
        "scrum_master": "backlog",
        "seo": "seo_strategy",
        "frontend": "frontend_code",
        "backend": "backend_code",
        "database": "db_schema",
        "qa": "tests",
        "security": "security_audit",
        "deploy": "deployment",
    }

    @classmethod
    def validate(cls, agent_name: str, output: Dict[str, Any]) -> Tuple[bool, List[str]]:
        issues = []
        expected_key = cls.EXPECTED_ARTIFACTS.get(agent_name)
        if expected_key:
            artifacts = output.get("artifacts", {})
            val = artifacts.get(expected_key)
            if val is None:
                issues.append(f"Missing artifact '{expected_key}' from {agent_name}")
            elif isinstance(val, str) and len(val.strip()) < 50:
                issues.append(f"Suspiciously short artifact '{expected_key}' ({len(val)} chars)")
        messages = output.get("messages", [])
        if not messages:
            issues.append(f"No messages from {agent_name}")
        return len(issues) == 0, issues


class CodeQualityChecker:
    """Checks for missing error handling. [15]"""

    @classmethod
    def check(cls, code: str) -> List[str]:
        issues = []
        if re.findall(r'async\s+def\s+\w+', code) and not re.search(r'try\s*:', code):
            issues.append("Async functions without try/except")
        if re.search(r'except\s*:', code):
            issues.append("Bare except clause")
        if re.search(r'(fetch|axios)\s*\(', code):
            if not re.search(r'(\.catch\(|try\s*{)', code):
                issues.append("API calls without error handling")
        return issues


class ComplianceChecker:
    """GDPR/HIPAA compliance checks. [29]"""

    @classmethod
    def check(cls, code: str) -> List[str]:
        issues = []
        pii = re.search(r'(?i)(email|phone|ssn|date_of_birth)', code)
        if pii:
            for log_pat in [r'print\(', r'log\.\w+\(', r'logger\.\w+\(', r'console\.log\(']:
                if re.search(f'{log_pat}[^)]*(?i)(email|phone|ssn)', code):
                    issues.append("PII potentially logged — GDPR concern")
                    break
            if not re.search(r'(?i)(encrypt|hash|bcrypt|argon)', code):
                issues.append("PII stored without encryption/hashing")
        return issues


class StyleEnforcer:
    """Code style rules per agent type. [13]"""

    RULES = {
        "frontend": "camelCase, TypeScript strict, Tailwind only, absolute imports",
        "backend": "snake_case, PEP 8, type hints, Pydantic v2, service layer pattern",
        "database": "snake_case tables, UUID PKs, soft deletes, created_at/updated_at",
    }

    @classmethod
    def get_style_prompt(cls, agent_name: str) -> str:
        rule = cls.RULES.get(agent_name, "")
        return f"\nCODE STYLE: {rule}" if rule else ""


class GuardRail:
    """Central validation facade."""

    @classmethod
    def validate_input(cls, raw_brief: str) -> Tuple[str, List[Dict]]:
        warnings = InputSanitizer.detect_injection(raw_brief)
        if warnings:
            raw_brief = InputSanitizer.sanitize(raw_brief)
        return raw_brief, warnings

    @classmethod
    def validate_output(cls, agent_name: str, output: Dict[str, Any]) -> Tuple[Dict, List[str]]:
        issues = []
        # Scan for secrets
        output = cls._redact_secrets(output, issues)
        # Validate completeness
        _, val_issues = OutputValidator.validate(agent_name, output)
        issues.extend(val_issues)
        # Code quality
        for key in ["frontend_code", "backend_code", "db_schema"]:
            code = output.get("artifacts", {}).get(key, "")
            if isinstance(code, str) and len(code) > 100:
                issues.extend(CodeQualityChecker.check(code))
                issues.extend(ComplianceChecker.check(code))
        return output, issues

    @classmethod
    def _redact_secrets(cls, output: Dict, issues: List[str]) -> Dict:
        cleaned = {}
        for k, v in output.items():
            if isinstance(v, str) and SecretScanner.has_secrets(v):
                for f in SecretScanner.scan(v):
                    issues.append(f"Secret ({f['type']}) in '{k}'")
                v = SecretScanner.redact(v)
            elif isinstance(v, dict):
                v = cls._redact_secrets(v, issues)
            cleaned[k] = v
        return cleaned
