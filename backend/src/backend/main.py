import os
import secrets
from typing import Any, Literal
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

app = FastAPI()
bearer_scheme = HTTPBearer(auto_error=False)


class ImportSnapshot(BaseModel):
    productos: list[dict[str, Any]]


class ImportAccepted(BaseModel):
    operation_id: UUID
    status: Literal["received"]


def verify_import_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> None:
    expected_token = os.getenv("IMPORT_API_TOKEN")
    if not expected_token:
        raise HTTPException(
            status_code=503,
            detail="Import authentication is not configured",
        )

    if credentials is None or not secrets.compare_digest(
        credentials.credentials, expected_token
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )


@app.get("/")
def read_root():
    return {"status": "ok"}


@app.post(
    "/imports",
    status_code=202,
    response_model=ImportAccepted,
    dependencies=[Depends(verify_import_token)],
)
def receive_import(snapshot: ImportSnapshot) -> ImportAccepted:
    return ImportAccepted(operation_id=uuid4(), status="received")
