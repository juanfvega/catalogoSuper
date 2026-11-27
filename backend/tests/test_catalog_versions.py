import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.main import app
from backend.storage import get_catalog_version, get_published_catalog


class CatalogVersionApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "catalog.db"
        self.database_env = patch.dict(
            "os.environ",
            {"CATALOG_DATABASE_PATH": str(self.database_path)},
        )
        self.database_env.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.database_env.stop()
        self.temp_dir.cleanup()

    @staticmethod
    def sample_product(**overrides: object) -> dict[str, object]:
        product: dict[str, object] = {
            "codigo": "PROD-001",
            "nombre": "Alfajor de Dulce de Leche x6",
            "categoria": "Panadería y Pastelería",
            "precio": 6500.00,
            "stock": 24,
            "vigente": True,
        }
        product.update(overrides)
        return product

    def test_post_publishes_catalog_and_keeps_previous_snapshots(self) -> None:
        first_response = self.client.post(
            "/catalog/versions",
            json={"products": [self.sample_product()]},
        )

        self.assertEqual(first_response.status_code, 201)
        first_version = first_response.json()
        self.assertEqual(first_version["version_id"], 1)
        self.assertIsNone(first_version["products"][0]["imagen"])

        second_response = self.client.post(
            "/catalog/versions",
            json={
                "products": [
                    self.sample_product(nombre="Alfajor actualizado")
                ]
            },
        )

        self.assertEqual(second_response.status_code, 201)
        self.assertEqual(second_response.json()["version_id"], 2)

        # Each storage call opens a new connection to the same file-backed database.
        published = get_published_catalog(self.database_path)
        previous = get_catalog_version(1, self.database_path)
        self.assertIsNotNone(published)
        self.assertEqual(published.version_id, 2)
        self.assertEqual(published.products[0].nombre, "Alfajor actualizado")
        self.assertIsNotNone(previous)
        self.assertEqual(previous.products[0].nombre, "Alfajor de Dulce de Leche x6")

    def test_invalid_product_fields_are_rejected(self) -> None:
        invalid_fields = (
            ("codigo", "prod-001"),
            ("nombre", "Ab"),
            ("categoria", "AB"),
            ("precio", 0),
            ("stock", -1),
            ("imagen", "foto.JPG"),
            ("vigente", "SI"),
        )

        for field, value in invalid_fields:
            with self.subTest(field=field):
                response = self.client.post(
                    "/catalog/versions",
                    json={"products": [self.sample_product(**{field: value})]},
                )
                self.assertEqual(response.status_code, 422)

        self.assertIsNone(get_published_catalog(self.database_path))

    def test_duplicate_product_codes_in_a_snapshot_are_rejected(self) -> None:
        response = self.client.post(
            "/catalog/versions",
            json={
                "products": [
                    self.sample_product(),
                    self.sample_product(nombre="Otro producto"),
                ]
            },
        )

        self.assertEqual(response.status_code, 422)
        self.assertIsNone(get_published_catalog(self.database_path))

    def test_supported_images_and_blank_image_are_accepted(self) -> None:
        image_values = (
            ("prod-001.jpg", "prod-001.jpg"),
            (
                "https://example.com/products/prod-001.png",
                "https://example.com/products/prod-001.png",
            ),
            ("", None),
        )

        for image, expected in image_values:
            with self.subTest(image=image):
                response = self.client.post(
                    "/catalog/versions",
                    json={"products": [self.sample_product(imagen=image)]},
                )
                self.assertEqual(response.status_code, 201)
                self.assertEqual(response.json()["products"][0]["imagen"], expected)

    def test_health_check_remains_available(self) -> None:
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})


if __name__ == "__main__":
    unittest.main()
