import os
import sqlite3
from contextlib import closing
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from backend.models import CatalogVersionRead, ImportOperationRead, Product


_DEFAULT_DATABASE_PATH = Path(__file__).resolve().parents[2] / "data" / "catalog.db"


def _database_path(database_path: str | Path | None = None) -> Path:
    if database_path is not None:
        return Path(database_path)
    configured_path = os.environ.get("CATALOG_DATABASE_PATH")
    if configured_path:
        return Path(configured_path)
    return _DEFAULT_DATABASE_PATH


def _connect(database_path: str | Path | None = None) -> sqlite3.Connection:
    path = _database_path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _initialize_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS catalog_versions (
            version_id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        );

        CREATE TABLE IF NOT EXISTS products (
            version_id INTEGER NOT NULL REFERENCES catalog_versions(version_id),
            codigo TEXT NOT NULL,
            nombre TEXT NOT NULL,
            categoria TEXT NOT NULL,
            precio TEXT NOT NULL,
            stock INTEGER NOT NULL CHECK (stock >= 0),
            imagen TEXT,
            vigente INTEGER NOT NULL CHECK (vigente IN (0, 1)),
            PRIMARY KEY (version_id, codigo)
        );

        CREATE TABLE IF NOT EXISTS catalog_state (
            singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
            published_version_id INTEGER NOT NULL
                REFERENCES catalog_versions(version_id)
        );

        CREATE TABLE IF NOT EXISTS import_operations (
            operation_id TEXT PRIMARY KEY,
            status TEXT NOT NULL CHECK (status IN ('received', 'published', 'failed')),
            version_id INTEGER REFERENCES catalog_versions(version_id),
            message TEXT,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        );
        """
    )


def _product_from_row(row: sqlite3.Row) -> Product:
    return Product(
        codigo=row["codigo"],
        nombre=row["nombre"],
        categoria=row["categoria"],
        precio=Decimal(row["precio"]),
        stock=row["stock"],
        imagen=row["imagen"],
        vigente=bool(row["vigente"]),
    )


def _version_from_row(
    connection: sqlite3.Connection, version_row: sqlite3.Row
) -> CatalogVersionRead:
    product_rows = connection.execute(
        """
        SELECT codigo, nombre, categoria, precio, stock, imagen, vigente
        FROM products
        WHERE version_id = ?
        ORDER BY codigo
        """,
        (version_row["version_id"],),
    ).fetchall()
    return CatalogVersionRead(
        version_id=version_row["version_id"],
        created_at=version_row["created_at"],
        products=[_product_from_row(row) for row in product_rows],
    )


def create_and_publish_catalog(
    products: list[Product], database_path: str | Path | None = None
) -> CatalogVersionRead:
    with closing(_connect(database_path)) as connection:
        _initialize_schema(connection)
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute("INSERT INTO catalog_versions DEFAULT VALUES")
            version_id = cursor.lastrowid
            if version_id is None:
                raise RuntimeError("SQLite no devolvió el identificador de versión")

            connection.executemany(
                """
                INSERT INTO products
                    (version_id, codigo, nombre, categoria, precio, stock, imagen, vigente)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        version_id,
                        product.codigo,
                        product.nombre,
                        product.categoria,
                        format(product.precio, "f"),
                        product.stock,
                        product.imagen,
                        int(product.vigente),
                    )
                    for product in products
                ],
            )
            connection.execute(
                """
                INSERT INTO catalog_state (singleton, published_version_id)
                VALUES (1, ?)
                ON CONFLICT(singleton) DO UPDATE SET
                    published_version_id = excluded.published_version_id
                """,
                (version_id,),
            )
            version_row = connection.execute(
                "SELECT version_id, created_at FROM catalog_versions WHERE version_id = ?",
                (version_id,),
            ).fetchone()
            if version_row is None:
                raise RuntimeError("No se pudo recuperar la versión recién creada")
            return _version_from_row(connection, version_row)


def get_published_catalog(
    database_path: str | Path | None = None,
) -> CatalogVersionRead | None:
    with closing(_connect(database_path)) as connection:
        _initialize_schema(connection)
        version_row = connection.execute(
            """
            SELECT versions.version_id, versions.created_at
            FROM catalog_state
            JOIN catalog_versions AS versions
                ON versions.version_id = catalog_state.published_version_id
            WHERE catalog_state.singleton = 1
            """
        ).fetchone()
        if version_row is None:
            return None
        return _version_from_row(connection, version_row)


def get_catalog_version(
    version_id: int, database_path: str | Path | None = None
) -> CatalogVersionRead | None:
    with closing(_connect(database_path)) as connection:
        _initialize_schema(connection)
        version_row = connection.execute(
            "SELECT version_id, created_at FROM catalog_versions WHERE version_id = ?",
            (version_id,),
        ).fetchone()
        if version_row is None:
            return None
        return _version_from_row(connection, version_row)


def create_import_operation(
    operation_id: UUID, database_path: str | Path | None = None
) -> None:
    with closing(_connect(database_path)) as connection:
        _initialize_schema(connection)
        with connection:
            connection.execute(
                """
                INSERT INTO import_operations (operation_id, status)
                VALUES (?, 'received')
                """,
                (str(operation_id),),
            )


def complete_import_operation(
    operation_id: UUID,
    version_id: int,
    database_path: str | Path | None = None,
) -> None:
    with closing(_connect(database_path)) as connection:
        _initialize_schema(connection)
        with connection:
            cursor = connection.execute(
                """
                UPDATE import_operations
                SET status = 'published', version_id = ?, message = NULL
                WHERE operation_id = ? AND status = 'received'
                """,
                (version_id, str(operation_id)),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("No se pudo guardar el resultado de la importación")


def fail_import_operation(
    operation_id: UUID,
    message: str,
    database_path: str | Path | None = None,
) -> None:
    with closing(_connect(database_path)) as connection:
        _initialize_schema(connection)
        with connection:
            cursor = connection.execute(
                """
                UPDATE import_operations
                SET status = 'failed', message = ?
                WHERE operation_id = ? AND status = 'received'
                """,
                (message, str(operation_id)),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("No se pudo guardar el resultado de la importación")


def get_import_operation(
    operation_id: UUID, database_path: str | Path | None = None
) -> ImportOperationRead | None:
    with closing(_connect(database_path)) as connection:
        _initialize_schema(connection)
        row = connection.execute(
            """
            SELECT operation_id, status, version_id, message, created_at
            FROM import_operations
            WHERE operation_id = ?
            """,
            (str(operation_id),),
        ).fetchone()
        if row is None:
            return None
        return ImportOperationRead(
            operation_id=row["operation_id"],
            status=row["status"],
            version_id=row["version_id"],
            message=row["message"],
            created_at=row["created_at"],
        )
