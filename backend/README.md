# Backend

The backend exposes the currently published catalog at `GET /catalog` and
accepts complete snapshots at `POST /catalog/publish`.

Snapshots are stored in SQLite. Set `CATALOG_DATABASE_PATH` to choose the
database file; it defaults to `backend/catalog.db`.
Each publish writes a new catalog version and changes the published-version
reference in the same transaction. A failed write or activation rolls back,
leaving reads on the previous complete version.

The publisher accepts a validator through `create_app(store, validator)`.
The default validator checks that product data is JSON-serializable. The
product-field rules from story 6 should be supplied through this validator when
that story's implementation is available.

Run the API from this directory with `uv run fastapi dev src/backend/main.py`.
Run the publication tests with `uv run python -m unittest discover -s tests`.
