import sqlite3
import tempfile
import unittest
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from backend.catalog import SQLiteCatalogStore, validate_snapshot
from backend.main import create_app


def validate_products(
    products: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {"row": row_number, "field": "sku", "message": "SKU is required"}
        for row_number, product in enumerate(products, start=1)
        if not product.get("sku")
    ]


class FaultInjectingCatalogStore(SQLiteCatalogStore):
    fail_after_first_product = False
    fail_activation = False

    def _insert_product(
        self,
        connection: sqlite3.Connection,
        version_id: str,
        row_number: int,
        product: Mapping[str, Any],
    ) -> None:
        if self.fail_after_first_product and row_number == 2:
            raise sqlite3.OperationalError("simulated product write failure")
        super()._insert_product(connection, version_id, row_number, product)

    def _activate_version(self, connection: sqlite3.Connection, version_id: str) -> None:
        if self.fail_activation:
            raise sqlite3.OperationalError("simulated activation failure")
        super()._activate_version(connection, version_id)


class CatalogPublicationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "catalog.db"
        self.store = FaultInjectingCatalogStore(database_path)
        self.client = TestClient(
            create_app(self.store, validator=validate_products),
            raise_server_exceptions=False,
        )

    def tearDown(self) -> None:
        self.client.close()
        self.temp_dir.cleanup()

    def publish(self, products: list[dict[str, Any]]) -> None:
        response = self.client.post("/catalog/publish", json=products)
        self.assertEqual(response.status_code, 201, response.text)

    def test_activation_failure_keeps_previous_catalog_visible(self) -> None:
        previous = [{"sku": "A1", "price": 4.25}]
        self.publish(previous)
        published_before_failure = self.client.get("/catalog").json()

        self.store.fail_activation = True
        response = self.client.post(
            "/catalog/publish",
            json=[{"sku": "B1", "price": 5.5}],
        )

        self.assertEqual(response.status_code, 500)
        self.assertEqual(self.client.get("/catalog").json(), published_before_failure)

    def test_partial_product_write_failure_keeps_previous_catalog_visible(self) -> None:
        previous = [{"sku": "A1", "price": 4.25}]
        self.publish(previous)
        published_before_failure = self.client.get("/catalog").json()

        self.store.fail_after_first_product = True
        response = self.client.post(
            "/catalog/publish",
            json=[{"sku": "B1"}, {"sku": "B2"}],
        )

        self.assertEqual(response.status_code, 500)
        self.assertEqual(self.client.get("/catalog").json(), published_before_failure)

    def test_invalid_snapshot_is_rejected_without_replacing_catalog(self) -> None:
        previous = [{"sku": "A1", "price": 4.25}]
        self.publish(previous)
        published_before_failure = self.client.get("/catalog").json()
        invalid_products = [{"price": 4.25}]

        response = self.client.post("/catalog/publish", json=invalid_products)

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"][0]["row"], 1)
        self.assertEqual(response.json()["detail"][0]["field"], "sku")
        self.assertEqual(self.client.get("/catalog").json(), published_before_failure)

    def test_json_validator_rejects_non_finite_values(self) -> None:
        issues = validate_snapshot([{"price": float("nan")}])

        self.assertEqual(issues[0]["row"], 1)
        self.assertEqual(issues[0]["field"], "price")

    def test_published_catalog_survives_store_reinitialization(self) -> None:
        products = [{"sku": "A1", "price": 4.25}]
        self.publish(products)

        restarted_store = SQLiteCatalogStore(self.store.database_path)

        self.assertEqual(
            restarted_store.get_published_snapshot(),
            self.client.get("/catalog").json(),
        )


if __name__ == "__main__":
    unittest.main()
