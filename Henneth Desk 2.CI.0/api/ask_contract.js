const encoder = new TextEncoder();

export const PILOT_SYMBOLS = Object.freeze([
  "ATRL",
  "BOP",
  "CNERGY",
  "DGKC",
  "ENGROH",
  "FFC",
  "GAL",
  "HBL",
  "HUBC",
  "LUCK",
  "MARI",
  "MEBL",
  "MLCF",
  "NBP",
  "NRL",
  "OGDC",
  "PPL",
  "PRL",
  "PSO",
  "UBL",
]);

const PILOT_SET = new Set(PILOT_SYMBOLS);
const REQUEST_LIMIT = 16 * 1024;
const CONTEXT_LIMIT = 24 * 1024;
const MAX_EXCERPT = 360;
const MAX_TEXT = 600;
const STANDARD_HTTPS_PORTS = new Set(["", "443"]);
const SAFE_MODEL_KEYS = new Set([
  "conclusion",
  "mechanism",
  "what_to_watch",
  "evidence_ids",
  "citation_ids",
]);
const DOWNSTREAM_KEYS = [
  "forecast",
  "valuation",
  "market_expectations",
  "scenario_lab",
];
const BLOCKED_DOWNSTREAM = Object.freeze({
  forecast: "blocked_not_implemented",
  valuation: "blocked_not_implemented",
  market_expectations: "blocked_not_implemented",
  scenario_lab: "blocked_not_implemented",
});
const CASE_MECHANISM_LABEL = "Available reported-fact mechanism.";
const CASE_MECHANISM_BOUNDARY =
  "Reported operating linkage only; no reported numeric case values, no standalone transaction outcome, no formal engine activation, and no advice.";
const UNSAFE_MODEL_TEXT =
  /(?:https?:\/\/|www\.|\b(?:buy|purchase|sell|dispose|accumulate|trim|reduce|overweight|underweight|outperform|underperform|take\s+profit|stop\s+loss|entry|enter|exit|hold|short|long|leverage|should|must|recommend|guarantee|promise|definite|definitely|certain|certainty|causal|causes|caused|will\s+(?:lead|cause|increase|decrease|rise|fall|improve|hurt)|profit|return|upside|downside|target price|fair value|prompt|developer|system|instruction|ignore previous|january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec|pkr|rs\.?|rupees?|\$|percent|percentage|zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|million|billion|trillion)\b)/i;
const DIGIT_OR_FULLWIDTH = /[\d\uFF10-\uFF19\u0660-\u0669\u06F0-\u06F9]/u;
const CASE_FORBIDDEN_TEXT = /\b(?:forecast|valuation|market_expectations|price_target|recommendation|reported_values)\b/i;

export function byteLength(value) {
  const text = typeof value === "string" ? value : JSON.stringify(value);
  return encoder.encode(text ?? "").length;
}

function isPlainObject(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  return Object.getPrototypeOf(value) === Object.prototype;
}

function ownEntries(value) {
  return isPlainObject(value) ? Object.entries(value) : [];
}

function boundedString(value, limit = MAX_TEXT) {
  if (typeof value !== "string") return null;
  const compact = value.replace(/\s+/g, " ").trim();
  if (!compact) return null;
  return compact.length > limit ? `${compact.slice(0, limit - 1)}…` : compact;
}

function boundedScalar(value) {
  if (
    value === null ||
    typeof value === "string" ||
    (typeof value === "number" && Number.isFinite(value)) ||
    typeof value === "boolean"
  ) {
    return value;
  }
  return null;
}

function boundedObject(value, allowedKeys, maxArray = 8) {
  if (!isPlainObject(value)) return {};
  const out = {};
  for (const key of allowedKeys) {
    const item = value[key];
    if (Array.isArray(item)) {
      out[key] = item.slice(0, maxArray).map(boundedScalar);
    } else if (isPlainObject(item)) {
      out[key] = boundedObject(item, Object.keys(item).slice(0, maxArray), maxArray);
    } else {
      out[key] = boundedScalar(item);
    }
  }
  return out;
}

function stableHash(parts) {
  let hash = 0x811c9dc5;
  const text = parts.map((part) => String(part ?? "")).join("\u001f");
  for (let i = 0; i < text.length; i += 1) {
    hash ^= text.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return hash.toString(16).padStart(8, "0");
}

function stableId(prefix, ...parts) {
  return `${prefix}_${stableHash(parts)}`;
}

function isPrivateIpv4(hostname) {
  const match = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/.exec(hostname);
  if (!match) return false;
  const octets = match.slice(1).map(Number);
  if (octets.some((n) => n < 0 || n > 255)) return true;
  const [a, b] = octets;
  return (
    a === 0 ||
    a === 10 ||
    a === 127 ||
    a === 169 && b === 254 ||
    a === 172 && b >= 16 && b <= 31 ||
    a === 192 && b === 168
  );
}

function looksEncodedPrivateIp(hostname) {
  const compact = hostname.toLowerCase();
  if (/^(?:0x|0)[0-9a-f.]+$/i.test(compact)) return true;
  if (/^\d+$/.test(compact)) return true;
  return /%[0-9a-f]{2}/i.test(compact);
}

export function isSafeHttpsUrl(value) {
  if (typeof value !== "string" || value.length > 2048) return false;
  let parsed;
  try {
    parsed = new URL(value);
  } catch {
    return false;
  }
  if (parsed.protocol !== "https:") return false;
  if (parsed.username || parsed.password) return false;
  if (!STANDARD_HTTPS_PORTS.has(parsed.port)) return false;
  const hostname = parsed.hostname.toLowerCase();
  if (
    !hostname ||
    hostname === "localhost" ||
    hostname.endsWith(".localhost") ||
    hostname === "::1" ||
    hostname.startsWith("[") ||
    isPrivateIpv4(hostname) ||
    looksEncodedPrivateIp(hostname)
  ) {
    return false;
  }
  return true;
}

function addCitation(registry, symbol, evidence, ownerType, ownerId) {
  if (!isPlainObject(evidence) || !isSafeHttpsUrl(evidence.source_url)) return null;
  const documentId = boundedString(evidence.document_id || evidence.doc_id, 80);
  const contentHash = boundedString(evidence.content_sha256, 96);
  const evidenceHash = boundedString(evidence.evidence_sha256 || evidence.hash, 96);
  const page = Number.isInteger(evidence.page) && evidence.page > 0 ? evidence.page : null;
  const sourceQualityLevel = Number.isInteger(evidence.source_quality_level)
    ? evidence.source_quality_level
    : null;
  const citation_id = stableId(
    "cit",
    symbol,
    ownerType,
    ownerId,
    documentId,
    contentHash,
    evidenceHash,
    evidence.source_url,
    page,
  );
  if (!registry.byId.has(citation_id)) {
    registry.byId.set(citation_id, {
      citation_id,
      owner_symbol: symbol,
      owner_type: ownerType,
      owner_id: boundedString(ownerId, 120),
      source_url: evidence.source_url,
      document_id: documentId,
      content_sha256: contentHash,
      evidence_sha256: evidenceHash,
      source: boundedString(evidence.source, 80),
      source_quality_level: sourceQualityLevel,
      page,
      label: [documentId, page ? `p${page}` : null].filter(Boolean).join(" · "),
    });
  }
  return citation_id;
}

function evidenceProjection(registry, symbol, evidence, ownerType, ownerId) {
  const citation_id = addCitation(registry, symbol, evidence, ownerType, ownerId);
  return {
    citation_id,
    document_id: boundedString(evidence?.document_id || evidence?.doc_id, 80),
    content_sha256: boundedString(evidence?.content_sha256, 96),
    evidence_sha256: boundedString(evidence?.evidence_sha256 || evidence?.hash, 96),
    source_quality_level: Number.isInteger(evidence?.source_quality_level)
      ? evidence.source_quality_level
      : null,
    page: Number.isInteger(evidence?.page) && evidence.page > 0 ? evidence.page : null,
    excerpt: boundedString(evidence?.text, MAX_EXCERPT),
  };
}

function requestQuestionSafe(question) {
  if (DIGIT_OR_FULLWIDTH.test(question)) throw new Error("question_contains_numeric_token");
  if (UNSAFE_MODEL_TEXT.test(question)) throw new Error("question_contains_unsafe_language");
}

export function validateRequest(input = {}, allowedSymbols = PILOT_SET) {
  if (!isPlainObject(input)) throw new Error("invalid_request");
  if (byteLength(input) > REQUEST_LIMIT) throw new Error("request_too_large");
  const allowed = allowedSymbols instanceof Set ? allowedSymbols : new Set(allowedSymbols || []);
  const keys = Object.keys(input);
  for (const key of keys) {
    if (!["symbol", "question"].includes(key)) throw new Error("extra_request_key");
  }
  const { symbol, question } = input;
  if (typeof symbol !== "string" || !/^[A-Z][A-Z0-9.]{1,9}$/.test(symbol)) {
    throw new Error("invalid_symbol");
  }
  if (!allowed.has(symbol)) throw new Error("symbol_not_allowed");
  if (typeof question !== "string" || !question.trim()) throw new Error("invalid_question");
  if (byteLength(question) > 4096) throw new Error("question_too_large");
  requestQuestionSafe(question);
  return { symbol, question: question.trim() };
}

function projectBrief(row, registry, symbol) {
  const briefRoot = isPlainObject(row.brief) ? row.brief : {};
  const brief = isPlainObject(briefRoot.current) ? briefRoot.current : briefRoot;
  const sections = [];
  for (const [sectionKey, sectionValue] of ownEntries(brief.sections)) {
    if (sections.length >= 6) break;
    const claims = Array.isArray(sectionValue)
      ? sectionValue
      : isPlainObject(sectionValue)
        ? (Array.isArray(sectionValue.cited_claims)
            ? sectionValue.cited_claims
            : Array.isArray(sectionValue.claims)
              ? sectionValue.claims
              : [])
        : [];
    const citedClaims = Array.isArray(sectionValue.cited_claims)
      ? sectionValue.cited_claims
      : Array.isArray(sectionValue.claims)
        ? sectionValue.claims
        : claims;
    sections.push({
      section_id: boundedString(sectionKey, 80),
      title: boundedString(sectionValue.title || sectionKey, 120),
      status: boundedString(sectionValue.status || "approved", 80),
      summary: boundedString(sectionValue.summary || sectionValue.text, 360),
      cited_claims: citedClaims.slice(0, 2).map((claim, index) => {
        const evidence = Array.isArray(claim?.evidence) ? claim.evidence[0] : isPlainObject(claim?.evidence) ? claim.evidence : claim;
        const claimId = boundedString(claim?.claim_id, 120) || `${sectionKey}:${index}`;
        return {
          claim_id: claimId,
          text: boundedString(claim?.text || claim?.claim || claim?.summary, MAX_EXCERPT),
          citation_id: evidenceProjection(registry, symbol, evidence, "brief_claim", claimId).citation_id,
        };
      }),
    });
  }
  return {
    status: boundedString(brief.status || "approved_current", 80),
    generated_at: boundedString(brief.generated_at || brief.as_of, 80),
    sections,
  };
}

function projectSignals(row, registry, symbol) {
  const source = isPlainObject(row.signal_clusters) ? row.signal_clusters : {};
  const clusters = Array.isArray(source.clusters) ? source.clusters : [];
  const linkedEventIds = new Set();
  return {
    linkedEventIds,
    signals: {
      coverage_status: boundedString(source.coverage_status || "no_clusterable_signal", 80),
      candidate_count: Number.isInteger(source.candidate_count) ? source.candidate_count : 0,
      eligible_count: Number.isInteger(source.eligible_count) ? source.eligible_count : 0,
      clusterable_count: Number.isInteger(source.clusterable_count) ? source.clusterable_count : 0,
      freshness: boundedString(source.freshness || "unknown", 80),
      rejection_reasons: boundedObject(source.rejection_reasons, Object.keys(source.rejection_reasons || {}).slice(0, 8)),
      clusters: clusters.slice(0, 5).map((cluster) => {
        const observations = Array.isArray(cluster?.observations) ? cluster.observations : [];
        for (const obs of observations) {
          if (typeof obs?.event_id === "string") linkedEventIds.add(obs.event_id);
        }
        return {
          cluster_id: boundedString(cluster?.cluster_id, 120),
          assessment: boundedString(cluster?.assessment, 80),
          confidence_band: boundedString(cluster?.confidence?.band, 80),
          proposition: boundedObject(cluster?.proposition, [
            "type",
            "stage",
            "target",
            "person",
            "role",
            "modality",
          ]),
          assertion_key: boundedString(cluster?.assertion_key, 180),
          conflict_key: boundedString(cluster?.conflict_key, 180),
          observations: observations.slice(0, 2).map((obs) => ({
            observation_id: boundedString(obs?.observation_id, 120),
            event_id: boundedString(obs?.event_id, 120),
            effective_date: boundedString(obs?.effective_date, 40),
            detected_at: boundedString(obs?.detected_at, 60),
            originator: boundedString(obs?.originator, 80),
            distributor: boundedString(obs?.distributor, 80),
            evidence: evidenceProjection(
              registry,
              symbol,
              obs?.evidence,
              "signal_observation",
              obs?.observation_id || obs?.event_id || cluster?.cluster_id,
            ),
          })),
        };
      }),
    },
  };
}

function projectEvents(row, registry, symbol, linkedEventIds) {
  const events = Array.isArray(row.operating_events) ? row.operating_events : [];
  return events
    .filter((event) => linkedEventIds.has(event?.event_id))
    .slice(0, 6)
    .map((event) => ({
      event_id: boundedString(event.event_id, 120),
      event_type: boundedString(event.event_type, 80),
      intelligence_type: boundedString(event.intelligence_type || "reported_fact", 80),
      effective_date: boundedString(event.effective_date, 40),
      detected_at: boundedString(event.detected_at, 60),
      description: boundedString(event.description, MAX_TEXT),
      priority_weight: boundedScalar(event.priority_weight),
      affected_drivers: Array.isArray(event.affected_drivers)
        ? event.affected_drivers.slice(0, 8).map((driver) => boundedString(driver, 120)).filter(Boolean)
        : [],
      evidence: (Array.isArray(event.evidence) ? event.evidence : [])
        .slice(0, 2)
        .map((evidence) =>
          evidenceProjection(registry, symbol, evidence, "operating_event", event.event_id),
        ),
    }));
}

function projectStudies(row, linkedEventIds) {
  const studies = Array.isArray(row.event_studies) ? row.event_studies : [];
  return studies
    .filter((study) => !study?.event_id || linkedEventIds.has(study.event_id))
    .slice(0, 1)
    .map((study) => ({
      study_id: boundedString(study.study_id, 120),
      event_id: boundedString(study.event_id, 120),
      baseline: boundedObject(study.baseline, [
        "selected_date",
        "selected_close",
        "baseline_date",
        "event_date",
        "price_source",
        "index_source",
        "status",
      ]),
      horizons: Array.isArray(study.horizons)
        ? study.horizons.slice(0, 8).map((horizon) =>
            boundedObject(horizon, [
              "label",
              "horizon",
              "target_date",
              "selected_stock_date",
              "selected_date",
              "selected_close",
              "selected_index_date",
              "stock_simple_return",
              "return_pct",
              "kse100_simple_return",
              "kse100_relative_return",
              "kse100_relative",
              "status",
              "reason",
            ]),
          )
        : ownEntries(study.horizons)
            .slice(0, 8)
            .map(([label, horizon]) => ({
              label,
              ...boundedObject(horizon, [
                "target_date",
                "selected_stock_date",
                "selected_date",
                "selected_close",
                "selected_index_date",
                "stock_simple_return",
                "return_pct",
                "kse100_simple_return",
                "kse100_relative_return",
                "kse100_relative",
                "status",
                "reason",
              ]),
            })),
      kse100_relative: boundedObject(study.kse100_relative, Object.keys(study.kse100_relative || {}).slice(0, 8)),
      analogue_aggregate: boundedObject(study.analogue_aggregate, Object.keys(study.analogue_aggregate || {}).slice(0, 8)),
      data_cutoff: boundedString(study.data_cutoff, 80),
      limitations: Array.isArray(study.limitations)
        ? study.limitations.slice(0, 8).map((item) => boundedString(item, 180)).filter(Boolean)
        : [],
      suppression: boundedObject(study.suppression, Object.keys(study.suppression || {}).slice(0, 8)),
    }));
}

function projectScenarios(row, linkedEventIds) {
  const scenarios = Array.isArray(row.impact_scenarios) ? row.impact_scenarios : [];
  const perEvent = new Map();
  const selected = [];
  for (const scenario of scenarios) {
    if (scenario?.event_id && linkedEventIds.size && !linkedEventIds.has(scenario.event_id)) continue;
    const count = perEvent.get(scenario?.event_id || "") || 0;
    if (count >= 3 || selected.length >= 6) continue;
    perEvent.set(scenario?.event_id || "", count + 1);
    selected.push({
      event_id: boundedString(scenario.event_id, 120),
      scenario_type: boundedString(scenario.scenario_type || scenario.type || "scenario", 80),
      case_name: boundedString(scenario.case_name || scenario.scenario, 80),
      probability: boundedScalar(scenario.probability),
      impact_status: boundedString(scenario.impact_status || "unknown_awaiting_sourced_inputs", 120),
      revenue_impact: scenario.revenue_impact ?? null,
      ebitda_impact: scenario.ebitda_impact ?? null,
      eps_impact: scenario.eps_impact ?? null,
      fcf_impact: scenario.fcf_impact ?? null,
      fair_value_impact: scenario.fair_value_impact ?? scenario.valuation_impact ?? null,
      assumptions: Array.isArray(scenario.assumptions)
        ? scenario.assumptions.slice(0, 6).map((item) => boundedString(item, 180)).filter(Boolean)
        : [],
      missing_inputs: Array.isArray(scenario.missing_inputs)
        ? scenario.missing_inputs.slice(0, 8).map((item) => boundedString(item, 180)).filter(Boolean)
        : [],
      quality_flags: Array.isArray(scenario.quality_flags)
        ? scenario.quality_flags.slice(0, 8).map((item) => boundedString(item, 120)).filter(Boolean)
        : [],
    });
  }
  return selected;
}

function projectDriverGraph(row) {
  const graph = isPlainObject(row.driver_graph) ? row.driver_graph : {};
  return {
    sector: boundedString(graph.sector, 80),
    status: boundedString(graph.status || "declarative_assumption", 80),
    drivers: Array.isArray(graph.drivers)
      ? graph.drivers.slice(0, 12).map((driver) => ({
          driver_id: boundedString(driver?.driver_id || driver?.id || driver?.name, 120),
          name: boundedString(driver?.name || driver?.driver, 160),
          label: boundedString(driver?.label || driver?.name, 160),
          assumption_type: "declarative_assumption",
        }))
      : [],
    edges: Array.isArray(graph.edges)
      ? graph.edges.slice(0, 12).map((edge) => ({
          from: boundedString(edge?.from || edge?.source, 120),
          to: boundedString(edge?.to || edge?.target, 120),
          label: boundedString(edge?.label || edge?.relationship, 160),
          assumption_type: "declarative_assumption",
        }))
      : [],
  };
}

function flattenObservationRows(source) {
  const rows = [];
  const visit = (value) => {
    if (!value || rows.length >= 24) return;
    if (Array.isArray(value)) {
      for (const item of value) visit(item);
      return;
    }
    if (!isPlainObject(value)) return;
    if (value.readiness === "model_loadable" || value.model_loadable === true) {
      rows.push({
        statement_type: boundedString(value.statement_type, 80),
        line_item: boundedString(value.line_item || value.line, 120),
        period_end: boundedString(value.period_end, 40),
        duration: boundedString(value.duration, 80),
        column_role: boundedString(value.column_role, 80),
        value: boundedScalar(value.value),
        normalized_value: boundedScalar(value.normalized_value),
        currency: boundedString(value.currency, 20),
        unit_multiplier: boundedScalar(value.unit_multiplier),
        readiness: "model_loadable",
        citation_id: null,
      });
    } else {
      for (const item of Object.values(value)) visit(item);
    }
  };
  visit(source);
  return rows.slice(0, 12);
}

function projectFinancialInputs(row) {
  const source = isPlainObject(row.financial_model_inputs) ? row.financial_model_inputs : {};
  const truth = isPlainObject(row.financial_truth_qualification) ? row.financial_truth_qualification : {};
  const truthQualified = truth.status === "qualified";
  const downstream = {};
  for (const key of DOWNSTREAM_KEYS) {
    downstream[key] = truthQualified
      ? boundedString(source.downstream_status?.[key] || BLOCKED_DOWNSTREAM[key], 120)
      : "blocked_financial_truth_not_qualified";
  }
  return {
    status: boundedString(source.status || "unsupported", 80),
    version: boundedString(source.version || source.model_version, 80),
    downstream_status: downstream,
    quality_flags: Array.isArray(source.quality_flags)
      ? source.quality_flags.slice(0, 10).map((item) => boundedString(item, 120)).filter(Boolean)
      : [],
    observations: truthQualified ? flattenObservationRows(source.observations || source) : [],
    derived: truthQualified && Array.isArray(source.derived)
      ? source.derived.slice(0, 12).map((item) =>
          boundedObject(item, ["metric", "period_end", "value", "status", "source_observation_ids"]),
        )
      : [],
  };
}

function projectCompanyBrain(row) {
  const source = isPlainObject(row.company_brain) ? row.company_brain : {};
  const domains = {};
  for (const [name, value] of ownEntries(source.domains).slice(0, 24)) {
    domains[name] = {
      status: boundedString(value.status || "unknown", 40),
      reference_count: Array.isArray(value.object_refs) ? value.object_refs.length : 0,
    };
  }
  const typeCounts = {};
  for (const item of Array.isArray(source.intelligence_objects) ? source.intelligence_objects : []) {
    const type = boundedString(item?.type, 40);
    if (type) typeCounts[type] = (typeCounts[type] || 0) + 1;
  }
  return {
    domains,
    type_counts: typeCounts,
    coverage: {
      object_count: Number.isInteger(source.coverage?.object_count) ? source.coverage.object_count : 0,
      available_or_partial_domains: Object.values(domains).filter((item) => ["available", "partial"].includes(item.status)).length,
      unknown_domains: Object.values(domains).filter((item) => item.status === "unknown").length,
      blocked_domains: Object.values(domains).filter((item) => item.status === "blocked").length,
    },
    recent_timeline: (Array.isArray(source.timeline) ? source.timeline : []).slice(-8).reverse().map((item) => ({
      date: boundedString(item.date, 40),
      intelligence_type: boundedString(item.type, 40),
      source_product: boundedString(item.source_product, 80),
    })),
  };
}

function projectSnapshotReadiness(row) {
  const status = isPlainObject(row.scenario_lab?.status) ? row.scenario_lab.status : {};
  const truth = isPlainObject(row.financial_truth_qualification) ? row.financial_truth_qualification : {};
  if (truth.status !== "qualified") {
    return {
      scenario_lab: "blocked_financial_truth_not_qualified",
      market_expectations: "blocked_financial_truth_not_qualified",
      valuation: "blocked_financial_truth_not_qualified",
      forecast: "blocked_financial_truth_not_qualified",
    };
  }
  return {
    scenario_lab: boundedString(status.scenario_lab || "blocked_missing_snapshot_inputs", 120),
    market_expectations: boundedString(status.market_expectations || "blocked_missing_snapshot_inputs", 120),
    valuation: boundedString(status.valuation || "blocked_missing_snapshot_inputs", 120),
    forecast: boundedString(status.forecast || "blocked_insufficient_qualified_history", 120),
  };
}

function projectThesisMonitoring(row) {
  const source = isPlainObject(row.thesis_monitoring) ? row.thesis_monitoring : {};
  const theses = Array.isArray(source.theses) ? source.theses : [];
  return {
    status: boundedString(source.status || "no_active_thesis", 80),
    active_thesis_count: Number.isInteger(source.active_thesis_count) ? source.active_thesis_count : theses.length,
    theses: theses.slice(0, 4).map((thesis) => ({
      status: boundedString(thesis?.status, 80),
      thesis_type: boundedString(thesis?.thesis_type, 80),
      source_cluster_id: boundedString(thesis?.source_cluster_id, 120),
      monitored_assertion: boundedString(thesis?.monitored_assertion || thesis?.assertion_key, 220),
      prove_check_count: Array.isArray(thesis?.prove_checks) ? thesis.prove_checks.length : 0,
      kill_check_count: Array.isArray(thesis?.kill_checks) ? thesis.kill_checks.length : 0,
      watch_item_count: Array.isArray(thesis?.watch_items) ? thesis.watch_items.length : 0,
    })),
  };
}

function projectConfidenceComponents(components) {
  const rows = Array.isArray(components)
    ? components
    : ownEntries(components).map(([name, value]) => ({ name, ...(isPlainObject(value) ? value : {}) }));
  return rows.slice(0, 7).map((component) => ({
    name: boundedString(component.name || component.component || component.key, 80),
    normalized_score: boundedScalar(component.normalized_score ?? component.score),
    weighted_points: boundedScalar(component.weighted_points ?? component.contribution ?? component.points),
  }));
}

function projectIntelligenceConfidence(row) {
  const source = isPlainObject(row.intelligence_confidence) ? row.intelligence_confidence : {};
  const assessments = Array.isArray(source.assessments) ? source.assessments : [];
  return {
    status: boundedString(source.status || (assessments.length ? "available" : "no_score"), 80),
    assessment_count: Number.isInteger(source.assessment_count) ? source.assessment_count : assessments.length,
    aggregate_score: boundedScalar(source.aggregate_score ?? source.score),
    aggregate_band: boundedString(source.aggregate_band || source.band || "no_score", 80),
    assessments: assessments.slice(0, 4).map((assessment) => ({
      confidence_id: boundedString(assessment?.confidence_id, 120),
      source_cluster_id: boundedString(assessment?.source_cluster_id, 120),
      score: boundedScalar(assessment?.score),
      band: boundedString(assessment?.band, 80),
      components: projectConfidenceComponents(assessment?.components),
    })),
  };
}

function hasDigit(value) {
  return typeof value === "string" && DIGIT_OR_FULLWIDTH.test(value);
}

function isSourceBoundEvidence(evidence) {
  const documentId = boundedString(evidence?.document_id || evidence?.doc_id, 80);
  const contentHash = boundedString(evidence?.content_sha256, 96);
  return (
    isPlainObject(evidence) &&
    isSafeHttpsUrl(evidence.source_url) &&
    !!documentId &&
    !!contentHash &&
    /^[a-f0-9]{64}$/i.test(contentHash) &&
    Number.isInteger(evidence.page) &&
    evidence.page > 0
  );
}

function projectCaseMechanism(caseObject, registry, symbol) {
  const mechanism = caseObject?.sections?.mechanism;
  if (
    !isPlainObject(mechanism) ||
    mechanism.status !== "available" ||
    mechanism.epistemic_type !== "reported_fact"
  ) {
    return null;
  }
  const items = (Array.isArray(mechanism.items) ? mechanism.items : [])
    .slice(0, 1)
    .map((item) => {
      const text = boundedString(item?.text, 220);
      if (!text || hasDigit(text) || CASE_FORBIDDEN_TEXT.test(text)) return null;
      const citation_ids = (Array.isArray(item?.evidence) ? item.evidence : [])
        .slice(0, 2)
        .filter(isSourceBoundEvidence)
        .map((evidence) => addCitation(registry, symbol, evidence, "case_mechanism", `${caseObject.case_id}:${item?.id || "item"}`))
        .filter(Boolean);
      return {
        item_id: boundedString(item?.id, 120),
        text,
        boundary: CASE_MECHANISM_BOUNDARY,
        citation_ids,
      };
    })
    .filter(Boolean)
    .filter((item) => item.citation_ids.length);
  if (!items.length) return null;
  return {
    status: "available_reported_fact",
    intelligence_type: "reported_fact",
    text: CASE_MECHANISM_LABEL,
    boundary: CASE_MECHANISM_BOUNDARY,
    items,
    citation_ids: [...new Set(items.flatMap((item) => item.citation_ids))],
  };
}

function projectIntelligenceCases(row, registry, symbol) {
  const source = isPlainObject(row.intelligence_cases) ? row.intelligence_cases : {};
  if (source.symbol && source.symbol !== symbol) return { status: "invalid_case_symbol", cases: [] };
  const lifecycle = new Set(["Observed", "Corroborated", "Modelled", "Validated", "Published", "Monitoring", "Closed"]);
  const cases = Array.isArray(source.cases) ? source.cases : [];
  return {
    status: boundedString(source.status || (cases.length ? "available" : "no_cases"), 80),
    cases: cases.slice(0, 1).flatMap((caseObject) => {
      if (!isPlainObject(caseObject) || caseObject.symbol !== symbol || !lifecycle.has(caseObject.status)) return [];
      const source_lineage = (Array.isArray(caseObject.source_lineage) ? caseObject.source_lineage : [])
        .slice(0, 1)
        .map((evidence) => ({
          citation_id: addCitation(registry, symbol, evidence, "intelligence_case", caseObject.case_id),
          document_id: boundedString(evidence?.document_id, 80),
        }))
        .filter((item) => item.citation_id);
      const observed_facts = (Array.isArray(caseObject.observed_facts) ? caseObject.observed_facts : [])
        .slice(0, 1)
        .map((fact) => ({
          fact_id: boundedString(fact?.fact_id, 120),
          statement: boundedString(fact?.statement, 180),
        }));
      const hypotheses = (Array.isArray(caseObject.alternative_readings) ? caseObject.alternative_readings : [])
        .slice(0, 2)
        .map((item) => ({
          hypothesis_id: boundedString(item?.alternative_id, 120),
          reading: boundedString(item?.reading, 180),
          rejection_condition: boundedString(item?.rejection_condition, 180),
        }));
      const watch_next = (Array.isArray(caseObject.sections?.watch_next?.items) ? caseObject.sections.watch_next.items : [])
        .slice(0, 2)
        .map((item) => ({
          watch_id: boundedString(item?.id, 160),
          condition: boundedString(item?.text, 180),
          status: boundedString(item?.status, 80),
          source_required: boundedString(item?.reason, 120),
        }));
      return [{
        case_id: boundedString(caseObject.case_id, 120),
        status: boundedString(caseObject.status, 40),
        epistemic_type: boundedString(caseObject.epistemic_type, 80),
        summary: boundedString(caseObject.summary, 180),
        observed_facts,
        mechanism: projectCaseMechanism(caseObject, registry, symbol),
        hypotheses,
        watch_next,
        source_lineage,
      }];
    }),
  };
}

export function projectCompany(row = {}, options = {}) {
  if (!isPlainObject(row)) throw new Error("invalid_company_row");
  const requestedSymbol = typeof options === "string" ? options : options.symbol;
  const symbol = row.symbol;
  if (typeof symbol !== "string" || !PILOT_SET.has(symbol)) throw new Error("symbol_not_allowed");
  if (requestedSymbol && requestedSymbol !== symbol) throw new Error("symbol_row_mismatch");
  const registry = { byId: new Map() };
  const { signals, linkedEventIds } = projectSignals(row, registry, symbol);
  const operating_events = projectEvents(row, registry, symbol, linkedEventIds);
  const projected = {
    schema_version: "ask_phase_c_case_v1",
    symbol,
    name: boundedString(row.name, 160),
    sector: boundedString(row.sector, 120),
    approved_brief: projectBrief(row, registry, symbol),
    signals,
    operating_events,
    event_studies: projectStudies(row, linkedEventIds),
    impact_scenarios: projectScenarios(row, linkedEventIds),
    driver_graph: projectDriverGraph(row),
    financial_model_inputs: projectFinancialInputs(row),
    company_brain: projectCompanyBrain(row),
    snapshot_readiness: projectSnapshotReadiness(row),
    thesis_monitoring: projectThesisMonitoring(row),
    intelligence_confidence: projectIntelligenceConfidence(row),
    intelligence_cases: projectIntelligenceCases(row, registry, symbol),
    citation_registry: {
      owner_symbol: symbol,
      citations: [...registry.byId.values()].sort((a, b) => a.citation_id.localeCompare(b.citation_id)),
    },
  };
  if (byteLength(projected) > CONTEXT_LIMIT) throw new Error("context_too_large");
  return projected;
}

export function buildAnswerSections(context, modelOutput = {}) {
  if (!isPlainObject(context) || !PILOT_SET.has(context.symbol)) throw new Error("invalid_context");
  const allowed = new Set((context.citation_registry?.citations || []).map((citation) => citation.citation_id));
  const safeModel = validateModelOutput(modelOutput, allowed, { symbol: context.symbol, allowEmpty: true });
  const downstream = {
    ...context.financial_model_inputs.downstream_status,
    ...context.snapshot_readiness,
  };
  const snapshotReady = [downstream.scenario_lab, downstream.market_expectations, downstream.valuation]
    .some((value) => String(value || "").startsWith("ready_"));
  return {
    schema_version: "ask_answer_v1",
    symbol: context.symbol,
    sections: {
      conclusion: {
        status: safeModel.conclusion ? "validated_inference" : "placeholder",
        intelligence_type: "validated_inference",
        text: safeModel.conclusion || "Unknown — awaiting validated inference.",
        citation_ids: safeModel.citation_ids || [],
      },
      evidence: {
        status: "server_rendered",
        intelligence_type: "reported_fact",
        items: (context.citation_registry?.citations || []).map((citation) => ({
          citation_id: citation.citation_id,
          label: citation.label,
          owner_symbol: citation.owner_symbol,
        })),
      },
      mechanism: {
        status: safeModel.mechanism ? "validated_inference" : "placeholder",
        intelligence_type: "validated_inference",
        text: safeModel.mechanism || "Unknown — no model inference accepted.",
        citation_ids: safeModel.citation_ids || [],
      },
      historical_benchmark: {
        status: context.event_studies.length ? "available" : "empty_state",
        methodology: "descriptive, not causal; raw simple price-return methodology when present",
        studies: context.event_studies,
      },
      financial_impact: {
        status: "unknown_current",
        text: "Unknown — awaiting sourced inputs.",
      },
      scenarios: {
        status: context.impact_scenarios.length ? "available" : "empty_state",
        scenarios: context.impact_scenarios,
      },
      valuation_readiness: {
        status: snapshotReady ? "snapshot_tools_available" : "unknown_current",
        downstream_status: downstream,
      },
      confidence: {
        status: context.intelligence_confidence.status,
        aggregate_score: context.intelligence_confidence.aggregate_score,
        aggregate_band: context.intelligence_confidence.aggregate_band,
        assessment_count: context.intelligence_confidence.assessment_count,
        assessments: context.intelligence_confidence.assessments,
      },
      what_to_watch: {
        status: safeModel.what_to_watch ? "validated_inference" : "server_placeholder",
        intelligence_type: "validated_inference",
        text: safeModel.what_to_watch || "Monitor only the state-derived affected drivers and coverage gaps.",
        citation_ids: safeModel.citation_ids || [],
      },
    },
  };
}

export function validateModelSelection(selection) {
  if (selection === "qualitative") return { mode: "qualitative" };
  if (isPlainObject(selection) && selection.mode === "qualitative" && Object.keys(selection).length === 1) {
    return { mode: "qualitative" };
  }
  throw new Error("invalid_model_selection");
}

function validateIds(ids, allowedIds, key) {
  if (ids === undefined) return [];
  if (!Array.isArray(ids)) throw new Error(`invalid_${key}`);
  return ids.map((id) => {
    if (typeof id !== "string" || !allowedIds.has(id)) throw new Error("unknown_id");
    return id;
  });
}

function validateSafeModelText(value, symbol) {
  if (value === undefined) return undefined;
  if (typeof value !== "string") throw new Error("invalid_output_text");
  if (byteLength(value) > 1200) throw new Error("output_text_too_large");
  if (DIGIT_OR_FULLWIDTH.test(value) || UNSAFE_MODEL_TEXT.test(value)) throw new Error("unsafe_output");
  for (const pilot of PILOT_SYMBOLS) {
    if (pilot !== symbol && new RegExp(`\\b${pilot.replace(".", "\\.")}\\b`, "i").test(value)) {
      throw new Error("cross_symbol_output");
    }
  }
  return value.trim();
}

export function validateModelOutput(output = {}, allowedIds = new Set(), options = {}) {
  if (!isPlainObject(output)) throw new Error("invalid_output");
  const allowed = allowedIds instanceof Set ? allowedIds : new Set(allowedIds || []);
  const keys = Object.keys(output);
  for (const key of keys) {
    if (!SAFE_MODEL_KEYS.has(key)) throw new Error("extra_output_key");
  }
  const citation_ids = validateIds(output.citation_ids, allowed, "citation_ids");
  const evidence_ids = validateIds(output.evidence_ids, allowed, "evidence_ids");
  const result = {};
  for (const key of ["conclusion", "mechanism", "what_to_watch"]) {
    const text = validateSafeModelText(output[key], options.symbol);
    if (text !== undefined) result[key] = text;
  }
  if (citation_ids.length) result.citation_ids = citation_ids;
  if (evidence_ids.length) result.evidence_ids = evidence_ids;
  const hasQualitative = ["conclusion", "mechanism", "what_to_watch"].some(
    (key) => result[key] && !/^unknown\b/i.test(result[key]),
  );
  if (hasQualitative && !citation_ids.length && !evidence_ids.length) {
    throw new Error("missing_citation_tie");
  }
  if (!options.allowEmpty && !keys.length) throw new Error("empty_output");
  return result;
}
