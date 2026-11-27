const IMPORT_STATUS_POLL_INTERVAL_MS = 5000;
const IMPORT_STATUS_MAX_WAIT_MS = 240000;

function importCatalogSnapshot(productos) {
  if (!Array.isArray(productos)) {
    throw new Error("productos debe ser una lista");
  }

  const config = getImportNotificationConfig_();
  const endpoint = config.apiBaseUrl.replace(/\/+$/, "") + "/imports";
  let response;

  try {
    response = UrlFetchApp.fetch(endpoint, {
      method: "post",
      contentType: "application/json",
      headers: { Authorization: "Bearer " + config.apiToken },
      payload: JSON.stringify({ productos: productos }),
      muteHttpExceptions: true,
    });
  } catch (error) {
    return notifyImportResult_(
      config,
      "failed",
      "No se pudo enviar el snapshot a la API: " + error.message,
    );
  }

  const statusCode = response.getResponseCode();
  const body = parseResponseBody_(response);
  if (statusCode !== 202) {
    const status = statusCode === 422 ? "rejected" : "failed";
    return notifyImportResult_(
      config,
      status,
      formatApiError_(body, statusCode),
    );
  }

  if (!body || body.status !== "received" || !body.operation_id) {
    return notifyImportResult_(
      config,
      "failed",
      "La API no devolvió un acuse válido con el identificador de operación.",
    );
  }

  return waitForImportResult_(config, body.operation_id);
}

function waitForImportResult_(config, operationId) {
  const endpoint =
    config.apiBaseUrl.replace(/\/+$/, "") +
    "/imports/" +
    encodeURIComponent(operationId);
  const deadline = Date.now() + IMPORT_STATUS_MAX_WAIT_MS;

  while (Date.now() < deadline) {
    let response;
    try {
      response = UrlFetchApp.fetch(endpoint, {
        method: "get",
        headers: { Authorization: "Bearer " + config.apiToken },
        muteHttpExceptions: true,
      });
    } catch (error) {
      return notifyImportResult_(
        config,
        "failed",
        "No se pudo consultar el resultado final de la operación " +
          operationId +
          ": " +
          error.message,
        operationId,
      );
    }

    const statusCode = response.getResponseCode();
    const result = parseResponseBody_(response);
    if (statusCode !== 200 || !result || result.raw !== undefined) {
      return notifyImportResult_(
        config,
        "failed",
        "No se pudo consultar el resultado final de la operación. " +
          formatApiError_(result, statusCode),
        operationId,
      );
    }

    if (result.status === "published") {
      return notifyImportResult_(
        config,
        "published",
        "Catálogo publicado en la versión " + result.version_id + ".",
        operationId,
      );
    }
    if (result.status === "failed") {
      return notifyImportResult_(
        config,
        "failed",
        result.message || "La API informó un fallo sin detalle adicional.",
        operationId,
      );
    }
    if (result.status !== "received") {
      return notifyImportResult_(
        config,
        "failed",
        "La API devolvió un estado de operación no reconocido: " +
          result.status,
        operationId,
      );
    }

    Utilities.sleep(IMPORT_STATUS_POLL_INTERVAL_MS);
  }

  return notifyImportResult_(
    config,
    "pending",
    "La operación sigue en estado received y no se confirmó un resultado final " +
      "dentro del tiempo de espera. Consulte su estado antes de volver a enviar " +
      "el snapshot; el acuse inicial no confirma la publicación.",
    operationId,
  );
}

function getImportNotificationConfig_() {
  const properties = PropertiesService.getScriptProperties();
  const apiBaseUrl = properties.getProperty("IMPORT_API_BASE_URL");
  const apiToken = properties.getProperty("IMPORT_API_TOKEN");
  const recipient = properties.getProperty("RESPONSABLE_EMAIL");
  if (!apiBaseUrl || !apiToken || !recipient) {
    throw new Error(
      "Configure IMPORT_API_BASE_URL, IMPORT_API_TOKEN y RESPONSABLE_EMAIL " +
        "en las propiedades del script.",
    );
  }
  return { apiBaseUrl: apiBaseUrl, apiToken: apiToken, recipient: recipient };
}

function parseResponseBody_(response) {
  const content = response.getContentText();
  try {
    return JSON.parse(content);
  } catch (error) {
    return { raw: content, parse_error: error.message };
  }
}

function formatApiError_(body, statusCode) {
  if (body && body.detail && Array.isArray(body.detail.errors)) {
    return body.detail.errors
      .map(function (error) {
        return "Fila " + error.row + ", " + error.field + ": " + error.message;
      })
      .join("\n");
  }
  if (body && typeof body.detail === "string") {
    return body.detail;
  }
  const rawBody = body && body.raw;
  return rawBody
    ? "HTTP " + statusCode + ": " + rawBody
    : "La API respondió HTTP " + statusCode + " sin detalles.";
}

function notifyImportResult_(config, status, message, operationId) {
  const displayStatus = {
    published: "publicado",
    rejected: "rechazado",
    failed: "fallido",
    pending: "pendiente de confirmación",
  }[status] || status;
  const subject =
    status === "published"
      ? "Importación del catálogo publicada"
      : status === "rejected"
        ? "Importación del catálogo rechazada"
        : status === "pending"
          ? "Importación del catálogo pendiente de confirmación"
          : "Falló la importación del catálogo";
  const body = [
    "Estado: " + displayStatus,
    operationId ? "Operación: " + operationId : null,
    "Detalle: " + message,
  ]
    .filter(Boolean)
    .join("\n");

  MailApp.sendEmail({
    to: config.recipient,
    subject: subject,
    body: body,
  });
  return { status: status, operation_id: operationId || null, message: message };
}
