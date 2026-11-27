import os
import unittest
from uuid import UUID
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.main import app


class ImportEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_health_route_remains_available(self) -> None:
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_valid_token_returns_operation_id_without_exposing_token(self) -> None:
        token = "test-import-token"
        snapshot = {
            "productos": [
                {
                    "codigo": "PROD-001",
                    "nombre": "Alfajor",
                    "categoria": "Almacén",
                    "precio": 6500.00,
                    "stock": 24,
                    "imagen": "prod-001.jpg",
                    "vigente": True,
                }
            ]
        }

        with patch.dict(os.environ, {"IMPORT_API_TOKEN": token}):
            response = self.client.post(
                "/imports",
                headers={"Authorization": f"Bearer {token}"},
                json=snapshot,
            )

        self.assertEqual(response.status_code, 202)
        body = response.json()
        self.assertEqual(body["status"], "received")
        UUID(body["operation_id"])
        self.assertNotIn(token, response.text)

    def test_missing_or_invalid_token_is_rejected(self) -> None:
        with patch.dict(os.environ, {"IMPORT_API_TOKEN": "configured-token"}):
            missing_token_response = self.client.post(
                "/imports", json={"productos": []}
            )
            invalid_token_response = self.client.post(
                "/imports",
                headers={"Authorization": "Bearer wrong-token"},
                json={"productos": []},
            )

        self.assertEqual(missing_token_response.status_code, 401)
        self.assertEqual(invalid_token_response.status_code, 401)

    def test_missing_server_token_configuration_fails_closed(self) -> None:
        with patch.dict(os.environ, {"IMPORT_API_TOKEN": ""}):
            response = self.client.post(
                "/imports",
                headers={"Authorization": "Bearer any-token"},
                json={"productos": []},
            )

        self.assertEqual(response.status_code, 503)
