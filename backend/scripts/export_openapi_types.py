"""Export FastAPI OpenAPI component schemas as frontend TypeScript aliases."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.main import app  # noqa: E402


def type_for(schema: dict) -> str:
    if "$ref" in schema:
        return "components[\"schemas\"][\"" + schema["$ref"].rsplit("/", 1)[-1] + "\"]"
    if schema.get("type") == "null":
        return "null"
    if "enum" in schema:
        return " | ".join(json.dumps(value) for value in schema["enum"])
    if "anyOf" in schema or "oneOf" in schema:
        return " | ".join(type_for(item) for item in schema.get("anyOf", schema.get("oneOf", [])))
    if schema.get("type") == "array":
        return f"Array<{type_for(schema.get('items', {}))}>"
    if schema.get("type") == "object" or "properties" in schema:
        properties = schema.get("properties", {})
        if not properties:
            additional = schema.get("additionalProperties")
            return f"Record<string, {type_for(additional)}>" if isinstance(additional, dict) else "Record<string, unknown>"
        required = set(schema.get("required", []))
        fields = []
        for field, value in properties.items():
            optional = "" if field in required else "?"
            fields.append(f"{json.dumps(field)}{optional}: {type_for(value)}")
        return "{ " + "; ".join(fields) + " }"
    if schema.get("type") == "integer" or schema.get("type") == "number":
        return "number"
    if schema.get("type") == "boolean":
        return "boolean"
    if schema.get("type") == "string":
        return "string"
    return "unknown"


def main() -> None:
    schema = app.openapi()
    definitions = schema.get("components", {}).get("schemas", {})
    lines = ["/* Generated from FastAPI OpenAPI. Do not edit manually; run npm run types:api. */", "export interface components {", "  schemas: {"]
    for name in sorted(definitions):
        lines.append(f"    {json.dumps(name)}: {type_for(definitions[name])};")
    lines += ["  };", "}", "", "export interface ApiPaths {"]
    for path, methods in sorted(schema.get("paths", {}).items()):
        for method, operation in sorted(methods.items()):
            if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                continue
            key = f"{method.upper()} {path}"
            response = operation.get("responses", {}).get("200", operation.get("responses", {}).get("201", {}))
            content_schema = response.get("content", {}).get("application/json", {}).get("schema", {})
            lines.append(f"  {json.dumps(key)}: {type_for(content_schema)};")
    lines += ["}", ""]
    destination = ROOT / "frontend" / "src" / "services" / "generatedApi.ts"
    destination.write_text("\n".join(lines), encoding="utf-8")
    print(f"Generated {destination.relative_to(ROOT)} from {len(schema.get('paths', {}))} OpenAPI paths")


if __name__ == "__main__":
    main()
