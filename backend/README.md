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

## Persistencia del catálogo

El backend guarda los catálogos en SQLite. Por defecto, la base de datos se crea
en `backend/data/catalog.db`. Para usar un volumen persistente en otro
directorio, define `CATALOG_DATABASE_PATH` con la ruta del archivo antes de
iniciar el servicio:

```bash
CATALOG_DATABASE_PATH=/var/lib/catalogo/catalog.db uv run uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

`POST /catalog/versions` recibe la lista completa de productos, crea una nueva
versión incremental y la publica en una transacción. Las versiones anteriores
se conservan como instantáneas completas. Cada producto requiere `codigo`
(SKU de 3–20 caracteres A-Z, 0-9 o `-`), `nombre` (3–100 caracteres),
`categoria` (3–50 caracteres), `precio` mayor que cero, `stock` entero no
negativo y `vigente` booleano. `imagen` es opcional; si se informa, debe ser un
nombre de archivo permitido en minúsculas o una URL HTTPS válida. Una imagen
vacía se almacena como omitida; no se asigna un recurso predeterminado hasta que
se defina.

Ejemplo:

```bash
curl -X POST http://localhost:8000/catalog/versions \
  -H 'Content-Type: application/json' \
  -d '{
    "products": [{
      "codigo": "PROD-001",
      "nombre": "Alfajor de Dulce de Leche x6",
      "categoria": "Panadería y Pastelería",
      "precio": 6500.00,
      "stock": 24,
      "imagen": "prod-001.jpg",
      "vigente": true
    }]
  }'
```

La respuesta HTTP `201` contiene el identificador incremental, la fecha de
creación y la instantánea publicada. Los cuerpos inválidos (incluidos SKU
duplicados dentro de la misma versión) responden con HTTP `422`.

## Lectura pública del catálogo

`GET /catalog` no requiere autenticación y devuelve la versión actualmente
publicada con todos sus productos y los campos del contrato (`codigo`, `nombre`,
`categoria`, `precio`, `stock`, `imagen` y `vigente`). El valor de `imagen` se
devuelve tal como fue almacenado: puede ser un nombre de archivo o una URL
HTTPS. Si todavía no hay una versión publicada, la ruta responde HTTP `404`.
FastAPI publica el contrato de respuesta en OpenAPI.

Ejemplo:

```bash
curl http://localhost:8000/catalog
```

Respuesta:

```json
{
  "version_id": 1,
  "created_at": "2026-11-27T18:29:00.000Z",
  "products": [
    {
      "codigo": "PROD-001",
      "nombre": "Alfajor de Dulce de Leche x6",
      "categoria": "Panadería y Pastelería",
      "precio": "6500.0",
      "stock": 24,
      "imagen": "prod-001.jpg",
      "vigente": true
    }
  ]
}
## Imágenes de productos

La integración puede guardar una imagen con `POST /products/{codigo}/image`,
usando `multipart/form-data` con el campo `image` y el mismo bearer token
configurado en `IMPORT_API_TOKEN`. Se aceptan JPEG, PNG y WebP de hasta 10 MiB.
El nombre enviado por el cliente no se utiliza como ruta. La respuesta incluye
una referencia estable como `/images/PROD-001`; `GET /images/{codigo}` sirve
esa imagen públicamente, sin autenticación. Cuando el catálogo publica el
producto con ese código, su campo `imagen` usa esta referencia estable en lugar
de un enlace externo.

Por defecto, los archivos se guardan en `backend/data/product-images`. Para
usar un volumen persistente, define `PRODUCT_IMAGE_STORAGE_PATH` con el
directorio correspondiente:

```bash
PRODUCT_IMAGE_STORAGE_PATH=/var/lib/catalogo/product-images uv run uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Ejemplo de carga:

```bash
curl -X POST http://localhost:8000/products/PROD-001/image \
  -H 'Authorization: Bearer <IMPORT_API_TOKEN>' \
  -F 'image=@producto.png'
```

## Importación de snapshots

`POST /imports` recibe un snapshot completo en `productos` y requiere un token
Bearer configurado mediante `IMPORT_API_TOKEN`. Los productos se validan contra
el mismo contrato antes de aceptar la operación. Si hay errores, responde con
HTTP `422` y un `detail.errors` con `row`, `field` y `message`; los números de
fila corresponden a Google Sheets, suponiendo encabezados en la fila 1 y el
primer producto en la fila 2. Los códigos duplicados se informan en todas las
filas involucradas. Un snapshot inválido no recibe un identificador de
operación ni inicia publicación.

Un snapshot válido responde HTTP `202` con un `operation_id` y estado
`received`. Este acuse confirma la recepción; no significa que el catálogo ya
esté publicado.

Ejemplo de llamada:

```bash
curl -X POST http://localhost:8000/imports \
  -H 'Authorization: Bearer <IMPORT_API_TOKEN>' \
  -H 'Content-Type: application/json' \
  -d '{
    "productos": [{
      "codigo": "PROD-001",
      "nombre": "Alfajor de Dulce de Leche x6",
      "categoria": "Panadería y Pastelería",
      "precio": 6500.00,
      "stock": 24,
      "imagen": "prod-001.jpg",
      "vigente": true
    }]
  }'
```

Configura `IMPORT_API_TOKEN` en el entorno del servidor. No lo incluyas en la
hoja ni en el código fuente.

### Consultar el resultado final

El `202 received` inicial confirma únicamente la recepción del snapshot. La API
lo publica y conserva un resultado consultable mediante
`GET /imports/{operation_id}`, usando el mismo bearer token:

```bash
curl http://localhost:8000/imports/<operation_id> \
  -H 'Authorization: Bearer <IMPORT_API_TOKEN>'
```

El estado será `received`, `published` o `failed`. La respuesta incluye
`version_id` cuando se publicó; en caso de fallo incluye un `message` accionable.
Las solicitudes rechazadas antes de aceptar la operación responden HTTP `422`
con los errores por fila y no tienen un `operation_id`.

### Notificaciones desde Apps Script

El archivo [`../apps-script/import-notification.gs`](../apps-script/import-notification.gs)
se puede copiar al proyecto Apps Script que envía los snapshots. Define estas
propiedades en **Configuración del proyecto > Propiedades del script**:

| Propiedad | Valor |
| --- | --- |
| `IMPORT_API_BASE_URL` | URL base del backend, por ejemplo `https://api.example.com` |
| `IMPORT_API_TOKEN` | El mismo bearer token configurado en el backend |
| `RESPONSABLE_EMAIL` | Dirección de correo que recibirá los resultados |

La función `importCatalogSnapshot(productos)` envía el snapshot, consulta el
resultado por `operation_id` hasta recibir un estado final y usa
`MailApp.sendEmail()` para notificar publicación, rechazo o fallo. Si vence el
tiempo de espera, notifica que el resultado sigue pendiente y no lo presenta
como una publicación exitosa. Autoriza los permisos de Apps Script para
solicitudes externas y envío de correo al ejecutar la función por primera vez.

## Entorno de ejecución

`APP_ENV` puede usarse para identificar el entorno de ejecución, por ejemplo
`development`, `staging` o `production`. Actualmente la aplicación no lee esta
variable ni cambia su configuración según su valor; definirla por sí sola no
altera el comportamiento del servicio. No se debe incluir su valor ni otros
detalles de configuración en la respuesta del health check.
