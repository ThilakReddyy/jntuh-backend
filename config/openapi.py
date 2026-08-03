"""Helpers for decorating the generated OpenAPI schema."""


def add_api_key_security(schema: dict, header_name: str) -> dict:
    """Expose a global header API-key input in OpenAPI clients such as Swagger."""
    security_schemes = schema.setdefault("components", {}).setdefault(
        "securitySchemes", {}
    )
    security_schemes["ApiKeyAuth"] = {
        "type": "apiKey",
        "in": "header",
        "name": header_name,
        "description": (
            "Enter the API access token. Swagger UI sends it in the "
            f"{header_name} request header."
        ),
    }
    schema["security"] = [{"ApiKeyAuth": []}]
    return schema
