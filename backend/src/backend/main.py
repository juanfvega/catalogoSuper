import os
import secrets
from typing import Any, Literal
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from backend.catalog import (
    CatalogPublisher,
    CatalogValidationError,
    SQLiteCatalogStore,
    SnapshotValidator,
)
from backend.models import (
    CatalogVersionCreate,
    CatalogVersionRead,
    validate_import_snapshot,
)
from backend.storage import create_and_publish_catalog, get_published_catalog


bearer_scheme = HTTPBearer(auto_error=False)


class ImportSnapshot(BaseModel):
    productos: list[Any]


class ImportAccepted(BaseModel):
    operation_id: UUID
    status: Literal["received"]


def verify_import_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> None:
    expected_token = os.getenv("IMPORT_API_TOKEN")
    if not expected_token:
        raise HTTPException(
            status_code=503,
            detail="Import authentication is not configured",
        )

    if credentials is None or not secrets.compare_digest(
        credentials.credentials, expected_token
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def create_app(
    store: SQLiteCatalogStore | None = None,
    validator: SnapshotValidator | None = None,
) -> FastAPI:
    application = FastAPI()

    @application.get("/")
    def read_root():
        return {"status": "ok"}

    if store is not None:
        publisher = (
            CatalogPublisher(store, validator)
            if validator is not None
            else CatalogPublisher(store)
        )

        @application.get("/catalog")
        def read_legacy_published_catalog():
            return store.get_published_snapshot()

        @application.post("/catalog/publish", status_code=201)
        def publish_legacy_catalog(products: list[dict[str, Any]]):
            try:
                version_id = publisher.publish(products)
            except CatalogValidationError as error:
                raise HTTPException(status_code=422, detail=error.issues) from error
            return {"version_id": version_id}
    else:

        @application.get(
            "/catalog",
            response_model=CatalogVersionRead,
            summary="Read the currently published catalog",
            response_description="The currently published catalog version and products.",
            responses={404: {"description": "No catalog has been published."}},
        )
        def read_published_catalog() -> CatalogVersionRead:
            catalog = get_published_catalog()
            if catalog is None:
                raise HTTPException(
                    status_code=404,
                    detail="No catalog has been published",
                )
            return catalog

        @application.post(
            "/catalog/versions",
            response_model=CatalogVersionRead,
            status_code=201,
        )
        def create_catalog_version(request: CatalogVersionCreate) -> CatalogVersionRead:
            return create_and_publish_catalog(request.products)

    @application.post(
        "/imports",
        status_code=202,
        response_model=ImportAccepted,
        dependencies=[Depends(verify_import_token)],
    )
    def receive_import(snapshot: ImportSnapshot) -> ImportAccepted:
        errors = validate_import_snapshot(snapshot.productos)
        if errors:
            raise HTTPException(status_code=422, detail={"errors": errors})
        return ImportAccepted(operation_id=uuid4(), status="received")

    return application


app = create_app()
