/**
 * Gate 2 Step 10 - client for the semantic configuration API.
 *
 * Talks to backend/semantic/config_routes.py (prefix /semantic/config).
 *
 * Functions take `API` and `token` as arguments rather than reading them from
 * the environment, because SemanticLayer.jsx already receives both as props
 * and every existing call on that page uses them.
 */

const request = async (API, token, path, options = {}) => {
  const response = await fetch(`${API}/semantic/config${path}`, {
    ...options,
    headers: {
      Authorization: `Bearer ${token}`,
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(options.headers || {})
    }
  });

  let payload = null;

  try {
    payload = await response.json();
  } catch (e) {
    payload = null;
  }

  if (!response.ok) {
    // FastAPI puts the readable reason in `detail`. Surfacing it matters here:
    // the API returns specific guidance for configurations it refuses, such as
    // a DATE_COLUMN strategy with no date column named.
    const detail =
      (payload && (payload.detail || payload.message)) ||
      `Request failed with status ${response.status}`;

    const error = new Error(
      typeof detail === "string" ? detail : JSON.stringify(detail)
    );

    error.status = response.status;
    throw error;
  }

  return payload;
};

/* ------------------------------------------------------------------ */
/* Reference data                                                      */
/* ------------------------------------------------------------------ */

export const getConfigOptions = (API, token) =>
  request(API, token, "/options");

/* ------------------------------------------------------------------ */
/* Suggestions                                                         */
/* ------------------------------------------------------------------ */

/**
 * Start a profiling run. Returns as soon as the run is accepted, not when it
 * finishes - a full run takes minutes - so the caller polls
 * getGenerationStatus until it stops reporting RUNNING.
 */
export const generateSuggestions = (API, token, { tableNames, useModel } = {}) =>
  request(API, token, "/suggestions/generate", {
    method: "POST",
    body: JSON.stringify({
      table_names: tableNames && tableNames.length ? tableNames : null,
      use_model: useModel !== false
    })
  });

export const getGenerationStatus = (API, token) =>
  request(API, token, "/suggestions/generation");

export const getSuggestions = (API, token, tableName) => {
  const query = tableName
    ? `?table_name=${encodeURIComponent(tableName)}`
    : "";

  return request(API, token, `/suggestions${query}`);
};

export const confirmSuggestion = (API, token, suggestionId, editedProposal) =>
  request(API, token, `/suggestions/${suggestionId}/confirm`, {
    method: "POST",
    body: JSON.stringify({ edited_proposal: editedProposal || null })
  });

export const rejectSuggestion = (API, token, suggestionId, reason) =>
  request(API, token, `/suggestions/${suggestionId}/reject`, {
    method: "POST",
    body: JSON.stringify({ reason: reason || null })
  });

/* ------------------------------------------------------------------ */
/* Domains                                                             */
/* ------------------------------------------------------------------ */

export const getDomains = (API, token) =>
  request(API, token, "/domains");

export const createDomain = (API, token, payload) =>
  request(API, token, "/domains", {
    method: "POST",
    body: JSON.stringify(payload)
  });

export const updateDomain = (API, token, domainId, payload) =>
  request(API, token, `/domains/${domainId}`, {
    method: "PUT",
    body: JSON.stringify(payload)
  });

export const setDomainActive = (API, token, domainId, isActive) =>
  request(API, token, `/domains/${domainId}/active`, {
    method: "PATCH",
    body: JSON.stringify({ is_active: isActive })
  });

/* ------------------------------------------------------------------ */
/* Table configuration                                                 */
/* ------------------------------------------------------------------ */

export const getTableConfigs = (API, token) =>
  request(API, token, "/tables");

export const updateTableConfig = (API, token, tableName, payload) =>
  request(API, token, `/tables/${encodeURIComponent(tableName)}`, {
    method: "PUT",
    body: JSON.stringify(payload)
  });

/* ------------------------------------------------------------------ */
/* Snapshot mappings                                                   */
/* ------------------------------------------------------------------ */

export const getSnapshotMappings = (API, token, tableName) =>
  request(
    API,
    token,
    `/tables/${encodeURIComponent(tableName)}/snapshot-mappings`
  );

/**
 * Replace the whole mapping set for a table.
 *
 * The API takes the set as a unit rather than row by row, because the FULL and
 * TO_DATE rows for one period are only meaningful together. The response may
 * carry `warnings` describing a comparison that would mislead.
 */
export const saveSnapshotMappings = (API, token, tableName, mappings) =>
  request(
    API,
    token,
    `/tables/${encodeURIComponent(tableName)}/snapshot-mappings`,
    {
      method: "PUT",
      body: JSON.stringify({ mappings })
    }
  );

/* ------------------------------------------------------------------ */
/* Dimension and metric configuration                                  */
/* ------------------------------------------------------------------ */

/**
 * Role, exclusion and confirmation state for every configured column.
 *
 * Kept separate from /semantic/metrics and /semantic/dimensions so that the
 * existing endpoints are unchanged. The page merges the two by id.
 */
export const getColumnState = (API, token) =>
  request(API, token, "/columns");

export const updateDimensionConfig = (API, token, dimensionId, payload) =>
  request(API, token, `/dimensions/${dimensionId}`, {
    method: "PATCH",
    body: JSON.stringify(payload)
  });

export const updateMetricConfig = (API, token, metricId, payload) =>
  request(API, token, `/metrics/${metricId}`, {
    method: "PATCH",
    body: JSON.stringify(payload)
  });

/* ------------------------------------------------------------------ */
/* Manual definition creation                                          */
/*                                                                     */
/* These reuse the pre-Gate-2 create endpoints on /semantic/metrics    */
/* and /semantic/dimensions (not the /semantic/config prefix), so they */
/* cannot go through the `request` helper above. The active connection */
/* is resolved server-side, exactly as the edit and delete calls the   */
/* workbench already makes to these same endpoints.                    */
/* ------------------------------------------------------------------ */

const plainRequest = async (API, token, path, options = {}) => {
  const response = await fetch(`${API}${path}`, {
    ...options,
    headers: {
      Authorization: `Bearer ${token}`,
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(options.headers || {})
    }
  });

  let payload = null;
  try {
    payload = await response.json();
  } catch (e) {
    payload = null;
  }

  if (!response.ok) {
    const detail =
      (payload && (payload.detail || payload.message)) ||
      `Request failed with status ${response.status}`;
    const error = new Error(
      typeof detail === "string" ? detail : JSON.stringify(detail)
    );
    error.status = response.status;
    throw error;
  }

  return payload;
};

// POST /semantic/metrics — MetricRequest: metric_name, business_name,
// synonyms?, description?, table_name, column_name, aggregation_type, is_active.
export const createMetricDefinition = (API, token, payload) =>
  plainRequest(API, token, "/semantic/metrics", {
    method: "POST",
    body: JSON.stringify(payload)
  });

// POST /semantic/dimensions — DimensionRequest: dimension_name, business_name,
// synonyms?, description?, table_name, column_name, is_active. dimension_role
// is not part of this body; it is applied afterward via updateDimensionConfig.
export const createDimensionDefinition = (API, token, payload) =>
  plainRequest(API, token, "/semantic/dimensions", {
    method: "POST",
    body: JSON.stringify(payload)
  });
