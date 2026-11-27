import re
from datetime import datetime
from decimal import Decimal

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
_IMAGE_FILENAME = re.compile(r"^[a-z0-9][a-z0-9._-]*\.(?:jpg|jpeg|png|webp)$")


class Product(BaseModel):
    model_config = ConfigDict(extra="forbid")

    codigo: str = Field(pattern=r"^[A-Z0-9-]{3,20}$")
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
