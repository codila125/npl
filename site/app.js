/* Nepal Premier League 2026 — static site behaviour. */
"use strict";

(function () {
  var NPT_OFFSET_MS = (5 * 60 + 45) * 60 * 1000;
  var MATCH_WINDOW_MS = 4 * 60 * 60 * 1000;
  var DATA_URL = "data/npl.json";
  // Cloudflare Worker in worker/live.js; empty disables the live panel.
  var LIVE_URL = "https://npl-live.codyprab34.workers.dev/live";
  var LIVE_POLL_MS = 30 * 1000;
  var LIVE_LEAD_MS = 15 * 60 * 1000;
  var LIVE_TAIL_MS = 6 * 60 * 60 * 1000;
  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  var DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

  var main = document.getElementById("main");
  var liveRegion = document.getElementById("live-region");
  var refreshNote = document.getElementById("refresh-note");
  var standingsContent = document.getElementById("standings-content");
  var statsContent = document.getElementById("stats-content");
  var scheduleContent = document.getElementById("schedule-content");
  var calendarStatus = document.getElementById("calendar-status");
  var calendarList = document.getElementById("calendar-list");
  var themeToggle = document.getElementById("theme-toggle");
  var livePanel = document.getElementById("live");
  var liveContent = document.getElementById("live-content");

  var currentData = null;
  var schemaMismatch = false;
  var lastHiddenAt = null;
  var liveTimer = null;
  var lastLive = null;
  var lastCards = {};
  var selectedInnings = {};
  var liveView = null;

  function announce(message) {
    liveRegion.textContent = "";
    liveRegion.textContent = message;
  }

  function make(tag, className, text) {
    var node = document.createElement(tag);
    if (className) {
      node.className = className;
    }
    if (text !== undefined && text !== null) {
      node.textContent = String(text);
    }
    return node;
  }

  function clear(node) {
    node.replaceChildren();
  }

  function setMessage(container, text) {
    clear(container);
    container.appendChild(make("p", null, text));
  }

  function siteBase() {
    return new URL(".", document.baseURI).href;
  }

  function webcalUrl(url) {
    var parsed = new URL(url);
    return "webcal://" + parsed.host + parsed.pathname;
  }

  function googleUrl(url) {
    return "https://calendar.google.com/calendar/r?cid=" + encodeURIComponent(webcalUrl(url));
  }

  function nptDate(iso) {
    var ms = Date.parse(iso);
    if (Number.isNaN(ms)) {
      return null;
    }
    return new Date(ms + NPT_OFFSET_MS);
  }

  function pad2(value) {
    return String(value).padStart(2, "0");
  }

  function formatUpdatedAt(iso) {
    var d = nptDate(iso);
    if (!d) {
      return iso;
    }
    var hour = d.getUTCHours();
    var ap = hour >= 12 ? "PM" : "AM";
    hour = hour % 12 || 12;
    return d.getUTCDate() + " " + MONTHS[d.getUTCMonth()] + " " + d.getUTCFullYear() +
      ", " + hour + ":" + pad2(d.getUTCMinutes()) + " " + ap;
  }

  function formatDate(iso) {
    var d = nptDate(iso);
    if (!d) {
      return iso;
    }
    return DAYS[d.getUTCDay()] + " " + d.getUTCDate() + " " + MONTHS[d.getUTCMonth()];
  }

  function formatTime(iso) {
    var d = nptDate(iso);
    if (!d) {
      return iso;
    }
    var hour = d.getUTCHours();
    var ap = hour >= 12 ? "PM" : "AM";
    hour = hour % 12 || 12;
    return hour + ":" + pad2(d.getUTCMinutes()) + " " + ap;
  }

  function formatNrr(value) {
    if (value > 0) {
      return "+" + value.toFixed(3);
    }
    if (value < 0) {
      return "\u2212" + Math.abs(value).toFixed(3);
    }
    return "0.000";
  }

  function capitalize(value) {
    if (!value) {
      return "";
    }
    return value.charAt(0).toUpperCase() + value.slice(1);
  }

  function phaseOf(match, now) {
    if (match.status === "completed") {
      return "completed";
    }
    var startMs = Date.parse(match.start_utc);
    if (Number.isNaN(startMs)) {
      return "upcoming";
    }
    if (now >= startMs && now < startMs + MATCH_WINDOW_MS) {
      return "inprogress";
    }
    if (now >= startMs + MATCH_WINDOW_MS) {
      return "awaiting";
    }
    return "upcoming";
  }

  function matchLabel(match) {
    return match.stage === "league" ? "Match " + match.number : match.label;
  }

  function statusText(match, phase) {
    if (match.status === "completed") {
      return match.outcome === "no_result" ? "No result" : "Completed";
    }
    if (match.status === "other") {
      return capitalize(match.status_raw);
    }
    if (phase === "inprogress") {
      return "In progress";
    }
    if (phase === "awaiting") {
      return "Awaiting result";
    }
    return "Upcoming";
  }

  function sideScore(side) {
    if (side.score === null || side.score === undefined) {
      return null;
    }
    var text = side.name + " " + side.score;
    if (side.overs !== null && side.overs !== undefined) {
      text += " (" + side.overs + " ov)";
    }
    return text;
  }

  function scoreLine(match) {
    if (match.outcome === "result") {
      if (match.teams.length < 2) {
        return null;
      }
      if (match.teams[0].score === null || match.teams[0].score === undefined ||
          match.teams[1].score === null || match.teams[1].score === undefined) {
        return null;
      }
      return match.teams.map(sideScore).join(" · ");
    }
    if (match.outcome === "no_result") {
      var parts = match.teams.map(sideScore).filter(Boolean);
      return parts.length ? parts.join(" · ") : null;
    }
    return null;
  }

  function retryButton() {
    var button = make("button", "retry", "Retry");
    button.type = "button";
    button.addEventListener("click", function () {
      loadData(false);
    });
    return button;
  }

  function renderErrorBlock(container) {
    clear(container);
    container.appendChild(make("p", null, "Couldn't load data."));
    container.appendChild(retryButton());
    if (schemaMismatch) {
      container.appendChild(make("p", null, "Try a hard refresh."));
    }
  }

  function renderStandings() {
    var data = currentData;
    if (!data.standings || data.standings.length === 0) {
      setMessage(standingsContent, "Standings are not available yet.");
      return;
    }

    var wrap = make("div", "table-wrap");
    wrap.tabIndex = 0;
    wrap.setAttribute("role", "region");
    wrap.setAttribute("aria-labelledby", "standings-caption");

    var table = make("table");
    var caption = make("caption", null, "NPL 2026 points table");
    caption.id = "standings-caption";
    table.appendChild(caption);

    var thead = make("thead");
    var headRow = make("tr");
    ["Pos", "Team", "P", "W", "L", "NR/T", "Pts", "NRR"].forEach(function (label) {
      var th = make("th", null, label);
      th.scope = "col";
      headRow.appendChild(th);
    });
    thead.appendChild(headRow);
    table.appendChild(thead);

    var tbody = make("tbody");
    var teamsBySlug = {};
    data.teams.forEach(function (team) {
      teamsBySlug[team.slug] = team;
    });

    data.standings.forEach(function (row) {
      var tr = make("tr");
      tr.appendChild(make("td", null, row.position));

      var teamCell = make("th");
      teamCell.scope = "row";
      var team = teamsBySlug[row.team];
      teamCell.appendChild(make("span", "team-full", team ? team.name : row.team));
      var short = make("span", "team-short", team ? team.short : row.team);
      short.setAttribute("aria-hidden", "true");
      teamCell.appendChild(short);
      tr.appendChild(teamCell);

      tr.appendChild(make("td", null, row.played));
      tr.appendChild(make("td", null, row.won));
      tr.appendChild(make("td", null, row.lost));
      tr.appendChild(make("td", null, row.tied + row.no_result));
      tr.appendChild(make("td", null, row.points));
      tr.appendChild(make("td", null, formatNrr(row.nrr)));
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    wrap.appendChild(table);

    clear(standingsContent);
    standingsContent.appendChild(wrap);
  }

  function statValue(value) {
    return value === null || value === undefined ? "–" : value;
  }

  // Columns per leaderboard; `key` marks the figure the board is ranked by.
  var STAT_BOARDS = [
    { category: "top_run_scorer", title: "Most runs", columns: [
      ["Inns", "innings"], ["Runs", "runs", true], ["Avg", "average"], ["SR", "strike_rate"]] },
    { category: "top_wicket_taker", title: "Most wickets", columns: [
      ["Inns", "innings"], ["Wkts", "wickets", true], ["Avg", "average"], ["Econ", "economy"]] },
    { category: "batting_strike_rate", title: "Best strike rate", columns: [
      ["Inns", "innings"], ["Runs", "runs"], ["SR", "strike_rate", true]] },
    { category: "bowling_economy", title: "Best economy", columns: [
      ["Inns", "innings"], ["Wkts", "wickets"], ["Econ", "economy", true]] }
  ];

  function statsTable(board, leaders, teamsBySlug) {
    var wrap = make("div", "table-wrap");
    wrap.tabIndex = 0;
    wrap.setAttribute("role", "region");
    var captionId = "stats-caption-" + board.category;
    wrap.setAttribute("aria-labelledby", captionId);

    var table = make("table");
    var caption = make("caption", null, board.title);
    caption.id = captionId;
    table.appendChild(caption);

    var thead = make("thead");
    var headRow = make("tr");
    ["#", "Player", "Team"].concat(board.columns.map(function (c) { return c[0]; }))
      .forEach(function (label) {
        var th = make("th", null, label);
        th.scope = "col";
        headRow.appendChild(th);
      });
    thead.appendChild(headRow);
    table.appendChild(thead);

    var tbody = make("tbody");
    leaders.forEach(function (row) {
      var tr = make("tr");
      tr.appendChild(make("td", null, row.rank));
      var player = make("th", null, row.player);
      player.scope = "row";
      tr.appendChild(player);
      var team = teamsBySlug[row.team];
      var teamCell = make("td");
      var abbr = make("abbr", null, team ? team.short : row.team);
      if (team) {
        abbr.title = team.name;
      }
      teamCell.appendChild(abbr);
      tr.appendChild(teamCell);
      board.columns.forEach(function (column) {
        tr.appendChild(make("td", column[2] ? "key" : null, statValue(row[column[1]])));
      });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    wrap.appendChild(table);
    return wrap;
  }

  function renderStats() {
    var stats = currentData.stats;
    var boards = STAT_BOARDS.filter(function (board) {
      return stats && Array.isArray(stats[board.category]) && stats[board.category].length > 0;
    });
    if (boards.length === 0) {
      setMessage(statsContent, "Stats are not available yet.");
      return;
    }
    var teamsBySlug = {};
    currentData.teams.forEach(function (team) {
      teamsBySlug[team.slug] = team;
    });
    var grid = make("div", "stats-grid");
    boards.forEach(function (board) {
      grid.appendChild(statsTable(board, stats[board.category], teamsBySlug));
    });
    clear(statsContent);
    statsContent.appendChild(grid);
  }

  function renderSchedule() {
    var data = currentData;
    if (!data.matches || data.matches.length === 0) {
      setMessage(scheduleContent, "The schedule is not available yet.");
      return;
    }

    var now = Date.now();
    var matches = data.matches.slice().sort(function (a, b) {
      if (a.start_utc !== b.start_utc) {
        return a.start_utc < b.start_utc ? -1 : 1;
      }
      return a.number - b.number;
    });

    var rows = [];
    matches.forEach(function (match) {
      var startMs = Date.parse(match.start_utc);
      if (Number.isNaN(startMs)) {
        console.warn("Skipping match with unparsable start_utc", match.number);
        return;
      }
      rows.push({ match: match, phase: phaseOf(match, now), startMs: startMs });
    });

    var next = null;
    for (var i = 0; i < rows.length; i++) {
      if (rows[i].phase !== "completed") {
        next = rows[i];
        break;
      }
    }

    var summary = make("p", "next-summary");
    if (next) {
      var nextMatch = next.match;
      var nextTeams = nextMatch.teams.map(function (side) { return side.name; }).join(" vs ");
      summary.appendChild(document.createTextNode(
        matchLabel(nextMatch) + " · " + nextTeams + " · " +
        formatDate(nextMatch.start_utc) + ", " + formatTime(nextMatch.start_utc) + " NPT "
      ));
      var jump = make("a", null, "Jump to it");
      jump.href = "#next-match";
      summary.appendChild(jump);
    } else {
      summary.textContent = "Season complete.";
    }

    var filterRow = make("div", "filter-row");
    var filterLabel = make("label", null, "Show matches for:");
    filterLabel.htmlFor = "team-filter";
    var select = make("select");
    select.id = "team-filter";
    select.appendChild(make("option", null, "All teams"));
    select.lastChild.value = "";
    data.teams.forEach(function (team) {
      var option = make("option", null, team.name);
      option.value = team.slug;
      select.appendChild(option);
    });
    filterRow.appendChild(filterLabel);
    filterRow.appendChild(select);

    var wrap = make("div", "table-wrap");
    wrap.tabIndex = 0;
    wrap.setAttribute("role", "region");
    wrap.setAttribute("aria-labelledby", "schedule-caption");

    var table = make("table");
    var caption = make("caption", null, "NPL 2026 schedule");
    caption.id = "schedule-caption";
    table.appendChild(caption);

    var thead = make("thead");
    var headRow = make("tr");
    ["#", "Date", "Time (NPT)", "Match", "Venue", "Result/Status"].forEach(function (label) {
      var th = make("th", null, label);
      th.scope = "col";
      headRow.appendChild(th);
    });
    thead.appendChild(headRow);
    table.appendChild(thead);

    var tbody = make("tbody");
    rows.forEach(function (item) {
      var match = item.match;
      var phase = item.phase;
      var tr = make("tr");
      if (next && match === next.match) {
        tr.id = "next-match";
        tr.tabIndex = -1;
        tr.classList.add("next-match");
      }
      if (phase === "completed") {
        tr.classList.add("completed");
      }

      var slugs = [];
      match.teams.forEach(function (side) {
        if (side.slug) {
          slugs.push(side.slug);
        }
      });
      tr.dataset.slugs = slugs.join(" ");

      tr.appendChild(make("td", null, match.stage === "league" ? match.number : match.label));
      tr.appendChild(make("td", null, formatDate(match.start_utc)));
      tr.appendChild(make("td", null, formatTime(match.start_utc)));

      var matchCell = make("td");
      match.teams.forEach(function (side, index) {
        if (index > 0) {
          matchCell.appendChild(document.createTextNode(" vs "));
        }
        matchCell.appendChild(make("span", side.placeholder ? "placeholder" : null, side.name));
      });
      tr.appendChild(matchCell);

      tr.appendChild(make("td", null, match.venue));

      var statusCell = make("td");
      if (next && match === next.match) {
        statusCell.appendChild(make("span", "badge", phase === "inprogress" ? "LIVE" : "NEXT"));
        statusCell.appendChild(document.createTextNode(" "));
      }
      var word = statusText(match, phase);
      statusCell.appendChild(document.createTextNode(word));

      if (match.status === "completed") {
        var detail = null;
        if (match.outcome === "result") {
          detail = match.result || null;
        } else if (match.outcome === "no_result") {
          detail = match.result || "No result";
        }
        if (detail && detail.toLowerCase() !== word.toLowerCase()) {
          statusCell.appendChild(make("br"));
          statusCell.appendChild(document.createTextNode(detail));
        }
        var scores = scoreLine(match);
        if (scores) {
          statusCell.appendChild(make("br"));
          statusCell.appendChild(document.createTextNode(scores));
        }
      }

      tr.appendChild(statusCell);
      tbody.appendChild(tr);
    });

    var noMatchesRow = make("tr", "no-matches");
    noMatchesRow.hidden = true;
    var noMatchesCell = make("td", null, "No matches for this team.");
    noMatchesCell.colSpan = 6;
    noMatchesRow.appendChild(noMatchesCell);
    tbody.appendChild(noMatchesRow);

    table.appendChild(tbody);
    wrap.appendChild(table);

    function applyFilter() {
      var slug = select.value;
      var visibleCount = 0;
      tbody.querySelectorAll("tr:not(.no-matches)").forEach(function (tr) {
        var slugs = tr.dataset.slugs ? tr.dataset.slugs.split(" ") : [];
        var show = !slug || slugs.indexOf(slug) !== -1;
        tr.hidden = !show;
        if (show) {
          visibleCount += 1;
        }
      });
      noMatchesRow.hidden = !slug || visibleCount > 0;
    }

    select.addEventListener("change", applyFilter);

    clear(scheduleContent);
    scheduleContent.appendChild(summary);
    scheduleContent.appendChild(filterRow);
    scheduleContent.appendChild(wrap);
  }

  function buildCalendarRow(slug, name) {
    var url = siteBase() + "calendar/" + slug + ".ics";

    var li = make("li", "calendar-row team-row");
    li.appendChild(make("span", "calendar-name", name));

    var actions = make("span", "calendar-actions");

    var subscribe = make("a", "btn subscribe", "Subscribe");
    subscribe.href = webcalUrl(url);
    subscribe.setAttribute("aria-label", "Subscribe to " + name + " calendar");
    actions.appendChild(subscribe);

    var googleLink = make("a", "btn google", "Google Calendar");
    googleLink.href = googleUrl(url);
    googleLink.target = "_blank";
    googleLink.rel = "noopener";
    googleLink.setAttribute("aria-label", "Add " + name + " to Google Calendar");
    actions.appendChild(googleLink);

    var copy = make("button", "copy", "Copy URL");
    copy.type = "button";
    copy.dataset.url = url;
    copy.setAttribute("aria-label", "Copy " + name + " calendar URL");
    actions.appendChild(copy);

    li.appendChild(actions);
    return li;
  }

  function renderCalendar() {
    var data = currentData;
    clear(calendarStatus);
    calendarList.querySelectorAll(".team-row").forEach(function (row) {
      row.remove();
    });
    data.teams.forEach(function (team) {
      if (!/^[a-z0-9-]+$/.test(team.slug)) {
        console.warn("Skipping team with invalid slug", team.slug);
        return;
      }
      calendarList.appendChild(buildCalendarRow(team.slug, team.name));
    });
  }

  function updateStaticAllMatchesRow() {
    var row = document.getElementById("all-matches-row");
    if (!row) {
      return;
    }
    var url = siteBase() + "calendar/npl.ics";
    row.querySelector(".subscribe").href = webcalUrl(url);
    row.querySelector(".google").href = googleUrl(url);
    row.querySelector(".copy").dataset.url = url;
  }

  function copyUrl(url, button) {
    function success() {
      var original = button.textContent;
      button.textContent = "Copied";
      announce("Copied " + url);
      setTimeout(function () {
        button.textContent = original;
      }, 2000);
    }
    function fail() {
      announce("Copy failed — copy the URL manually.");
      window.prompt("Copy this calendar URL:", url);
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(url).then(success, fail);
    } else {
      fail();
    }
  }

  // Matches the live panel follows: not completed in the published data and
  // inside [start - LIVE_LEAD_MS, start + LIVE_TAIL_MS).
  function liveCandidates(now) {
    if (!currentData) {
      return [];
    }
    return currentData.matches.filter(function (match) {
      var startMs = Date.parse(match.start_utc);
      return match.status !== "completed" && !Number.isNaN(startMs) &&
        now >= startMs - LIVE_LEAD_MS && now < startMs + LIVE_TAIL_MS;
    });
  }

  function hasScore(live) {
    return live.teams.some(function (side) {
      return side.score !== null && side.score !== undefined;
    });
  }

  function liveStatus(match, live, now) {
    if (live && live.status === "completed") {
      return live.result || "Completed";
    }
    if (live && hasScore(live)) {
      return null;
    }
    if (now < Date.parse(match.start_utc)) {
      return "Starts " + formatTime(match.start_utc) + " NPT";
    }
    return "Scheduled for " + formatTime(match.start_utc) + " NPT";
  }

  function cell(tag, text, className) {
    return make(tag, className || null, text === null || text === undefined ? "–" : text);
  }

  function scoreTable(caption, columns, rows) {
    var wrap = make("div", "table-wrap");
    var table = make("table", "score-table");
    table.appendChild(make("caption", null, caption));
    var head = make("tr");
    columns.forEach(function (name, index) {
      head.appendChild(make("th", index === 0 ? null : "num", name));
    });
    table.appendChild(make("thead")).appendChild(head);
    var body = make("tbody");
    rows.forEach(function (row) {
      body.appendChild(row);
    });
    table.appendChild(body);
    wrap.appendChild(table);
    return wrap;
  }

  function nameCell(name, note, active) {
    var th = make("th");
    var line = make("span", active ? "at-crease" : null, name + (active ? " *" : ""));
    th.appendChild(line);
    if (note) {
      th.appendChild(make("span", "sub", note));
    }
    return th;
  }

  function battingRows(innings) {
    return innings.batting.map(function (b) {
      var row = make("tr");
      var active = !b.out && b.on_strike;
      row.appendChild(nameCell(b.name, b.out ? b.dismissal : "not out", active));
      row.appendChild(cell("td", b.runs, "num strong"));
      row.appendChild(cell("td", b.balls, "num"));
      row.appendChild(cell("td", b.fours, "num"));
      row.appendChild(cell("td", b.sixes, "num"));
      row.appendChild(cell("td", b.strike_rate === null ? null : b.strike_rate.toFixed(1), "num"));
      return row;
    });
  }

  function bowlingRows(innings) {
    return innings.bowling.map(function (b) {
      var row = make("tr");
      row.appendChild(nameCell(b.name, null, b.bowling_now));
      row.appendChild(cell("td", b.overs, "num"));
      row.appendChild(cell("td", b.maidens, "num"));
      row.appendChild(cell("td", b.runs, "num"));
      row.appendChild(cell("td", b.wickets, "num strong"));
      row.appendChild(cell("td", b.economy === null ? null : b.economy.toFixed(2), "num"));
      return row;
    });
  }

  // Scorecard names carry role marks the squad list lacks: "Rohit Paudel (c)".
  function bareName(name) {
    return name.replace(/\s*\((?:c|wk|c & wk)\)\s*$/i, "").trim();
  }

  // Squad members of `teamId` whose name is not in `seen`.
  function yetTo(card, teamId, seen) {
    var side = card.team1.team_id === teamId ? card.squad.team1 : card.squad.team2;
    var taken = seen.map(bareName);
    return side.filter(function (p) {
      return taken.indexOf(bareName(p.name)) === -1;
    }).map(function (p) { return p.name; });
  }

  function listLine(label, names) {
    var line = make("p", "roster");
    line.appendChild(make("strong", null, label));
    line.appendChild(document.createTextNode(" " + (names.length ? names.join(", ") : "–")));
    return line;
  }

  // Newest-first commentary → overs newest-first, each ball oldest-first.
  function recentOvers(card, inningsId) {
    var overs = [];
    var byNumber = {};
    card.commentary.forEach(function (c) {
      if (c.innings !== inningsId || c.over_number === null) {
        return;
      }
      var group = byNumber[c.over_number];
      if (!group) {
        group = { number: c.over_number + 1, bowler: c.bowler, balls: [] };
        byNumber[c.over_number] = group;
        overs.push(group);
      }
      group.balls.unshift(c);
    });
    // The API only sends the latest ~20 balls, so an older over is often cut
    // off at its start. Keep the newest over (it may be in progress) and show
    // an older one only when all six legal balls are known.
    return overs.filter(function (over, index) {
      var legal = over.balls.filter(function (ball) { return !ball.extra || ball.extra[0] === "L" || ball.extra === "B"; });
      return index === 0 || legal.length >= 6;
    }).slice(0, 4);
  }

  function ballKey(ball) {
    return [ball.innings, ball.over, ball.extra, ball.wicket].join("|");
  }

  // Poll results carry only the latest balls; keep earlier ones we have seen
  // so overs complete while the page stays open. Newest first, newest wins.
  function mergeCommentary(fresh, previous) {
    var seen = {};
    fresh.forEach(function (ball) { seen[ballKey(ball)] = true; });
    var kept = (previous || []).filter(function (ball) { return !seen[ballKey(ball)]; });
    return fresh.concat(kept).slice(0, 120);
  }

  function renderOvers(card, innings) {
    var overs = recentOvers(card, innings.id);
    if (overs.length === 0) {
      return null;
    }
    var list = make("ol", "overs");
    overs.forEach(function (over) {
      var item = make("li");
      var total = over.balls.reduce(function (sum, ball) { return sum + (ball.runs || 0); }, 0);
      item.appendChild(make("span", "over-no", "Over " + over.number));
      var balls = make("span", "balls");
      over.balls.forEach(function (ball) {
        var chip = make("span", "ball" + (ball.wicket ? " wicket" : ball.boundary ? " boundary" : ""),
          ball.wicket ? "W" : ball.extra ? ball.extra.charAt(0) + ball.extra.slice(1).toLowerCase() :
            ball.runs === null ? "·" : ball.runs);
        chip.title = ball.over + " " + (ball.text || "");
        balls.appendChild(chip);
      });
      item.appendChild(balls);
      item.appendChild(make("span", "over-meta", total + (total === 1 ? " run · " : " runs · ") + (over.bowler || "")));
      list.appendChild(item);
    });
    var block = make("div", "overs-block");
    block.appendChild(make("h3", null, "Recent overs"));
    block.appendChild(list);
    return block;
  }

  function ballsOf(overs) {
    var parts = String(overs || "0").split(".");
    return Number(parts[0]) * 6 + Number(parts[1] || 0);
  }

  // "X need N runs from B balls · RRR" while the second innings is in progress.
  function chaseLine(card, current) {
    if (!current || card.status === "completed" || !card.target || !card.max_overs ||
        card.innings_order.indexOf(current.id) !== 1 || current.runs === null) {
      return null;
    }
    var need = card.target - current.runs;
    var left = card.max_overs * 6 - ballsOf(current.overs);
    if (need <= 0 || left <= 0) {
      return null;
    }
    var rate = (need * 6 / left).toFixed(2);
    return current.team + " need " + need + " from " + left + " balls · required rate " + rate;
  }

  function stat(label, value) {
    var node = make("div", "crease-stat");
    node.appendChild(make("span", "crease-name", label));
    node.appendChild(make("span", "crease-figure", value));
    return node;
  }

  // Who is out there right now: not-out batters and the bowler in action.
  function renderCrease(innings) {
    var batters = innings.batting.filter(function (b) {
      return !b.out && (b.balls || b.runs || b.on_strike);
    });
    var bowler = innings.bowling.filter(function (b) { return b.bowling_now; })[0];
    if (!batters.length && !bowler) {
      return null;
    }
    var strip = make("div", "crease");
    strip.appendChild(make("h3", null, "At the crease"));
    var row = make("div", "crease-row");
    batters.slice(0, 2).forEach(function (b) {
      var item = stat(b.name + (b.on_strike ? " *" : ""), b.runs + " (" + b.balls + ")");
      item.classList.add("batter");
      item.appendChild(make("span", "crease-sub", b.fours + "×4 · " + b.sixes + "×6 · SR " +
        (b.strike_rate === null ? "–" : b.strike_rate.toFixed(0))));
      row.appendChild(item);
    });
    if (bowler) {
      var item = stat(bowler.name, bowler.wickets + "/" + bowler.runs);
      item.classList.add("bowler");
      item.appendChild(make("span", "crease-sub", bowler.overs + " ov · " + bowler.maidens +
        " mdn · econ " + (bowler.economy === null ? "–" : bowler.economy.toFixed(1))));
      row.appendChild(item);
    }
    strip.appendChild(row);
    return strip;
  }

  function renderInnings(card, innings) {
    var panel = make("div", "innings");
    var crease = card.status !== "completed" && card.current_innings === innings.id ?
      renderCrease(innings) : null;
    if (crease) {
      panel.appendChild(crease);
    }
    var overs = renderOvers(card, innings);
    if (overs) {
      panel.appendChild(overs);
    }
    var otherTeamId = card.team1.team_id === innings.team_id ? card.team2.team_id : card.team1.team_id;
    panel.appendChild(scoreTable("Batting", ["Batter", "R", "B", "4s", "6s", "SR"], battingRows(innings)));
    panel.appendChild(listLine("Yet to bat", yetTo(card, innings.team_id, innings.batting.map(function (b) {
      return b.name;
    }))));
    if (innings.extras_detail) {
      panel.appendChild(listLine("Extras", [innings.extras + " (" + innings.extras_detail + ")"]));
    }
    if (innings.fall_of_wickets.length) {
      panel.appendChild(listLine("Fall of wickets", innings.fall_of_wickets.map(function (f) {
        return f.score + " (" + f.player + ", " + f.over + " ov)";
      })));
    }
    panel.appendChild(scoreTable("Bowling", ["Bowler", "O", "M", "R", "W", "Econ"], bowlingRows(innings)));
    panel.appendChild(listLine("Yet to bowl", yetTo(card, otherTeamId, innings.bowling.map(function (b) {
      return b.name;
    }))));
    return panel;
  }

  function renderTabs(matchId, innings, selectedId) {
    var tabs = make("div", "innings-tabs");
    tabs.setAttribute("role", "group");
    tabs.setAttribute("aria-label", "Innings");
    innings.forEach(function (inn) {
      var tab = make("button", "innings-tab", (inn.short || inn.team) + " " + (inn.score || ""));
      tab.type = "button";
      tab.setAttribute("aria-pressed", inn.id === selectedId ? "true" : "false");
      tab.setAttribute("data-tab", matchId + ":" + inn.id);
      tab.addEventListener("click", function () {
        selectedInnings[matchId] = inn.id;
        rerenderLive();
      });
      tabs.appendChild(tab);
    });
    return tabs;
  }

  function renderScorecard(match, card) {
    var wrap = make("div", "scorecard");
    var shown = card.innings.filter(function (inn) {
      return inn.batting.length || inn.bowling.length;
    });
    if (!shown.length) {
      return wrap;
    }
    var selected = shown.filter(function (inn) {
      return inn.id === selectedInnings[match.id];
    })[0] || shown.filter(function (inn) {
      return inn.id === card.current_innings;
    })[0] || shown[0];
    // Current innings first, so the tabs read "now, then earlier".
    shown.sort(function (a, b) {
      return (b.id === card.current_innings) - (a.id === card.current_innings);
    });
    if (shown.length > 1) {
      wrap.appendChild(renderTabs(match.id, shown, selected.id));
    }
    wrap.appendChild(renderInnings(card, selected));
    return wrap;
  }

  function renderBoard(match, live, card) {
    var liveBySlug = {};
    live.teams.forEach(function (side) {
      liveBySlug[side.slug] = side;
    });
    var batting = null;
    if (card) {
      card.innings.forEach(function (inn) {
        if (inn.id === card.current_innings) {
          batting = inn.team;
        }
      });
    }
    var board = make("div", "board");
    match.teams.forEach(function (side) {
      var row = liveBySlug[side.slug];
      var team = make("div", "board-team" + (batting === side.name && live.status !== "completed" ? " batting" : ""));
      team.appendChild(make("span", "board-name", side.name));
      team.appendChild(make("span", "board-score", row && row.score ? row.score : "Yet to bat"));
      if (row && row.score && row.overs) {
        team.appendChild(make("span", "board-overs", row.overs + " ov"));
      }
      board.appendChild(team);
    });
    return board;
  }

  function renderLiveMatch(match, live, now, card) {
    var block = make("div", "live-match");
    var head = make("p", "live-title");
    if (live && hasScore(live) && live.status !== "completed") {
      head.appendChild(make("span", "badge", "LIVE"));
    }
    head.appendChild(make("span", null, matchLabel(match) + " · " +
      match.teams.map(function (side) { return side.name; }).join(" vs ")));
    block.appendChild(head);

    if (live && hasScore(live)) {
      block.appendChild(renderBoard(match, live, card));
    }
    var status = liveStatus(match, live, now);
    var current = card && card.innings.filter(function (inn) {
      return inn.id === card.current_innings;
    })[0];
    var chase = card ? chaseLine(card, current) : null;
    if (chase || status) {
      block.appendChild(make("p", "live-status", chase || status));
    }
    if (card && card.toss) {
      block.appendChild(make("p", "live-toss", card.toss));
    }
    if (card && card.innings.length) {
      block.appendChild(renderScorecard(match, card));
    }
    return block;
  }

  function rerenderLive() {
    if (liveView) {
      renderLive(liveView.candidates, liveView.payload, liveView.failed, lastCards);
    }
  }

  function renderLive(candidates, payload, failed, cards) {
    liveView = { candidates: candidates, payload: payload, failed: failed };
    var focused = document.activeElement && document.activeElement.getAttribute &&
      document.activeElement.getAttribute("data-tab");
    var now = Date.now();
    var liveById = {};
    if (payload) {
      payload.matches.forEach(function (live) {
        liveById[live.id] = live;
      });
    }
    clear(liveContent);
    candidates.forEach(function (match) {
      liveContent.appendChild(renderLiveMatch(match, liveById[match.id] || null, now, cards[match.id] || null));
    });
    if (failed) {
      liveContent.appendChild(make("p", "updated", payload ?
        "Couldn't refresh live scores — showing the last check." :
        "Live scores are unavailable right now."));
    }
    livePanel.hidden = false;
    if (focused) {
      var again = liveContent.querySelector('[data-tab="' + focused + '"]');
      if (again) {
        again.focus();
      }
    }
  }

  // Per-match scorecards for matches that have a score; a failed card keeps
  // the last good one and never fails the panel.
  function loadCards(candidates, payload) {
    var scored = {};
    payload.matches.forEach(function (live) {
      if (hasScore(live)) {
        scored[live.id] = true;
      }
    });
    return Promise.all(candidates.filter(function (match) {
      return scored[match.id];
    }).map(function (match) {
      return fetch(LIVE_URL + "/" + encodeURIComponent(match.id), { cache: "no-store" }).then(function (response) {
        if (!response.ok) {
          throw new Error("HTTP " + response.status);
        }
        return response.json();
      }).then(function (card) {
        if (card && Array.isArray(card.innings) && card.team1 && card.squad) {
          card.commentary = mergeCommentary(card.commentary || [],
            lastCards[match.id] && lastCards[match.id].commentary);
          lastCards[match.id] = card;
        }
      }).catch(function () {});
    }));
  }

  function pollLive() {
    clearTimeout(liveTimer);
    liveTimer = null;
    if (!LIVE_URL || !currentData || document.visibilityState === "hidden") {
      return;
    }
    liveTimer = setTimeout(pollLive, LIVE_POLL_MS);
    var candidates = liveCandidates(Date.now());
    if (candidates.length === 0) {
      livePanel.hidden = true;
      return;
    }
    fetch(LIVE_URL, { cache: "no-store" }).then(function (response) {
      if (!response.ok) {
        throw new Error("HTTP " + response.status);
      }
      return response.json();
    }).then(function (payload) {
      if (!payload || !Array.isArray(payload.matches)) {
        throw new Error("bad live payload");
      }
      lastLive = payload;
      renderLive(candidates, payload, false, lastCards);
      return loadCards(candidates, payload).then(function () {
        renderLive(candidates, payload, false, lastCards);
      });
    }).catch(function () {
      renderLive(candidates, lastLive, true, lastCards);
    });
  }

  function showLoading() {
    main.setAttribute("aria-busy", "true");
    refreshNote.hidden = true;
    setMessage(standingsContent, "Loading…");
    setMessage(statsContent, "Loading…");
    setMessage(scheduleContent, "Loading…");
    clear(calendarStatus);
    calendarStatus.appendChild(make("p", null, "Loading teams…"));
    calendarList.querySelectorAll(".team-row").forEach(function (row) {
      row.remove();
    });
  }

  function renderReady() {
    main.setAttribute("aria-busy", "false");
    refreshNote.hidden = true;
    renderStandings();
    renderStats();
    renderSchedule();
    renderCalendar();
    pollLive();
  }

  function renderError() {
    main.setAttribute("aria-busy", "false");
    refreshNote.hidden = true;
    renderErrorBlock(standingsContent);
    renderErrorBlock(statsContent);
    renderErrorBlock(scheduleContent);
    clear(calendarStatus);
    calendarStatus.appendChild(make("p", null, "Team calendars unavailable until data loads"));
    calendarStatus.appendChild(retryButton());
    calendarList.querySelectorAll(".team-row").forEach(function (row) {
      row.remove();
    });
  }

  function validateData(data) {
    schemaMismatch = false;
    if (!data || typeof data !== "object") {
      throw new Error("missing data");
    }
    if (data.schema_version !== 1) {
      schemaMismatch = true;
      throw new Error("schema version");
    }
    if (!data.season || typeof data.updated_at !== "string" ||
        !Array.isArray(data.teams) || !Array.isArray(data.standings) ||
        !Array.isArray(data.matches)) {
      throw new Error("missing keys");
    }
  }

  function loadData(refresh) {
    if (!refresh) {
      currentData = null;
      schemaMismatch = false;
      showLoading();
    }
    return fetch(DATA_URL, { cache: "no-cache" }).then(function (response) {
      if (!response.ok) {
        throw new Error("HTTP " + response.status);
      }
      return response.json();
    }).then(function (data) {
      validateData(data);
      currentData = data;
      renderReady();
    }).catch(function () {
      if (currentData) {
        announce("Couldn't refresh — showing data from " + formatUpdatedAt(currentData.updated_at));
        refreshNote.textContent = "Couldn't refresh — showing data from " +
          formatUpdatedAt(currentData.updated_at);
        refreshNote.hidden = false;
        main.setAttribute("aria-busy", "false");
      } else {
        currentData = null;
        renderError();
      }
    });
  }

  function initTheme() {
    var initial = document.documentElement.getAttribute("data-theme");
    var theme = initial === "dark" ? "dark" : "light";
    document.documentElement.setAttribute("data-theme", theme);
    themeToggle.setAttribute("aria-pressed", theme === "dark" ? "true" : "false");

    themeToggle.addEventListener("click", function () {
      var current = document.documentElement.getAttribute("data-theme");
      var next = current === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", next);
      themeToggle.setAttribute("aria-pressed", next === "dark" ? "true" : "false");
      try {
        localStorage.setItem("npl-theme", next);
      } catch (e) {
        /* storage unavailable: session-only toggle still works */
      }
    });

    if (window.matchMedia) {
      var mq = window.matchMedia("(prefers-color-scheme: dark)");
      var onChange = function (event) {
        var stored = null;
        try {
          stored = localStorage.getItem("npl-theme");
        } catch (e) {
          stored = null;
        }
        if (stored !== "light" && stored !== "dark") {
          document.documentElement.setAttribute("data-theme", event.matches ? "dark" : "light");
          themeToggle.setAttribute("aria-pressed", event.matches ? "true" : "false");
        }
      };
      if (mq.addEventListener) {
        mq.addEventListener("change", onChange);
      } else if (mq.addListener) {
        mq.addListener(onChange);
      }
    }
  }

  calendarList.addEventListener("click", function (event) {
    var button = event.target.closest(".copy");
    if (!button || !calendarList.contains(button)) {
      return;
    }
    copyUrl(button.dataset.url, button);
  });

  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "hidden") {
      lastHiddenAt = Date.now();
    } else if (document.visibilityState === "visible") {
      if (lastHiddenAt !== null && Date.now() - lastHiddenAt > 5 * 60 * 1000) {
        loadData(true);
      } else {
        pollLive();
      }
    }
  });

  initTheme();
  updateStaticAllMatchesRow();
  loadData(false);
})();
