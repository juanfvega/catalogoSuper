# Backend del catálogo

API HTTP construida con FastAPI.

## Preparar el entorno

Desde este directorio (`backend/`), instala las dependencias con:

```bash
uv sync
```

## Iniciar el servidor

Ejecuta la aplicación con Uvicorn:

```bash
uv run uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

La API queda disponible en `http://localhost:8000`. El comando `uv run backend`
no inicia el servidor ASGI; actualmente ejecuta una función que solo imprime un
mensaje.

## Health check

La ruta `GET /` responde con HTTP `200` y:

```json
{"status": "ok"}
```

La respuesta indica que el servicio está disponible y no incluye valores de
configuración.

## Entorno de ejecución

`APP_ENV` puede usarse para identificar el entorno de ejecución, por ejemplo
`development`, `staging` o `production`. Actualmente la aplicación no lee esta
variable ni cambia su configuración según su valor; definirla por sí sola no
altera el comportamiento del servicio. No se debe incluir su valor ni otros
detalles de configuración en la respuesta del health check.
