import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


from config.openapi import add_api_key_security


def test_api_key_security_is_available_to_openapi_clients():
    schema = {"components": {"schemas": {"Result": {"type": "object"}}}}

    result = add_api_key_security(schema, "X-Api-Key")

    assert result is schema
    assert schema["components"]["schemas"] == {"Result": {"type": "object"}}
    assert schema["components"]["securitySchemes"]["ApiKeyAuth"] == {
        "type": "apiKey",
        "in": "header",
        "name": "X-Api-Key",
        "description": (
            "Enter the API access token. Swagger UI sends it in the "
            "X-Api-Key request header."
        ),
    }
    assert schema["security"] == [{"ApiKeyAuth": []}]
