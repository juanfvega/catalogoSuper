import json
import os
import sqlite3
from collections.abc import Callable, Mapping, Sequence
from contextlib import closing
from pathlib import Path
from typing import Any
from uuid import uuid4


ValidationIssue = dict[str, Any]
SnapshotValidator = Callable[[Sequence[Mapping[str, Any]]], Sequence[ValidationIssue]]


class CatalogValidationError(ValueError):
    def __init__(self, issues: Sequence[ValidationIssue]):
        self.issues = list(issues)
        super().__init__("The catalog snapshot contains invalid products")


def validate_snapshot(products: Sequence[Mapping[str, Any]]) -> Sequence[ValidationIssue]:
    """Validate that each product can be stored as JSON.

    The product-field contract belongs to the catalog validator from story 6 and
    can be supplied to CatalogPublisher when that implementation is available.
    """
    issues: list[ValidationIssue] = []
    for row_number, product in enumerate(products, start=1):
        if not isinstance(product, Mapping):
            issues.append({"row": row_number, "field": "*", "message": "Product must be an object"})
            continue
        for field, value in product.items():
            try:
                json.dumps(value, allow_nan=False)
            except (TypeError, ValueError):
                issues.append(
                    {
                        "row": row_number,
                        "field": str(field),
                        "message": "Value must be valid JSON",
                    }
                )
    return issues


class SQLiteCatalogStore:
    def __init__(self, database_path: str | Path):
        self.database_path = str(database_path)
        if self.database_path != ":memory:":
            Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS catalog_versions (
                    version_id TEXT PRIMARY KEY
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS catalog_products (
                    version_id TEXT NOT NULL REFERENCES catalog_versions(version_id),
                    row_number INTEGER NOT NULL,
                    product_json TEXT NOT NULL,
                    PRIMARY KEY (version_id, row_number)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS published_catalog (
                    singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
                    version_id TEXT REFERENCES catalog_versions(version_id)
                )
                """
            )
            connection.execute(
                "INSERT OR IGNORE INTO published_catalog (singleton_id, version_id) VALUES (1, NULL)"
            )

    def publish(self, products: Sequence[Mapping[str, Any]]) -> str:
        version_id = str(uuid4())
        with closing(self._connect()) as connection, connection:
            connection.execute(
                "INSERT INTO catalog_versions (version_id) VALUES (?)", (version_id,)
            )
            for row_number, product in enumerate(products, start=1):
                self._insert_product(connection, version_id, row_number, product)
            self._activate_version(connection, version_id)
        return version_id

    def _insert_product(
        self,
        connection: sqlite3.Connection,
        version_id: str,
        row_number: int,
        product: Mapping[str, Any],
    ) -> None:
        product_json = json.dumps(product, allow_nan=False, separators=(",", ":"))
        connection.execute(
            """
            INSERT INTO catalog_products (version_id, row_number, product_json)
            VALUES (?, ?, ?)
            """,
            (version_id, row_number, product_json),
        )

    def _activate_version(self, connection: sqlite3.Connection, version_id: str) -> None:
        connection.execute(
            "UPDATE published_catalog SET version_id = ? WHERE singleton_id = 1",
            (version_id,),
        )

    def get_published_snapshot(self) -> dict[str, Any]:
        with closing(self._connect()) as connection:
            connection.execute("BEGIN")
            published = connection.execute(
                "SELECT version_id FROM published_catalog WHERE singleton_id = 1"
            ).fetchone()
            version_id = published["version_id"]
            if version_id is None:
                connection.commit()
                return {"version_id": None, "products": []}

            rows = connection.execute(
                """
                SELECT product_json
                FROM catalog_products
                WHERE version_id = ?
                ORDER BY row_number
                """,
                (version_id,),
            ).fetchall()
            products = [json.loads(row["product_json"]) for row in rows]
            connection.commit()
            return {"version_id": version_id, "products": products}


class CatalogPublisher:
    def __init__(
        self,
        store: SQLiteCatalogStore,
        validator: SnapshotValidator = validate_snapshot,
    ):
        self.store = store
        self.validator = validator

    def publish(self, products: Sequence[Mapping[str, Any]]) -> str:
        issues = self.validator(products)
        if issues:
            raise CatalogValidationError(issues)
        return self.store.publish(products)


def default_catalog_store() -> SQLiteCatalogStore:
    default_path = Path(__file__).resolve().parents[2] / "catalog.db"
    database_path = os.environ.get("CATALOG_DATABASE_PATH", str(default_path))
    return SQLiteCatalogStore(database_path)
