from typing import Any

from fastapi import FastAPI, HTTPException

from backend.catalog import (
    CatalogPublisher,
    CatalogValidationError,
    SQLiteCatalogStore,
    SnapshotValidator,
    default_catalog_store,
    validate_snapshot,
)


def create_app(
    store: SQLiteCatalogStore | None = None,
    validator: SnapshotValidator = validate_snapshot,
) -> FastAPI:
    publisher = CatalogPublisher(
        store if store is not None else default_catalog_store(),
        validator,
    )
    app = FastAPI()

    @app.get("/")
    def read_root() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/catalog")
    def read_catalog() -> dict[str, Any]:
        return publisher.store.get_published_snapshot()

    @app.post("/catalog/publish", status_code=201)
    def publish_catalog(products: list[dict[str, Any]]) -> dict[str, str]:
        try:
            version_id = publisher.publish(products)
        except CatalogValidationError as error:
            raise HTTPException(status_code=422, detail=error.issues) from error
        return {"version_id": version_id}

    return app


app = create_app()
