import { buildAnswerSections, byteLength, projectCompany, validateModelOutput, validateModelSelection, validateRequest } from "./ask_contract.js";

export const config = { runtime: "edge" };
export const BODY_LIMIT = 16 * 1024;
// A bounded owner-only slice currently carries 20 Company Brains and their
// provenance. Keep a hard cap while accommodating the published artifact.
const DATA_LIMIT = 8 * 1024 * 1024;
const JWKS_URL = "https://qteoncckohuoatbjjykb.supabase.co/auth/v1/.well-known/jwks.json";
const DEFAULT_MODEL = "openai/gpt-oss-120b";
let keyCache = null;
let keyCacheAt = 0;

function json(status, body) {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" } });
}
function b64urlToBytes(value) {
  const normalized = value.replace(/-/g, "+").replace(/_/g, "/");
  const padded = normalized + "=".repeat((4 - (normalized.length % 4)) % 4);
  const binary = atob(padded);
  return Uint8Array.from(binary, (character) => character.charCodeAt(0));
}
async function verifyToken(token, ownerId, fetchImpl = fetch) {
  if (!token || !ownerId) return null;
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;
    const [headerPart, payloadPart, signaturePart] = parts;
    const header = JSON.parse(new TextDecoder().decode(b64urlToBytes(headerPart)));
    const payload = JSON.parse(new TextDecoder().decode(b64urlToBytes(payloadPart)));
    if (header.alg !== "ES256" || !header.kid || typeof payload.exp !== "number" || payload.exp * 1000 < Date.now() - 30_000) return null;
    const now = Date.now();
    if (!keyCache || now - keyCacheAt >= 60 * 60 * 1000) {
      const response = await fetchImpl(JWKS_URL, { cache: "no-store" });
      if (!response.ok) return null;
      const jwks = await response.json();
      const imported = new Map();
      for (const jwk of jwks.keys || []) {
        if (jwk.kty !== "EC" || jwk.crv !== "P-256" || !jwk.kid) continue;
        imported.set(jwk.kid, await crypto.subtle.importKey("jwk", jwk, { name: "ECDSA", namedCurve: "P-256" }, false, ["verify"]));
      }
      keyCache = imported;
      keyCacheAt = now;
    }
    const key = keyCache.get(header.kid);
    if (!key) return null;
    const valid = await crypto.subtle.verify({ name: "ECDSA", hash: "SHA-256" }, key, b64urlToBytes(signaturePart), new TextEncoder().encode(`${headerPart}.${payloadPart}`));
    return valid ? payload : null;
  } catch { return null; }
}

export async function readBoundedBody(request, limit = BODY_LIMIT) {
  const declared = Number(request.headers.get("content-length"));
  if (Number.isFinite(declared) && declared > limit) throw new Error("body_too_large");
  if (!request.body) {
    const text = await request.text();
    if (byteLength(text) > limit) throw new Error("body_too_large");
    return text;
  }
  const reader = request.body.getReader();
  const chunks = [];
  let total = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      total += value.byteLength;
      if (total > limit) throw new Error("body_too_large");
      chunks.push(value);
    }
  } finally { reader.releaseLock(); }
  const bytes = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
  return new TextDecoder().decode(bytes);
}

async function loadCompanyRow(request, token, symbol, fetchImpl = fetch) {
  const url = new URL("/data/company_intelligence.json", request.url);
  const response = await fetchImpl(url, { headers: { authorization: `Bearer ${token}`, "cache-control": "no-store" }, cache: "no-store" });
  if (!response.ok) throw new Error("data_unavailable");
  const bytes = new Uint8Array(await response.arrayBuffer());
  if (bytes.byteLength > DATA_LIMIT) throw new Error("data_too_large");
  const data = JSON.parse(new TextDecoder().decode(bytes));
  const row = (Array.isArray(data?.tickers) ? data.tickers : []).find((candidate) => candidate?.symbol === symbol);
  if (!row) throw new Error("company_not_found");
  return row;
}

function parseModelJson(content) {
  if (typeof content !== "string" || !content.trim()) throw new Error("model_empty");
  const trimmed = content.trim();
  const fenced = /^```(?:json)?\s*([\s\S]*?)\s*```$/i.exec(trimmed);
  return JSON.parse(fenced ? fenced[1] : trimmed);
}
const SELECTION_SCHEMA = Object.freeze({ name: "henneth_qualitative_selection", strict: true, schema: { type: "object", properties: { mode: { type: "string", enum: ["qualitative"] } }, required: ["mode"], additionalProperties: false } });
const OUTPUT_SCHEMA = Object.freeze({ name: "henneth_qualitative_answer", strict: true, schema: { type: "object", properties: { conclusion: { type: "string" }, mechanism: { type: "string" }, what_to_watch: { type: "string" }, citation_ids: { type: "array", items: { type: "string" } }, evidence_ids: { type: "array", items: { type: "string" } } }, additionalProperties: false } });

async function callGroq(apiKey, messages, schema, fetchImpl = fetch) {
  if (!apiKey) throw new Error("provider_not_configured");
  const response = await fetchImpl("https://api.groq.com/openai/v1/chat/completions", { method: "POST", headers: { "content-type": "application/json", authorization: `Bearer ${apiKey}` }, body: JSON.stringify({ model: process.env.CI_ASK_MODEL || process.env.GROQ_MODEL || DEFAULT_MODEL, temperature: 0, max_tokens: 700, response_format: { type: "json_schema", json_schema: schema }, messages }) });
  if (!response.ok) throw new Error(response.status === 429 ? "provider_busy" : "provider_error");
  const payload = await response.json();
  return parseModelJson(payload?.choices?.[0]?.message?.content);
}

export function createHandler(deps = {}) {
  const fetchImpl = deps.fetchImpl || fetch;
  const verifyImpl = deps.verifyToken || ((token, owner) => verifyToken(token, owner, fetchImpl));
  const rowImpl = deps.fetchCompanyRow || loadCompanyRow;
  const groqImpl = deps.callGroq || callGroq;
  return async function handler(request) {
    if (request.method !== "POST") return json(405, { ok: false, error: "method_not_allowed" });
    const ownerId = deps.ownerId ?? process.env.CI_OWNER_USER_ID;
    if (!ownerId) return json(500, { ok: false, error: "service_unavailable" });
    const authorization = request.headers.get("authorization") || "";
    if (!authorization.startsWith("Bearer ")) return json(401, { ok: false, error: "account_required" });
    const token = authorization.slice(7).trim();
    const identity = await verifyImpl(token, ownerId);
    if (!identity) return json(401, { ok: false, error: "account_required" });
    if (identity.sub !== ownerId) return json(403, { ok: false, error: "owner_required" });
    const apiKey = deps.groqApiKey ?? process.env.GROQ_API_KEY;
    if (!apiKey) return json(500, { ok: false, error: "service_unavailable" });
    let body;
    try { body = JSON.parse(await readBoundedBody(request)); } catch (error) { return json(error.message === "body_too_large" ? 413 : 400, { ok: false, error: error.message === "body_too_large" ? "body_too_large" : "bad_request" }); }
    let cleanRequest;
    try { cleanRequest = validateRequest(body); } catch { return json(400, { ok: false, error: "bad_request" }); }
    let context;
    try { context = projectCompany(await rowImpl(request, token, cleanRequest.symbol, fetchImpl), { symbol: cleanRequest.symbol }); } catch { return json(502, { ok: false, error: "data_unavailable" }); }
    let selection;
    try { selection = validateModelSelection(await groqImpl(apiKey, [{ role: "system", content: "Return only the qualitative mode as strict JSON." }, { role: "user", content: JSON.stringify({ mode: "qualitative", symbol: cleanRequest.symbol }) }], SELECTION_SCHEMA, fetchImpl)); } catch { return json(502, { ok: false, error: "model_unavailable" }); }
    if (selection.mode !== "qualitative") return json(502, { ok: false, error: "model_unavailable" });
    let modelOutput = {};
    try {
      const allowed = new Set((context.citation_registry?.citations || []).map((citation) => citation.citation_id));
      const raw = await groqImpl(apiKey, [{ role: "system", content: "Return only qualitative source-tied JSON. Use an Intelligence Case only at its emitted lifecycle and epistemic type; do not upgrade an Observed case or invent model outputs. No numbers, dates, prices, advice, URLs, or other company symbols." }, { role: "user", content: JSON.stringify({ context, question: cleanRequest.question }) }], OUTPUT_SCHEMA, fetchImpl);
      modelOutput = validateModelOutput(raw, allowed, { symbol: context.symbol, allowEmpty: true });
    } catch { modelOutput = {}; }
    const answer = buildAnswerSections(context, modelOutput);
    return json(200, { ok: true, answer, citations: context.citation_registry.citations });
  };
}

export default createHandler();
export { OUTPUT_SCHEMA, SELECTION_SCHEMA, verifyToken };
