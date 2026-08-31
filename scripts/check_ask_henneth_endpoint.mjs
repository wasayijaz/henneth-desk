#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { PILOT_SYMBOLS } from "../Henneth Desk 2.CI.0/api/ask_contract.js";
import { BODY_LIMIT, createHandler } from "../Henneth Desk 2.CI.0/api/ask.js";

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const SLICE = JSON.parse(fs.readFileSync(path.join(ROOT, "Henneth Desk 2.CI.0", "data", "company_intelligence.json"), "utf8"));
const row = SLICE.tickers.find((candidate) => candidate.symbol === "MLCF");
let checks = 0;

function assert(condition, message) {
  checks += 1;
  if (!condition) throw new Error(message);
}

function response(body, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

function makeRequest(body, headers = {}, method = "POST") {
  return new Request("https://ci.henneth.app/api/ask", {
    method,
    headers: { "content-type": "application/json", ...headers },
    body: method === "POST" ? (typeof body === "string" ? body : JSON.stringify(body)) : undefined,
  });
}

function deps(overrides = {}) {
  const calls = { data: 0, groq: 0, auth: 0 };
  const fetchImpl = async (url, options = {}) => {
    if (String(url).includes("company_intelligence.json")) {
      calls.data += 1;
      assert(options.headers?.authorization === "Bearer owner-token", "data bearer forwarding");
      assert(options.headers?.["cache-control"] === "no-store", "data no-store forwarding");
      return new Response(JSON.stringify(SLICE), { headers: { "content-type": "application/json" } });
    }
    throw new Error("unexpected network call");
  };
  const groq = async (apiKey, messages, schema) => {
    calls.groq += 1;
    assert(apiKey === "test-key", "provider key forwarding");
    assert(schema?.strict === true && schema?.schema?.additionalProperties === false, "strict provider schema");
    if (calls.groq === 1) {
      assert(schema.schema.properties.mode.enum.length === 1 && schema.schema.properties.mode.enum[0] === "qualitative", "qualitative-only selection");
      return { mode: "qualitative" };
    }
    assert(messages?.[0]?.content?.includes("do not upgrade an Observed case"), "case lifecycle system guard");
    const supplied = JSON.parse(messages?.[1]?.content || "{}");
    assert(supplied.context?.intelligence_cases?.cases?.[0]?.status === "Observed", "source-bound observed case supplied to Ask");
    return overrides.modelOutput || {};
  };
  return {
    calls,
    fetchImpl: overrides.fetchImpl || fetchImpl,
    ownerId: "owner-id",
    groqApiKey: "test-key",
    verifyToken: async (token) => {
      calls.auth += 1;
      if (token === "owner-token") return { sub: "owner-id", exp: Date.now() / 1000 + 60 };
      if (token === "other-token") return { sub: "other-id", exp: Date.now() / 1000 + 60 };
      return null;
    },
    callGroq: overrides.callGroq || groq,
  };
}

async function bodyJson(result) { return result.json(); }

async function main() {
  let d = deps();
  let handler = createHandler(d);
  let result = await handler(makeRequest({ symbol: "MLCF", question: "What changed in the latest filing?" }, { authorization: "Bearer owner-token" }));
  let payload = await bodyJson(result);
  assert(result.status === 200, "success status");
  assert(payload.ok === true && payload.answer?.schema_version === "ask_answer_v1", "success answer schema");
  assert(Array.isArray(payload.citations), "server citations only");
  assert(result.headers.get("cache-control") === "no-store", "response no-store");
  assert(d.calls.data === 1 && d.calls.groq === 2, "one data fetch and two bounded provider calls");

  result = await handler(makeRequest({ symbol: "MLCF", question: "x" }, {}, "GET"));
  assert(result.status === 405, "POST only");
  result = await handler(makeRequest({ symbol: "MLCF", question: "x" }));
  assert(result.status === 401, "missing auth");
  result = await handler(makeRequest({ symbol: "MLCF", question: "x" }, { authorization: "Bearer other-token" }));
  assert(result.status === 403, "non-owner forbidden");

  let noAuthCalls = 0;
  d = deps({ fetchImpl: async () => { noAuthCalls += 1; throw new Error("must not call"); } });
  handler = createHandler(d);
  result = await handler(makeRequest({ symbol: "MLCF", question: "x" }, { authorization: "Bearer invalid" }));
  assert(result.status === 401 && noAuthCalls === 0 && d.calls.data === 0 && d.calls.groq === 0, "no data/provider before auth");

  result = await handler(makeRequest({ symbol: "MLCF", question: "x".repeat(BODY_LIMIT) }, { authorization: "Bearer owner-token" }));
  assert(result.status === 413, "raw body byte cap");

  d = deps({ modelOutput: { conclusion: "Unsafe 10% claim", citation_ids: ["missing"] } });
  handler = createHandler(d);
  result = await handler(makeRequest({ symbol: "MLCF", question: "What changed?" }, { authorization: "Bearer owner-token" }));
  payload = await bodyJson(result);
  assert(result.status === 200 && payload.answer.sections.conclusion.status === "placeholder", "unsafe model output deterministic fallback");

  d = deps({ fetchImpl: async () => response({}, 503) });
  handler = createHandler(d);
  result = await handler(makeRequest({ symbol: "MLCF", question: "What changed?" }, { authorization: "Bearer owner-token" }));
  assert(result.status === 502, "data failure is generic 502");

  d = deps({ callGroq: async () => { throw new Error("provider secret detail"); } });
  handler = createHandler(d);
  result = await handler(makeRequest({ symbol: "MLCF", question: "What changed?" }, { authorization: "Bearer owner-token" }));
  payload = await bodyJson(result);
  assert(result.status === 502 && !JSON.stringify(payload).includes("provider secret"), "provider failure does not leak detail");

  d = deps({ fetchImpl: async (url) => new Response(JSON.stringify({ tickers: PILOT_SYMBOLS.filter((symbol) => symbol !== "MLCF").map((symbol) => ({ symbol })) })) });
  handler = createHandler(d);
  result = await handler(makeRequest({ symbol: "MLCF", question: "What changed?" }, { authorization: "Bearer owner-token" }));
  assert(result.status === 502, "exact requested row required");

  console.log(`ask_henneth_endpoint: PASS (${checks} endpoint assertions)`);
}

main().catch((error) => {
  console.error(`ask_henneth_endpoint: FAIL — ${error.message}`);
  process.exitCode = 1;
});
