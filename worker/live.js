/* Live-score proxy for the NPL fan site (Cloudflare Worker).

   The official API rejects browser requests from other origins, and the
   GitHub Pages data only refreshes every ~30 minutes. This Worker fetches
   the same `matches` endpoint the scraper uses, with the same User-Agent,
   trims it to the fields the live panel needs, and serves it with CORS for
   the site. Responses are memoised per isolate for TTL_MS so a busy page
   still sends at most a couple of upstream requests a minute. */

const UPSTREAM = "https://nplt20league.com/api/v1/matches?season=2026";
const USER_AGENT = "npl-calendar-bot/1.0 (+https://github.com/codila125/npl)";
const ALLOWED_ORIGINS = ["https://codila125.github.io", "http://localhost:8000"];
const TTL_MS = 30 * 1000;

let memo = null; // { at: epoch ms, body: string }

function corsHeaders(origin) {
  const headers = { Vary: "Origin" };
  if (origin && ALLOWED_ORIGINS.includes(origin)) {
    headers["Access-Control-Allow-Origin"] = origin;
    headers["Access-Control-Allow-Methods"] = "GET, OPTIONS";
  }
  return headers;
}

function json(body, status, extra) {
  return new Response(typeof body === "string" ? body : JSON.stringify(body), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": `public, max-age=${TTL_MS / 1000}`,
      ...extra,
    },
  });
}

export function trim(source, fetchedAt) {
  if (!source || !Array.isArray(source.data) || source.data.length === 0) {
    throw new Error("upstream returned no `data` list");
  }
  return {
    fetched_at: fetchedAt,
    matches: source.data.map((m) => ({
      id: m.id,
      status: m.status,
      result: m.result ?? null,
      updated_at: m.updatedAt ?? null,
      teams: (m.participants || []).map((p) => ({
        slug: p.slug ?? null,
        score: p.score ?? null,
        overs: p.overs ?? null,
        target: p.target ?? null,
      })),
    })),
  };
}

async function loadLive(fetchImpl, now) {
  if (memo && now - memo.at < TTL_MS) {
    return memo.body;
  }
  const resp = await fetchImpl(UPSTREAM, {
    headers: { "User-Agent": USER_AGENT, Accept: "application/json" },
  });
  if (resp.status !== 200) {
    throw new Error(`upstream HTTP ${resp.status}`);
  }
  const body = JSON.stringify(trim(await resp.json(), new Date(now).toISOString()));
  memo = { at: now, body };
  return body;
}

export async function handle(request, fetchImpl = fetch, now = Date.now()) {
  const cors = corsHeaders(request.headers.get("Origin"));
  const url = new URL(request.url);
  if (request.method === "OPTIONS") {
    return new Response(null, { status: 204, headers: cors });
  }
  if (request.method !== "GET" || url.pathname !== "/live") {
    return json({ error: "not_found" }, 404, cors);
  }
  try {
    return json(await loadLive(fetchImpl, now), 200, cors);
  } catch (err) {
    return json({ error: "upstream_unavailable" }, 502, { ...cors, "Cache-Control": "no-store" });
  }
}

export function resetMemo() {
  memo = null;
}

export default {
  fetch: (request) => handle(request),
};
