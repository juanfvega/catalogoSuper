import os
import re
import tempfile
import warnings
from io import BytesIO
from pathlib import Path

from PIL import Image

from backend.models import PRODUCT_CODE_PATTERN


MAX_IMAGE_SIZE_BYTES = 10 * 1024 * 1024
_SUPPORTED_IMAGE_TYPES = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}
_PRODUCT_CODE = re.compile(PRODUCT_CODE_PATTERN)


class InvalidProductImage(ValueError):
    pass


class ProductImageTooLarge(ValueError):
    pass


def product_image_reference(codigo: str) -> str:
    _validate_product_code(codigo)
    return f"/images/{codigo}"


def _validate_product_code(codigo: str) -> None:
    if not _PRODUCT_CODE.fullmatch(codigo):
        raise ValueError("codigo de producto inválido")


def _image_directory() -> Path:
    configured_directory = os.environ.get("PRODUCT_IMAGE_STORAGE_PATH")
    if configured_directory:
        return Path(configured_directory)
    return Path(__file__).resolve().parents[2] / "data" / "product-images"


def _image_path(codigo: str) -> Path:
    _validate_product_code(codigo)
    return _image_directory() / codigo


def _validate_image(contents: bytes) -> str:
    if len(contents) > MAX_IMAGE_SIZE_BYTES:
        raise ProductImageTooLarge

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(contents)) as image:
                image_format = image.format
                if (
                    not isinstance(image_format, str)
                    or image_format not in _SUPPORTED_IMAGE_TYPES
                ):
                    raise InvalidProductImage(
                        "Solo se admiten imágenes JPEG, PNG o WebP"
                    )
                image.verify()
    except InvalidProductImage:
        raise
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        OSError,
        SyntaxError,
    ) as error:
        raise InvalidProductImage("El archivo no contiene una imagen válida") from error

    return image_format


def store_product_image(codigo: str, contents: bytes) -> str:
    image_format = _validate_image(contents)
    destination = _image_path(codigo)
    destination.parent.mkdir(parents=True, exist_ok=True)

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=destination.parent,
            prefix=f".{codigo}.",
            delete=False,
        ) as staged_file:
            temporary_path = Path(staged_file.name)
            staged_file.write(contents)
            staged_file.flush()
            os.fsync(staged_file.fileno())
        os.replace(temporary_path, destination)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

    return product_image_reference(codigo)


def has_product_image(codigo: str) -> bool:
    return _image_path(codigo).is_file()


def get_product_image(codigo: str) -> tuple[Path, str]:
    path = _image_path(codigo)
    try:
        with Image.open(path) as image:
            image_format = image.format
    except FileNotFoundError:
        raise
    except (Image.DecompressionBombError, OSError, SyntaxError) as error:
        raise InvalidProductImage("La imagen almacenada no es válida") from error

    media_type = _SUPPORTED_IMAGE_TYPES.get(image_format or "")
    if media_type is None:
        raise InvalidProductImage("El formato de imagen almacenado no está permitido")
    return path, media_type
