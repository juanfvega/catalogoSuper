# Backend

## Importar un snapshot del catálogo

El endpoint privado `POST /imports` recibe un snapshot JSON completo y responde `202 Accepted` con un identificador de operación. En esta etapa solo acusa recibo; la validación, persistencia y publicación se implementan en historias posteriores.

El cuerpo debe tener una propiedad `productos` que contenga una lista de productos con los campos del contrato:

```json
{
  "productos": [
    {
      "codigo": "PROD-001",
      "nombre": "Alfajor de Dulce de Leche x6",
      "categoria": "Panadería y Pastelería",
      "precio": 6500.00,
      "stock": 24,
      "imagen": "prod-001.jpg",
      "vigente": true
    }
  ]
}
```

La validación de campos y reglas de negocio corresponde a la etapa posterior de validación.

Configura el token fuera del código y de la hoja, mediante la variable de entorno `IMPORT_API_TOKEN`. No lo registres ni lo incluyas en el repositorio. La solicitud debe usar HTTPS y el header `Authorization: Bearer <token>`.

- Token válido: devuelve `202` con `operation_id` y estado `received`.
- Token ausente o inválido: devuelve `401`.
- Token del servidor no configurado: devuelve `503`; el endpoint falla de forma cerrada.
