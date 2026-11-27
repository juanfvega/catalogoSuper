# Importar Google Sheets con Apps Script

Este Apps Script envía manualmente la tabla completa de la hoja activa a
`POST /imports`. El servicio valida el snapshot y responde `202` cuando lo
recibe; ese acuse no confirma que el catálogo ya esté publicado.

## Preparar el proyecto

1. Crea un proyecto de Apps Script vinculado a la hoja o copia `Import.gs` en
   un proyecto existente.
2. La primera fila debe contener los encabezados exactos `codigo`, `nombre`,
   `categoria`, `precio`, `stock` y `vigente`. `imagen` es opcional; las
   imágenes informadas deben ser URLs HTTPS. Las columnas adicionales se
   ignoran.
3. Mantén los códigos como texto en Sheets para preservar guiones y ceros
   iniciales. `precio` debe ser numérico, `stock` un entero y `vigente` un
   valor booleano de Sheets.
4. En **Configuración del proyecto → Propiedades del script**, agrega:
   - `IMPORT_API_URL`: URL completa HTTPS del endpoint, terminada en `/imports`
     (por ejemplo, `https://api.example.com/imports`).
   - `IMPORT_API_TOKEN`: el mismo valor configurado como `IMPORT_API_TOKEN` en
     el servidor.
5. Guarda y recarga la hoja. Revisa **Compartir** en Google Drive y limita los
   permisos de edición de la hoja y del proyecto de Apps Script al dueño y a
   personas autorizadas. Los editores del proyecto pueden cambiar el código y
   acceder a propiedades usadas por el script; Script Properties no sustituyen
   la restricción de editores.

No escribas el token en celdas, archivos del repositorio, registros ni código
fuente. El endpoint debe ser accesible desde Apps Script por HTTPS.

## Ejecutar una importación

Después de terminar la edición y comprobar que el bloque de productos está
completo, selecciona **Importar catálogo → Enviar snapshot completo** en la
hoja. No se crea un disparador automático: cada ejecución es una decisión
manual del operador.

El script lee todos los valores de la hoja activa, ignora filas vacías al final
y detiene el envío si hay filas vacías entre productos para que los números de
fila de los errores coincidan con Sheets. Los valores se envían bajo `productos`
con los nombres del contrato. `imagen` vacío se envía como `null`; una URL
informada se conserva como referencia y no se descarga ni se sube el archivo.

Un HTTP `202` con `operation_id` y estado `received` se muestra como acuse de
recepción. Errores HTTP, configuración incompleta, encabezados inválidos y
respuestas inesperadas se reportan como errores de ejecución; el cuerpo de
error de validación del backend se incluye en el mensaje.

## Verificación manual

Prueba primero contra un entorno de staging:

1. Importa una fila de prueba válida con un `codigo` único y confirma el toast
   con `operation_id` y estado recibido.
2. Prueba una fila inválida (por ejemplo, `stock` negativo) y confirma que la
   ejecución muestra el error HTTP `422` con el detalle del backend.
3. Revisa los registros de ejecución y confirma que no contienen el token.

No uses una fila inválida en producción para esta prueba.
