from fastapi import FastAPI

from backend.models import CatalogVersionCreate, CatalogVersionRead
from backend.storage import create_and_publish_catalog

app = FastAPI()


@app.get("/")
def read_root():
    return {"status": "ok"}


@app.post(
    "/catalog/versions",
    response_model=CatalogVersionRead,
    status_code=201,
)
def create_catalog_version(request: CatalogVersionCreate) -> CatalogVersionRead:
    return create_and_publish_catalog(request.products)
