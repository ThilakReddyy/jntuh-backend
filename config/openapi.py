"""Helpers for decorating the generated OpenAPI schema."""


OPENAPI_SERVERS = (
    {"url": "http://localhost:8000/", "description": "Local development"},
    {"url": "https://jntuhresults.dhethi.com/", "description": "Production"},
)


def add_servers(schema: dict) -> dict:
    """Expose the available API environments to OpenAPI clients."""
    schema["servers"] = [dict(server) for server in OPENAPI_SERVERS]
    return schema


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
