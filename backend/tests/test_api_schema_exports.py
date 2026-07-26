from routers import api_schemas, schemas


def test_legacy_api_schema_module_reexports_public_models() -> None:
    assert api_schemas.__all__ == schemas.__all__
    assert all(getattr(api_schemas, name) is getattr(schemas, name) for name in schemas.__all__)
