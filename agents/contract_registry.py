"""
ContractRegistry — Single source of truth for API and DB schema contracts.

Solves: [04] Conflicting outputs · [14] API mismatch · [16] DB drift · [17] Duplicate logic · [18] Non-deterministic output
"""

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class APIContract:
    """Represents a registered API endpoint contract."""

    def __init__(self, endpoint: str, method: str, request_schema: dict,
                 response_schema: dict, auth_required: bool, registered_by: str):
        self.endpoint = endpoint
        self.method = method
        self.request_schema = request_schema
        self.response_schema = response_schema
        self.auth_required = auth_required
        self.registered_by = registered_by
        self.version = 1
        self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "endpoint": self.endpoint, "method": self.method,
            "request_schema": self.request_schema,
            "response_schema": self.response_schema,
            "auth_required": self.auth_required,
            "registered_by": self.registered_by,
            "version": self.version, "created_at": self.created_at,
        }


class SchemaContract:
    """Represents a registered DB table schema."""

    def __init__(self, table_name: str, columns: List[dict],
                 constraints: List[str], registered_by: str):
        self.table_name = table_name
        self.columns = columns
        self.constraints = constraints
        self.registered_by = registered_by
        self.version = 1
        self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "table_name": self.table_name, "columns": self.columns,
            "constraints": self.constraints, "registered_by": self.registered_by,
            "version": self.version, "created_at": self.created_at,
        }


class ContractRegistry:
    """
    Central registry for all contracts between agents.
    Prevents drift by making agents read contracts instead of guessing.

    [04] DB Agent registers schema → Backend reads it (not invents its own)
    [14] Backend registers API → Frontend reads it (not assumes endpoints)
    [16] Schema changes must go through registry → prevents drift
    [17] Shared validation rules registered once, consumed by all
    [18] Output pinning — same context produces cached output
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._api_contracts: Dict[str, APIContract] = {}
            cls._schema_contracts: Dict[str, SchemaContract] = {}
            cls._validation_rules: Dict[str, dict] = {}
            cls._output_cache: Dict[str, str] = {}
            cls._change_log: List[dict] = []
        return cls._instance

    # --- API Contracts [14] ---

    def register_api(self, endpoint: str, method: str, request_schema: dict,
                     response_schema: dict, auth_required: bool,
                     registered_by: str) -> APIContract:
        key = f"{method.upper()} {endpoint}"
        contract = APIContract(endpoint, method, request_schema,
                               response_schema, auth_required, registered_by)
        old = self._api_contracts.get(key)
        if old:
            contract.version = old.version + 1
        self._api_contracts[key] = contract
        self._log_change("api_contract", key, registered_by, contract.version)
        return contract

    def get_api(self, endpoint: str, method: str = "GET") -> Optional[APIContract]:
        return self._api_contracts.get(f"{method.upper()} {endpoint}")

    def get_all_apis(self) -> List[dict]:
        return [c.to_dict() for c in self._api_contracts.values()]

    # --- Schema Contracts [16] ---

    def register_schema(self, table_name: str, columns: List[dict],
                        constraints: List[str], registered_by: str) -> SchemaContract:
        contract = SchemaContract(table_name, columns, constraints, registered_by)
        old = self._schema_contracts.get(table_name)
        if old:
            contract.version = old.version + 1
        self._schema_contracts[table_name] = contract
        self._log_change("schema_contract", table_name, registered_by, contract.version)
        return contract

    def get_schema(self, table_name: str) -> Optional[SchemaContract]:
        return self._schema_contracts.get(table_name)

    def get_all_schemas(self) -> List[dict]:
        return [c.to_dict() for c in self._schema_contracts.values()]

    # --- Validation Rules [17] ---

    def register_validation(self, name: str, rule: dict, applies_to: List[str]) -> None:
        self._validation_rules[name] = {
            "rule": rule, "applies_to": applies_to,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    def get_validations(self, domain: str) -> List[dict]:
        return [v for v in self._validation_rules.values() if domain in v["applies_to"]]

    # --- Output Pinning [18] ---

    def pin_output(self, agent_name: str, context: str, output: str) -> None:
        key = self._hash(f"{agent_name}:{context}")
        self._output_cache[key] = output

    def get_pinned(self, agent_name: str, context: str) -> Optional[str]:
        key = self._hash(f"{agent_name}:{context}")
        return self._output_cache.get(key)

    # --- Mismatch Detection ---

    def detect_mismatches(self) -> List[str]:
        """Find conflicts between registered contracts."""
        issues = []
        for key, api in self._api_contracts.items():
            # Check if API references tables that exist in schema
            for field in self._extract_fields(api.request_schema):
                found = False
                for schema in self._schema_contracts.values():
                    col_names = [c.get("name", "") for c in schema.columns]
                    if field in col_names:
                        found = True
                        break
                if not found and field not in ["id", "created_at", "updated_at"]:
                    issues.append(f"API '{key}' references field '{field}' not in any schema")
        return issues

    # --- Change Log ---

    def get_change_log(self) -> List[dict]:
        return list(self._change_log)

    # --- Helpers ---

    def _log_change(self, contract_type: str, key: str, by: str, version: int):
        self._change_log.append({
            "type": contract_type, "key": key, "by": by,
            "version": version, "at": datetime.now(timezone.utc).isoformat(),
        })

    @staticmethod
    def _hash(text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()[:16]

    @staticmethod
    def _extract_fields(schema: dict) -> List[str]:
        if isinstance(schema, dict):
            return list(schema.get("properties", schema).keys())
        return []

    def clear(self):
        """Reset (for tests)."""
        self._api_contracts.clear()
        self._schema_contracts.clear()
        self._validation_rules.clear()
        self._output_cache.clear()
        self._change_log.clear()


# Global instance
contract_registry = ContractRegistry()
