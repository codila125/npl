/* Nepal Premier League 2026 — static site behaviour. */
"use strict";

(function () {
  var NPT_OFFSET_MS = (5 * 60 + 45) * 60 * 1000;
  var MATCH_WINDOW_MS = 4 * 60 * 60 * 1000;
  var DATA_URL = "data/npl.json";
  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  var DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

  var main = document.getElementById("main");
  var liveRegion = document.getElementById("live-region");
  var refreshNote = document.getElementById("refresh-note");
  var standingsContent = document.getElementById("standings-content");
  var scheduleContent = document.getElementById("schedule-content");
  var calendarStatus = document.getElementById("calendar-status");
  var calendarList = document.getElementById("calendar-list");
  var themeToggle = document.getElementById("theme-toggle");

  var currentData = null;
  var schemaMismatch = false;
  var lastHiddenAt = null;

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

    var updated = make("p", "updated");
    var time = make("time");
    time.dateTime = data.updated_at;
    time.textContent = formatUpdatedAt(data.updated_at) + " NPT";
    updated.append("Data updated ", time);

    clear(standingsContent);
    standingsContent.appendChild(wrap);
    standingsContent.appendChild(updated);
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

  function showLoading() {
    main.setAttribute("aria-busy", "true");
    refreshNote.hidden = true;
    setMessage(standingsContent, "Loading…");
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
    renderSchedule();
    renderCalendar();
  }

  function renderError() {
    main.setAttribute("aria-busy", "false");
    refreshNote.hidden = true;
    renderErrorBlock(standingsContent);
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
      }
    }
  });

  initTheme();
  updateStaticAllMatchesRow();
  loadData(false);
})();
