import os
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image

from backend.image_storage import MAX_IMAGE_SIZE_BYTES
from backend.main import app


class ProductImageApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.image_directory = Path(self.temp_dir.name) / "images"
        self.database_path = Path(self.temp_dir.name) / "catalog.db"
        self.environment = patch.dict(
            os.environ,
            {
                "CATALOG_DATABASE_PATH": str(self.database_path),
                "IMPORT_API_TOKEN": "test-import-token",
                "PRODUCT_IMAGE_STORAGE_PATH": str(self.image_directory),
            },
        )
        self.environment.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        self.environment.stop()
        self.temp_dir.cleanup()

    @staticmethod
    def png_image() -> bytes:
        buffer = BytesIO()
        Image.new("RGB", (2, 2), color="red").save(buffer, format="PNG")
        return buffer.getvalue()

    def upload(self, contents: bytes, headers: dict[str, str] | None = None):
        request_headers = (
            headers
            if headers is not None
            else {"Authorization": "Bearer test-import-token"}
        )
        return self.client.post(
            "/products/PROD-001/image",
            headers=request_headers,
            files={"image": ("product.jpg", contents, "image/jpeg")},
        )

    def test_uploaded_image_has_stable_reference_and_overrides_private_url(self) -> None:
        contents = self.png_image()
        upload_response = self.upload(contents)

        self.assertEqual(upload_response.status_code, 201)
        self.assertEqual(
            upload_response.json(),
            {"codigo": "PROD-001", "imagen": "/images/PROD-001"},
        )

        public_image = self.client.get("/images/PROD-001")
        self.assertEqual(public_image.status_code, 200)
        self.assertEqual(public_image.content, contents)
        self.assertEqual(public_image.headers["content-type"], "image/png")

        catalog_response = self.client.post(
            "/catalog/versions",
            json={
                "products": [
                    {
                        "codigo": "PROD-001",
                        "nombre": "Alfajor de Dulce de Leche x6",
                        "categoria": "Panadería y Pastelería",
                        "precio": 6500,
                        "stock": 24,
                        "imagen": "https://onedrive.example/private-temporary-link",
                        "vigente": True,
                    }
                ]
            },
        )
        self.assertEqual(catalog_response.status_code, 201)
        self.assertEqual(
            catalog_response.json()["products"][0]["imagen"],
            "/images/PROD-001",
        )
        self.assertTrue((self.image_directory / "PROD-001").is_file())

    def test_upload_requires_authentication_and_rejects_invalid_images(self) -> None:
        missing_token = self.upload(
            self.png_image(),
            headers={},
        )
        invalid_image = self.upload(
            b"not an image",
        )

        self.assertEqual(missing_token.status_code, 401)
        self.assertEqual(invalid_image.status_code, 422)
        self.assertFalse((self.image_directory / "PROD-001").exists())
        self.assertEqual(self.client.get("/images/PROD-001").status_code, 404)

    def test_upload_rejects_files_over_the_size_limit(self) -> None:
        response = self.upload(b"x" * (MAX_IMAGE_SIZE_BYTES + 1))

        self.assertEqual(response.status_code, 413)
        self.assertFalse((self.image_directory / "PROD-001").exists())

    def test_invalid_product_code_is_rejected(self) -> None:
        response = self.client.post(
            "/products/prod-001/image",
            headers={"Authorization": "Bearer test-import-token"},
            files={"image": ("product.png", self.png_image(), "image/png")},
        )

        self.assertEqual(response.status_code, 422)

    def test_catalog_rejects_an_image_reference_for_a_different_product(self) -> None:
        response = self.client.post(
            "/catalog/versions",
            json={
                "products": [
                    {
                        "codigo": "PROD-001",
                        "nombre": "Alfajor de Dulce de Leche x6",
                        "categoria": "Panadería y Pastelería",
                        "precio": 6500,
                        "stock": 24,
                        "imagen": "/images/PROD-002",
                        "vigente": True,
                    }
                ]
            },
        )

        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
