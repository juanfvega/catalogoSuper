function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu("Importar catálogo")
    .addItem("Enviar snapshot completo", "importCatalogSnapshot")
    .addToUi();
}

function importCatalogSnapshot() {
  var properties = PropertiesService.getScriptProperties();
  var endpoint = properties.getProperty("IMPORT_API_URL");
  var token = properties.getProperty("IMPORT_API_TOKEN");

  if (
    !endpoint ||
    !/^https:\/\/[^/\s?#]+(?:\/[^?#\s]*)?\/imports\/?$/.test(endpoint)
  ) {
    throw new Error(
      "Configura IMPORT_API_URL como una URL HTTPS terminada en /imports."
    );
  }
  if (!token || !token.trim()) {
    throw new Error("Configura IMPORT_API_TOKEN en las propiedades del script.");
  }

  var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  var snapshot = buildImportSnapshot_(sheet.getDataRange().getValues());
  var response = UrlFetchApp.fetch(endpoint, {
    method: "post",
    contentType: "application/json",
    headers: { Authorization: "Bearer " + token },
    payload: JSON.stringify({ productos: snapshot }),
    muteHttpExceptions: true,
  });
  var statusCode = response.getResponseCode();
  var responseText = response.getContentText();

  if (statusCode !== 202) {
    throw new Error(
      "La importación respondió HTTP " + statusCode + ": " + responseText
    );
  }

  var result;
  try {
    result = JSON.parse(responseText);
  } catch (error) {
    throw new Error("La API respondió HTTP 202 con un cuerpo JSON inválido.");
  }
  if (
    !result ||
    typeof result !== "object" ||
    !result.operation_id ||
    result.status !== "received"
  ) {
    throw new Error("La API respondió HTTP 202 con un acuse inválido.");
  }

  SpreadsheetApp.getActiveSpreadsheet().toast(
    "Snapshot recibido. Operación: " + result.operation_id +
      ". Esto no confirma la publicación.",
    "Importación de catálogo",
    10
  );
}

function buildImportSnapshot_(values) {
  if (!values || values.length === 0) {
    throw new Error("La hoja activa está vacía.");
  }

  var headers = values[0].map(function (value) {
    return String(value).trim();
  });
  var requiredHeaders = [
    "codigo",
    "nombre",
    "categoria",
    "precio",
    "stock",
    "vigente",
  ];
  var columnIndexes = {};

  headers.forEach(function (header, index) {
    if (header === "imagen" || requiredHeaders.indexOf(header) !== -1) {
      if (Object.prototype.hasOwnProperty.call(columnIndexes, header)) {
        throw new Error("La columna " + header + " aparece más de una vez.");
      }
      columnIndexes[header] = index;
    }
  });
  requiredHeaders.forEach(function (header) {
    if (!Object.prototype.hasOwnProperty.call(columnIndexes, header)) {
      throw new Error("Falta la columna obligatoria: " + header + ".");
    }
  });

  var lastPopulatedRow = values.length - 1;
  while (lastPopulatedRow > 0 && isBlankRow_(values[lastPopulatedRow])) {
    lastPopulatedRow--;
  }

  var products = [];
  var encounteredBlankRow = false;
  for (var rowIndex = 1; rowIndex <= lastPopulatedRow; rowIndex++) {
    var row = values[rowIndex];
    if (isBlankRow_(row)) {
      encounteredBlankRow = true;
      continue;
    }
    if (encounteredBlankRow) {
      throw new Error(
        "Hay una fila vacía antes de otros productos (fila " +
          (rowIndex + 1) +
          "). Elimínala o completa el bloque de productos antes de importar."
      );
    }

    var image = Object.prototype.hasOwnProperty.call(columnIndexes, "imagen")
      ? row[columnIndexes.imagen]
      : null;
    image = isBlankCell_(image) ? null : String(image).trim();
    if (image !== null && !/^https:\/\/\S+$/i.test(image)) {
      throw new Error(
        "La imagen de la fila " +
          (rowIndex + 1) +
          " debe ser una URL HTTPS o estar vacía."
      );
    }

    products.push({
      codigo: sheetText_(row[columnIndexes.codigo]),
      nombre: sheetText_(row[columnIndexes.nombre]),
      categoria: sheetText_(row[columnIndexes.categoria]),
      precio: row[columnIndexes.precio],
      stock: row[columnIndexes.stock],
      imagen: image,
      vigente: row[columnIndexes.vigente],
    });
  }

  return products;
}

function isBlankRow_(row) {
  return row.every(isBlankCell_);
}

function isBlankCell_(value) {
  return (
    value === null ||
    value === "" ||
    (typeof value === "string" && value.trim() === "")
  );
}

function sheetText_(value) {
  return value === null || typeof value === "undefined"
    ? ""
    : String(value).trim();
}
