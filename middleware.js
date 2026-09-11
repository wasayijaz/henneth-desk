/* EDGE MIDDLEWARE — the account gate for the desk's data layer.
 *
 * WHY THIS EXISTS
 * Until now the sign-in screen gated the INTERFACE, not the DATA. Every file under /state/ was a
 * plain static asset, so `curl https://desk.henneth.app/state/backtests.json` returned 4.7 MB of
 * results to anyone, with no account, no cookie and no key. The whole research product —
 * rooms.json (the Desk Room debates), dossiers.json, fairvalue.json, claims.json, strategy_map —
 * was one wget away. This closes that.
 *
 * WHY MIDDLEWARE AND NOT A SERVERLESS PROXY
 * state/ is 92 MB across 729 files. Streaming that through a function would blow the bundle limit,
 * add a cold start to every one of the ~23 fetches a ticker page makes, and undo the mobile
 * performance work. Middleware runs BEFORE the static asset is served, so the files stay on the
 * CDN and only gain an auth check.
 *
 * WHY THE TOKEN CAN BE VERIFIED HERE WITH NO SECRET
 * This Supabase project signs access tokens with ES256 (asymmetric, P-256) and publishes the
 * PUBLIC half at /auth/v1/.well-known/jwks.json. So verification is a local Web Crypto operation
 * against a public key: no shared secret to store in an env var and leak, and no round trip to
 * Supabase per request. Confirmed against the live JWKS before this was written — if the project
 * is ever switched back to legacy HS256 symmetric keys, `alg` stops being ES256 and EVERY request
 * fails closed (see verify()), which is the correct direction to fail.
 */

const JWKS_URL = 'https://qteoncckohuoatbjjykb.supabase.co/auth/v1/.well-known/jwks.json';

/* THE DELIBERATE EXCEPTIONS. Two different reasons; keep them distinguishable.
 *
 * 1. natal_ephem.bin / natal_ephem.json (owner decision, 2026-07-21).
 *    /cast — casting a birth chart — stays open, because it is the top of the acquisition funnel:
 *    a stranger gets real value first and the chart follows them into the account they create
 *    afterwards (see migrateGuestChart in app.js).
 *    These are an ASTRONOMICAL EPHEMERIS — planetary positions over time. Public-domain physics
 *    anyone can compute with open-source libraries. Not research, no desk output, and they reveal
 *    nothing about how the desk reasons.
 *    NOTE: docs/PUBLICATION_RESTRUCTURE.md §5 cuts personal astro from launch. When that lands,
 *    these two come OUT of this set — but only after the probe below is live, never before, or
 *    watchdog.py loses its unauthenticated health check.
 *
 * 2. public_probe.json — written by build_dashboard.py, exists solely to be fetched without a
 *    credential so watchdog.py can prove the deploy propagated and /state/ is reachable. Built
 *    from a literal with a timestamp and nothing else.
 *
 * Add to this set ONLY if the same test passes: is the file public knowledge that happens to be
 * cached here (or infrastructure with no desk output), rather than something the desk produced?
 * Everything proprietary — every backtest, valuation, debate, score and claim — requires an
 * account. */
const PUBLIC_FILES = new Set(['natal_ephem.bin', 'natal_ephem.json', 'public_probe.json']);

// Owner-only Company Intelligence artifacts are not part of the root desk's /state surface.
// They are removed from the root build and denied here as defense-in-depth, even for a valid
// desk bearer. Keep this list synchronized with scripts/root_state_publication.py; preflight
// runs scripts/check_root_state_publication.py to enforce that.
const CI_PRIVATE_STATE_FILES = new Set([
  'company_documents.json',
  'company_briefs.json',
  'company_brief_receipts.json',
  'company_event_ledger.json',
  'company_financial_series.json',
  'company_source_qa.json',
  'document_synthesis_queue.json',
]);
const CI_PRIVATE_STATE_PREFIXES = ['company_intel/'];

/* JWKS cached per edge isolate. Supabase rotates signing keys rarely; an hour of staleness costs
 * at most one failed verification after a rotation, and the next request refetches. */
let keyCache = null;
let keyCacheAt = 0;
const KEY_TTL_MS = 60 * 60 * 1000;

function b64urlToBytes(s) {
  const norm = s.replace(/-/g, '+').replace(/_/g, '/');
  const padded = norm + '='.repeat((4 - (norm.length % 4)) % 4);
  const bin = atob(padded);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

async function getKeys() {
  const now = Date.now();
  if (keyCache && now - keyCacheAt < KEY_TTL_MS) return keyCache;
  const res = await fetch(JWKS_URL, { cf: { cacheTtl: 3600 } });
  if (!res.ok) throw new Error('jwks ' + res.status);
  const jwks = await res.json();
  const map = new Map();
  for (const k of jwks.keys || []) {
    if (k.kty !== 'EC' || k.crv !== 'P-256') continue;
    const key = await crypto.subtle.importKey(
      'jwk', k, { name: 'ECDSA', namedCurve: 'P-256' }, false, ['verify']
    );
    map.set(k.kid, key);
  }
  keyCache = map;
  keyCacheAt = now;
  return map;
}

/* Returns true ONLY for a token that is well-formed, ES256, unexpired, and carries a signature
 * that verifies against the project's published public key. Every failure path — malformed,
 * wrong algorithm, unknown key id, expired, bad signature, JWKS unreachable — returns false.
 * There is no branch that returns true without a successful crypto.subtle.verify(). */
async function verify(token) {
  try {
    const parts = token.split('.');
    if (parts.length !== 3) return false;
    const [h, p, s] = parts;

    const header = JSON.parse(new TextDecoder().decode(b64urlToBytes(h)));
    const payload = JSON.parse(new TextDecoder().decode(b64urlToBytes(p)));

    // `alg` is attacker-controlled, so it is checked against an allowlist rather than trusted.
    // This is what blocks the classic alg:none and alg-confusion forgeries.
    if (header.alg !== 'ES256') return false;
    if (!header.kid) return false;
    // exp is in seconds. A 30s skew allowance, and expiry is mandatory — a token with no exp
    // would otherwise be valid forever.
    if (typeof payload.exp !== 'number') return false;
    if (payload.exp * 1000 < Date.now() - 30_000) return false;

    const keys = await getKeys();
    const key = keys.get(header.kid);
    if (!key) return false;

    // ES256 JWT signatures are raw r||s (64 bytes), which is exactly the format Web Crypto's
    // ECDSA verify expects — no DER unwrapping needed.
    return await crypto.subtle.verify(
      { name: 'ECDSA', hash: 'SHA-256' },
      key,
      b64urlToBytes(s),
      new TextEncoder().encode(h + '.' + p)
    );
  } catch {
    return false;
  }
}

function deny(reason) {
  return new Response(
    JSON.stringify({ error: 'account_required', detail: reason }),
    {
      status: 401,
      headers: {
        'content-type': 'application/json',
        // Never let a denial be cached — a visitor who signs in a second later must not be
        // served a stale 401 from the browser or the CDN.
        'cache-control': 'no-store',
        'www-authenticate': 'Bearer realm="henneth-desk"',
      },
    }
  );
}

function notFound() {
  return new Response(null, {
    status: 404,
    headers: { 'cache-control': 'no-store' },
  });
}

function normalizeStatePath(file) {
  let value = String(file || '');
  for (let i = 0; i < 3; i++) {
    try {
      const decoded = decodeURIComponent(value);
      if (decoded === value) break;
      value = decoded;
    } catch {
      return null;
    }
  }
  value = value.replace(/\\/g, '/').replace(/^\/+/, '');
  while (value.startsWith('state/')) value = value.slice('state/'.length);

  const parts = [];
  for (const part of value.split('/')) {
    if (!part || part === '.') continue;
    if (part === '..') return null;
    parts.push(part);
  }
  return parts.join('/');
}

function isCiPrivateStatePath(file) {
  const normalized = normalizeStatePath(file);
  if (normalized === null) return true;
  return CI_PRIVATE_STATE_FILES.has(normalized)
    || CI_PRIVATE_STATE_PREFIXES.some((prefix) => normalized.startsWith(prefix));
}

export const config = {
  // Only the data layer. index.html, app.js, themes.css and the brand assets stay public — the
  // app shell has to load in order to show a sign-in screen at all.
  matcher: '/state/:path*',
};

export default async function middleware(request) {
  const path = new URL(request.url).pathname;
  const file = path.replace(/^\/state\//, '');

  if (isCiPrivateStatePath(file)) return notFound();
  if (PUBLIC_FILES.has(file)) return; // open funnel — see PUBLIC_FILES

  const header = request.headers.get('authorization') || '';
  if (!header.startsWith('Bearer ')) return deny('missing bearer token');

  const ok = await verify(header.slice(7).trim());
  if (!ok) return deny('invalid or expired token');

  // Returning nothing continues to the static asset on the CDN.
  return;
}
