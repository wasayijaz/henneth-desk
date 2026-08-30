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

  function parsePath(pathname) {
    const match = String(pathname || "").match(PATH);
    if (!match) return null;
    return { ticker: match[1].toUpperCase(), caseId: match[2] };
  }

  function companyCaseRow(row) {
    const payload = row?.intelligence_cases;
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
      return {
        symbol: row?.symbol || null,
        status: "intelligence_cases_state_missing",
        case_count: 0,
        cases: [],
        rejection_reasons: ["intelligence_cases_state_missing"],
      };
    }
    return payload;
  }

  function findCase(row, caseId) {
    const payload = companyCaseRow(row);
    if (payload.status === "intelligence_cases_state_missing" && !(payload.cases || []).length) {
      return { ok: false, reason: "intelligence_cases_state_missing", payload, case: null };
    }
    const wanted = String(caseId || "");
    const found = (Array.isArray(payload.cases) ? payload.cases : []).find(item => item && item.case_id === wanted);
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
    const status = section.status || (section.items || section.text || section.dimensions || section.formulas ? "available" : "blocked");
    const reason = section.reason
      || (String(status).startsWith("blocked") ? (section.status || "not_yet_modelled") : null)
      || (status === "available" ? null : "not_yet_modelled");
    return {
      key,
      status,
      reason,
      text: section.text,
      epistemic_type: section.epistemic_type,
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
        ? { key, status: "available", reason: null, text, epistemic_type: caseObject.epistemic_type || "reported_fact" }
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
    SECTIONS,
    parsePath,
    companyCaseRow,
    findCase,
    caseHref,
    discoverableCases,
    resolveSection,
  };
})();
