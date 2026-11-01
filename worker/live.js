/* Live-score proxy for the NPL fan site (Cloudflare Worker).

   The official API rejects browser requests from other origins, and the
   GitHub Pages data only refreshes every ~30 minutes. This Worker fetches
   the same `matches` endpoint the scraper uses, with the same User-Agent,
   trims it to the fields the live panel needs, and serves it with CORS for
   the site. Responses are memoised per isolate for TTL_MS so a busy page
   still sends at most a couple of upstream requests a minute. */

const UPSTREAM = "https://nplt20league.com/api/v1/matches?season=2026";
const SCORECARD_BASE = "https://nplt20league.com/api/v1/matches/";
const MATCH_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const USER_AGENT = "npl-calendar-bot/1.0 (+https://github.com/codila125/npl)";
const ALLOWED_ORIGINS = ["https://codila125.github.io", "http://localhost:8000"];
const TTL_MS = 30 * 1000;

let memo = null; // { at: epoch ms, body: string }
const scorecardMemo = new Map(); // match id -> { at: epoch ms, body: string }

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


const num = (v) => (v === null || v === undefined || v === "" ? null : Number(v));
const text = (v) => (v === null || v === undefined || v === "" ? null : String(v));
const player = (p) => ({ key: p.key ?? null, name: p.name ?? "", role: p.role ?? null });

function trimInnings(inn) {
  return {
    id: inn.inningsId ?? null,
    team_id: inn.teamId ?? null,
    team: inn.teamName ?? null,
    short: inn.shortName ?? null,
    score: text(inn.score),
    runs: num(inn.runs),
    wickets: num(inn.wickets),
    overs: text(inn.overs),
    extras: num(inn.extras),
    extras_detail: text(inn.extrasDetail),
    batting: (inn.batting || []).map((b) => ({
      key: b.key ?? null,
      name: b.name ?? "",
      runs: num(b.runs),
      balls: num(b.balls),
      fours: num(b.fours),
      sixes: num(b.sixes),
      strike_rate: num(b.strikeRate),
      out: b.out === true,
      on_strike: b.onStrike === true,
      dismissal: text(b.dismissal),
    })),
    bowling: (inn.bowling || []).map((b) => ({
      key: b.key ?? null,
      name: b.name ?? "",
      overs: text(b.overs),
      maidens: num(b.maidens),
      runs: num(b.runs),
      wickets: num(b.wickets),
      economy: num(b.economy),
      bowling_now: b.bowlingNow === true,
    })),
    fall_of_wickets: (inn.fallOfWickets || []).map((f) => ({
      over: text(f.over),
      score: text(f.score),
      player: text(f.playerName),
    })),
  };
}

// The feed sometimes lists a delivery twice (a bare "no run," stub, then the
// full commentary) under the same over label. Wides share their label with the
// next legal ball, so `extra` ("WD", "NB") is part of the identity. Keep the
// entry with the most text, in the order first seen (newest first).
function trimCommentary(entries) {
  const byBall = new Map();
  for (const c of entries || []) {
    if ((c.type !== "ball" && c.type !== "wicket") || text(c.over) === null) {
      continue;
    }
    const code = String(c.runs ?? "").toUpperCase();
    const extra = ["WD", "NB", "LB", "B"].includes(code) ? code : null;
    const ball = {
      innings: c.inningsId ?? null,
      over: text(c.over),
      over_number: num(c.overNumber),
      ball: num(c.ballNumber),
      batter: text(c.batterName),
      bowler: text(c.bowlerName),
      runs: num(c.runsScored),
      extra,
      wicket: c.isWicket === true,
      boundary: c.isBoundary === true,
      text: text(c.text),
    };
    const key = `${ball.innings}|${ball.over}|${extra}|${ball.wicket}`;
    const prev = byBall.get(key);
    if (!prev || (ball.text || "").length > (prev.text || "").length) {
      byBall.set(key, ball);
    }
  }
  return [...byBall.values()];
}

export function trimScorecard(source, fetchedAt) {
  const d = source && source.data;
  if (!d || typeof d !== "object" || !Array.isArray(d.innings)) {
    throw new Error("upstream returned no scorecard");
  }
  const side = (t) => ({
    team_id: t?.teamId ?? null,
    name: t?.name ?? null,
    score: text(t?.score),
    overs: text(t?.overs),
  });
  return {
    fetched_at: fetchedAt,
    id: d.matchId ?? null,
    status: d.status ?? null,
    result: d.result ?? null,
    toss: text(d.toss),
    target: num(d.targetRuns),
    max_overs: num(d.maxOvers),
    current_innings: d.currentInningsId ?? null,
    innings_order: Array.isArray(d.inningsOrder) ? d.inningsOrder : [],
    updated_at: d.updatedAt ?? null,
    team1: side(d.team1),
    team2: side(d.team2),
    squad: {
      team1: ((d.squad && d.squad.team1) || []).map(player),
      team2: ((d.squad && d.squad.team2) || []).map(player),
    },
    innings: d.innings.map(trimInnings),
    commentary: trimCommentary(d.commentary),
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

async function loadScorecard(id, fetchImpl, now) {
  const hit = scorecardMemo.get(id);
  if (hit && now - hit.at < TTL_MS) {
    return hit.body;
  }
  const resp = await fetchImpl(`${SCORECARD_BASE}${id}/scorecard`, {
    headers: { "User-Agent": USER_AGENT, Accept: "application/json" },
  });
  if (resp.status === 404) {
    return null;
  }
  if (resp.status !== 200) {
    throw new Error(`upstream HTTP ${resp.status}`);
  }
  const body = JSON.stringify(trimScorecard(await resp.json(), new Date(now).toISOString()));
  if (scorecardMemo.size >= 64) {
    scorecardMemo.clear();
  }
  scorecardMemo.set(id, { at: now, body });
  return body;
}

export async function handle(request, fetchImpl = fetch, now = Date.now()) {
  const cors = corsHeaders(request.headers.get("Origin"));
  const url = new URL(request.url);
  if (request.method === "OPTIONS") {
    return new Response(null, { status: 204, headers: cors });
  }
  const scorecard = url.pathname.match(/^\/live\/([^/]+)$/);
  if (request.method !== "GET" || (url.pathname !== "/live" && !scorecard)) {
    return json({ error: "not_found" }, 404, cors);
  }
  if (scorecard && !MATCH_ID.test(scorecard[1])) {
    return json({ error: "not_found" }, 404, cors);
  }
  try {
    if (scorecard) {
      const body = await loadScorecard(scorecard[1], fetchImpl, now);
      return body === null ? json({ error: "not_found" }, 404, cors) : json(body, 200, cors);
    }
    return json(await loadLive(fetchImpl, now), 200, cors);
  } catch (err) {
    return json({ error: "upstream_unavailable" }, 502, { ...cors, "Cache-Control": "no-store" });
  }
}

export function resetMemo() {
  memo = null;
  scorecardMemo.clear();
}

export default {
  fetch: (request) => handle(request),
};
