"""The pagination gate must inspect response envelopes behind OpenAPI refs."""
import json
import tempfile
import unittest
from pathlib import Path
import importlib.util


MODULE_PATH = Path(__file__).resolve().parents[1] / "gate_pagination.py"
SPEC = importlib.util.spec_from_file_location("gate_pagination", MODULE_PATH)
gate = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(gate)


class PaginationReferenceTests(unittest.TestCase):
    def test_envelope_reference_passes_but_array_reference_fails(self):
        spec = {
            "openapi": "3.1.0",
            "paths": {"/records": {"get": {
                "parameters": [
                    {"in": "query", "name": "limit"},
                    {"in": "query", "name": "offset"},
                ],
                "responses": {"200": {"content": {"application/json": {
                    "schema": {"$ref": "#/components/schemas/Page"},
                }}}},
            }}},
            "components": {"schemas": {
                "Page": {"type": "object", "properties": {
                    "items": {"type": "array", "items": {"type": "string"}},
                    "page": {"type": "object"},
                }},
            }},
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "openapi.json"
            path.write_text(json.dumps(spec))
            self.assertEqual(gate.check_spec(str(path), set()), [])
            del spec["components"]["schemas"]["Page"]["properties"]["page"]
            path.write_text(json.dumps(spec))
            self.assertEqual(len(gate.check_spec(str(path), set())), 1)
