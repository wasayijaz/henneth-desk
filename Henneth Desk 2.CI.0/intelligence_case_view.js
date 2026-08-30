(() => {
  const PATH = /^\/company\/([A-Za-z0-9]+)\/intelligence\/([A-Za-z0-9._-]+)\/?$/;
  const LIFECYCLE = Object.freeze(["Observed", "Corroborated", "Modelled", "Validated", "Published"]);
  const SECTIONS = Object.freeze([
    ["conclusion", "Conditional conclusion"],
    ["evidence", "Evidence"],
    ["hypotheses", "Competing hypotheses"],
    ["mechanism", "Mechanism and drivers"],
    ["analogues", "Analogue status"],
    ["financial_impact", "Quarterly financial impact"],
    ["scenarios", "Scenarios"],
    ["valuation", "Valuation"],
    ["expectations", "Price-implied expectations"],
    ["confidence", "Confidence dimensions"],
    ["watch_next", "Watch next"],
    ["sources", "Sources"],
    ["formulas", "Formulas"],
  ]);
  const SECTION_KEYS = new Set(SECTIONS.map(([key]) => key));
  const SECTION_STATUSES = new Set(["available", "blocked", "empty_state"]);
  const EPISTEMIC_TYPES = Object.freeze(["reported_fact", "derived_fact", "inference", "scenario", "forecast"]);

  function parsePath(pathname) {
    const match = String(pathname || "").match(PATH);
    if (!match) return null;
    return { ticker: match[1].toUpperCase(), caseId: match[2] };
  }

  function rejectedPayload(row, reason) {
    return {
      symbol: row?.symbol || null,
      status: reason,
      case_count: 0,
      cases: [],
      rejection_reasons: [reason],
    };
  }

  function validTicker(value) {
    return typeof value === "string" && /^[A-Z0-9]+$/.test(value);
  }

  function sectionHasContent(section) {
    return (typeof section.text === "string" && section.text.trim())
      || (Array.isArray(section.items) && section.items.length)
      || (Array.isArray(section.dimensions) && section.dimensions.length)
      || (Array.isArray(section.formulas) && section.formulas.length);
  }

  function validateSection(section) {
    if (!section || typeof section !== "object" || Array.isArray(section)) return "section_shape_invalid";
    if (section.status !== undefined && (!SECTION_STATUSES.has(section.status) || typeof section.status !== "string")) {
      return "section_status_invalid";
    }
    return null;
  }

  function validateCase(caseObject, symbol, seenIds) {
    if (!caseObject || typeof caseObject !== "object" || Array.isArray(caseObject)) return "case_shape_invalid";
    if (caseObject.symbol !== symbol) return "case_symbol_mismatch";
    if (typeof caseObject.case_id !== "string" || !caseObject.case_id) return "case_id_invalid";
    if (seenIds.has(caseObject.case_id)) return "duplicate_case_id";
    seenIds.add(caseObject.case_id);
    if (!LIFECYCLE.includes(caseObject.status)) return "case_lifecycle_invalid";
    if (!EPISTEMIC_TYPES.includes(caseObject.epistemic_type)) return "case_epistemic_type_invalid";
    if (caseObject.sections !== undefined) {
      if (!caseObject.sections || typeof caseObject.sections !== "object" || Array.isArray(caseObject.sections)) return "sections_shape_invalid";
      for (const [key, section] of Object.entries(caseObject.sections)) {
        if (!SECTION_KEYS.has(key)) return "section_key_invalid";
        const reason = validateSection(section);
        if (reason) return reason;
        if (section.status === "available" && !sectionHasContent(section)) return "section_content_invalid";
      }
    }
    return null;
  }

  function validateCompanyRow(row, requestedTicker) {
    const ticker = String(requestedTicker || "").toUpperCase();
    const rowSymbol = row?.symbol;
    if (!validTicker(ticker) || typeof rowSymbol !== "string" || rowSymbol !== ticker) {
      return { payload: rejectedPayload(row, "ticker_identity_mismatch"), reason: "ticker_identity_mismatch" };
    }
    const payload = row?.intelligence_cases;
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
      return { payload: rejectedPayload(row, "intelligence_cases_state_missing"), reason: "intelligence_cases_state_missing" };
    }
    if (payload.symbol !== ticker) return { payload: rejectedPayload(row, "payload_symbol_mismatch"), reason: "payload_symbol_mismatch" };
    if (!Array.isArray(payload.cases)) return { payload: rejectedPayload(row, "cases_shape_invalid"), reason: "cases_shape_invalid" };
    const seenIds = new Set();
    for (const caseObject of payload.cases) {
      const reason = validateCase(caseObject, ticker, seenIds);
      if (reason) return { payload: rejectedPayload(row, reason), reason };
    }
    return { payload, reason: null };
  }

  function companyCaseRow(row, requestedTicker) {
    const ticker = requestedTicker === undefined ? row?.symbol : requestedTicker;
    return validateCompanyRow(row, ticker).payload;
  }

  function findCase(row, caseId, requestedTicker) {
    const ticker = requestedTicker === undefined ? row?.symbol : requestedTicker;
    const validated = validateCompanyRow(row, ticker);
    const payload = validated.payload;
    if (validated.reason) return { ok: false, reason: validated.reason, payload, case: null };
    const wanted = String(caseId || "");
    const found = payload.cases.find(item => item.case_id === wanted);
    if (!found) return { ok: false, reason: "case_not_found", payload, case: null };
    return { ok: true, reason: null, payload, case: found };
  }

  function caseHref(symbol, caseId) {
    const ticker = String(symbol || "").trim().toUpperCase();
    const id = String(caseId || "").trim();
    if (!/^[A-Z0-9]+$/.test(ticker) || !/^[A-Za-z0-9._-]+$/.test(id)) return "";
    return "/company/" + ticker + "/intelligence/" + id;
  }

  function discoverableCases(row) {
    if (!row || !Object.prototype.hasOwnProperty.call(row, "intelligence_cases")) {
      return { status: "absent", reason: null, items: [] };
    }
    const payload = row.intelligence_cases;
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
      return { status: "invalid", reason: "intelligence_cases_shape_invalid", items: [] };
    }
    if (!Array.isArray(payload.cases)) {
      return { status: "invalid", reason: "intelligence_cases_cases_invalid", items: [] };
    }
    const items = [];
    for (const item of payload.cases) {
      if (!item || typeof item !== "object" || Array.isArray(item)) {
        return { status: "invalid", reason: "intelligence_case_item_invalid", items: [] };
      }
      const caseId = String(item.case_id || "").trim();
      const symbol = String(item.symbol || row.symbol || "").trim().toUpperCase();
      const href = caseHref(symbol, caseId);
      if (!href) return { status: "invalid", reason: "intelligence_case_identity_invalid", items: [] };
      items.push({ case_id: caseId, symbol, href, title: String(item.case_type || item.case_id || "Intelligence case").replaceAll("_", " "), summary: String(item.summary || "").trim(), status: String(item.status || payload.status || "unknown") });
    }
    return { status: items.length ? "available" : "empty", reason: null, items };
  }
  function blocked(key, reason) {
    const text = String(reason || "").trim();
    return { key, status: "blocked", reason: text || "not_yet_modelled" };
  }

  function explicitSection(caseObject, key) {
    const section = caseObject?.sections?.[key];
    if (!section || typeof section !== "object" || Array.isArray(section)) return null;
    const hasContent = Boolean(sectionHasContent(section));
    const status = section.status === "available" && !hasContent
      ? "empty_state"
      : section.status || (hasContent ? "available" : "empty_state");
    const reason = section.reason
      || (String(status).startsWith("blocked") ? (section.status || "not_yet_modelled") : null)
      || (status === "empty_state" ? "section_content_missing" : null)
      || (status === "available" ? null : "not_yet_modelled");
    return {
      key,
      status,
      reason,
      text: section.text,
      epistemic_type: EPISTEMIC_TYPES.includes(section.epistemic_type) ? section.epistemic_type : caseObject?.epistemic_type,
      items: section.items,
      dimensions: section.dimensions,
      formulas: section.formulas,
    };
  }

  function resolveSection(caseObject, key) {
    const explicit = explicitSection(caseObject, key);
    if (explicit) return explicit;
    const policy = caseObject?.policy || {};
    const blocks = caseObject?.promotion_blocks || {};
    if (key === "conclusion") {
      const text = String(caseObject?.summary || "").trim();
      return text
        ? { key, status: "available", reason: null, text, epistemic_type: EPISTEMIC_TYPES.includes(caseObject.epistemic_type) ? caseObject.epistemic_type : null }
        : blocked(key, "not_yet_modelled");
    }
    if (key === "evidence") {
      const items = Array.isArray(caseObject?.observed_facts) ? caseObject.observed_facts : [];
      return items.length ? { key, status: "available", reason: null, items } : blocked(key, "not_yet_modelled");
    }
    if (key === "hypotheses") {
      const items = Array.isArray(caseObject?.alternative_readings) ? caseObject.alternative_readings : [];
      return items.length ? { key, status: "available", reason: null, items } : blocked(key, "not_yet_modelled");
    }
    if (key === "sources") {
      const items = Array.isArray(caseObject?.source_lineage) ? caseObject.source_lineage : [];
      return items.length ? { key, status: "available", reason: null, items } : blocked(key, "not_yet_modelled");
    }
    if (key === "mechanism" || key === "financial_impact") {
      return blocked(key, blocks.Modelled || "not_yet_modelled");
    }
    if (key === "analogues" || key === "scenarios" || key === "watch_next" || key === "confidence") {
      return blocked(key, "not_yet_modelled");
    }
    if (key === "valuation") {
      return blocked(key, policy.no_valuation ? (blocks.Published || "not_yet_modelled") : "not_yet_modelled");
    }
    if (key === "expectations") {
      return blocked(key, policy.no_market_expectations ? (blocks.Published || "not_yet_modelled") : "not_yet_modelled");
    }
    if (key === "formulas") return blocked(key, "formula_id_not_emitted");
    return blocked(key, "not_yet_modelled");
  }

  window.HennethIntelligenceCaseView = {
    PATH,
    LIFECYCLE,
    EPISTEMIC_TYPES,
    SECTIONS,
    parsePath,
    companyCaseRow,
    findCase,
    caseHref,
    discoverableCases,
    resolveSection,
  };
})();
