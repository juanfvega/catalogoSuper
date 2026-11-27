import logging
import os
import secrets
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, File, HTTPException, Path, UploadFile
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from backend.catalog import (
    CatalogPublisher,
    CatalogValidationError,
    SQLiteCatalogStore,
    SnapshotValidator,
)
from backend.image_storage import (
    MAX_IMAGE_SIZE_BYTES,
    InvalidProductImage,
    ProductImageTooLarge,
    get_product_image,
    has_product_image,
    product_image_reference,
    store_product_image,
)
from backend.models import (
    PRODUCT_CODE_PATTERN,
    CatalogVersionCreate,
    CatalogVersionRead,
    ImportOperationRead,
    Product,
    validate_import_snapshot,
)
from backend.storage import (
    complete_import_operation,
    create_and_publish_catalog,
    create_import_operation,
    fail_import_operation,
    get_import_operation,
    get_published_catalog,
)


bearer_scheme = HTTPBearer(auto_error=False)
logger = logging.getLogger(__name__)

IMPORT_PUBLICATION_FAILURE_MESSAGE = (
    "No se pudo confirmar la publicación. Verifique el catálogo publicado y los "
    "registros del servicio antes de volver a enviar el snapshot."
)


class ImportSnapshot(BaseModel):
    productos: list[Any]


class ImportAccepted(BaseModel):
    operation_id: UUID
    status: Literal["received"]


class ProductImageStored(BaseModel):
    codigo: str
    imagen: str


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
            products = [
                product.model_copy(
                    update={"imagen": product_image_reference(product.codigo)}
                )
                if has_product_image(product.codigo)
                else product
                for product in request.products
            ]
            return create_and_publish_catalog(products)

    @application.post(
        "/products/{codigo}/image",
        response_model=ProductImageStored,
        status_code=201,
        dependencies=[Depends(verify_import_token)],
    )
    async def upload_product_image(
        codigo: Annotated[str, Path(pattern=PRODUCT_CODE_PATTERN)],
        image: Annotated[UploadFile, File()],
    ) -> ProductImageStored:
        try:
            contents = await image.read(MAX_IMAGE_SIZE_BYTES + 1)
        finally:
            await image.close()

        try:
            reference = store_product_image(codigo, contents)
        except ProductImageTooLarge as error:
            raise HTTPException(
                status_code=413,
                detail=f"Image must not exceed {MAX_IMAGE_SIZE_BYTES} bytes",
            ) from error
        except InvalidProductImage as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

        return ProductImageStored(codigo=codigo, imagen=reference)

    @application.get("/images/{codigo}")
    def read_product_image(
        codigo: Annotated[str, Path(pattern=PRODUCT_CODE_PATTERN)],
    ) -> FileResponse:
        try:
            path, media_type = get_product_image(codigo)
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=404, detail="Product image not found"
            ) from error
        return FileResponse(
            path,
            media_type=media_type,
            headers={"Cache-Control": "no-cache"},
        )

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
        operation_id = uuid4()
        create_import_operation(operation_id)
        try:
            products = [
                Product.model_validate(product) for product in snapshot.productos
            ]
            products = [
                product.model_copy(
                    update={"imagen": product_image_reference(product.codigo)}
                )
                if has_product_image(product.codigo)
                else product
                for product in products
            ]
            published = create_and_publish_catalog(products)
        except Exception:
            logger.exception(
                "Import operation %s failed during publication", operation_id
            )
            fail_import_operation(operation_id, IMPORT_PUBLICATION_FAILURE_MESSAGE)
        else:
            complete_import_operation(operation_id, published.version_id)
        return ImportAccepted(operation_id=operation_id, status="received")

    @application.get(
        "/imports/{operation_id}",
        response_model=ImportOperationRead,
        dependencies=[Depends(verify_import_token)],
    )
    def read_import_operation(operation_id: UUID) -> ImportOperationRead:
        operation = get_import_operation(operation_id)
        if operation is None:
            raise HTTPException(status_code=404, detail="Import operation not found")
        return operation

    return application


app = create_app()
