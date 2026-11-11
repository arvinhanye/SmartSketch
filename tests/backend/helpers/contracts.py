"""Translate OpenAPI component references for standalone JSON Schema validators."""


def rewrite_schema_refs(node):
    if isinstance(node, dict):
        return {
            key: (value.replace("#/components/schemas/", "#/$defs/")
                  if key == "$ref" and isinstance(value, str) else rewrite_schema_refs(value))
            for key, value in node.items()
        }
    if isinstance(node, list):
        return [rewrite_schema_refs(item) for item in node]
    return node
