import re
from datetime import datetime
from decimal import Decimal
from typing import TypedDict

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    StrictBool,
    StrictInt,
    TypeAdapter,
    ValidationError,
    field_validator,
    model_validator,
)


_HTTP_URL = TypeAdapter(HttpUrl)
PRODUCT_CODE_PATTERN = r"^[A-Z0-9-]{3,20}$"
_IMAGE_FILENAME = re.compile(r"^[a-z0-9][a-z0-9._-]*\.(?:jpg|jpeg|png|webp)$")
_IMAGE_PUBLIC_PATH = re.compile(r"^/images/[A-Z0-9-]{3,20}$")


class SnapshotValidationError(TypedDict):
    row: int
    field: str
    message: str


class Product(BaseModel):
    model_config = ConfigDict(extra="forbid")

    codigo: str = Field(pattern=PRODUCT_CODE_PATTERN)
    nombre: str = Field(min_length=3, max_length=100)
    categoria: str = Field(min_length=3, max_length=50)
    precio: Decimal = Field(gt=0, allow_inf_nan=False)
    stock: StrictInt = Field(ge=0)
    imagen: str | None = None
    vigente: StrictBool

    @field_validator("nombre", "categoria", mode="before")
    @classmethod
    def strip_text_fields(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("imagen", mode="before")
    @classmethod
    def blank_image_is_omitted(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("imagen")
    @classmethod
    def validate_image(cls, value: str | None) -> str | None:
        if value is None:
            return None

        if _IMAGE_PUBLIC_PATH.fullmatch(value):
            return value

        try:
            image_url = _HTTP_URL.validate_python(value)
        except ValidationError:
            if not _IMAGE_FILENAME.fullmatch(value):
                raise ValueError(
                    "imagen debe ser un nombre de archivo permitido en minúsculas o una URL HTTPS válida"
                )
            return value

        if image_url.scheme != "https":
            raise ValueError("la URL de imagen debe usar HTTPS")
        return str(image_url)

    @model_validator(mode="after")
    def image_reference_matches_product_code(self) -> "Product":
        if (
            self.imagen is not None
            and _IMAGE_PUBLIC_PATH.fullmatch(self.imagen)
            and self.imagen != f"/images/{self.codigo}"
        ):
            raise ValueError("la ruta de imagen debe corresponder al codigo del producto")
        return self


class CatalogVersionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    products: list[Product]

    @model_validator(mode="after")
    def product_codes_are_unique(self) -> "CatalogVersionCreate":
        codes = [product.codigo for product in self.products]
        if len(codes) != len(set(codes)):
            raise ValueError("cada producto de la versión debe tener un codigo único")
        return self


class CatalogVersionRead(BaseModel):
    version_id: int
    created_at: datetime
    products: list[Product]


def validate_import_snapshot(products: list[object]) -> list[SnapshotValidationError]:
    errors: list[SnapshotValidationError] = []
    valid_code_rows: dict[str, list[int]] = {}

    for product_index, raw_product in enumerate(products):
        sheet_row = product_index + 2
        if isinstance(raw_product, dict):
            code = raw_product.get("codigo")
            if isinstance(code, str) and re.fullmatch(PRODUCT_CODE_PATTERN, code):
                valid_code_rows.setdefault(code, []).append(sheet_row)

        try:
            Product.model_validate(raw_product)
        except ValidationError as validation_error:
            for error in validation_error.errors():
                location = error["loc"]
                field = (
                    location[0]
                    if location and isinstance(location[0], str)
                    else "producto"
                )
                errors.append(
                    {
                        "row": sheet_row,
                        "field": field,
                        "message": error["msg"],
                    }
                )

    for code, rows in valid_code_rows.items():
        if len(rows) < 2:
            continue
        duplicate_rows = ", ".join(str(row) for row in rows)
        for sheet_row in rows:
            errors.append(
                {
                    "row": sheet_row,
                    "field": "codigo",
                    "message": f"codigo duplicado en las filas {duplicate_rows}",
                }
            )

    errors.sort(key=lambda error: (error["row"], error["field"], error["message"]))
    return errors
