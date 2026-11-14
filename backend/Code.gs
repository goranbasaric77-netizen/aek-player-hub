/**
 * AEK Player Hub · zadnji deo (Google Apps Script + Google Sheet)
 *
 * Jedna tabela, pet listova: Players, Plan, Results, Log, Tokens (+ Today za staff pregled).
 * App (index.html) salje POST zahteve kao text/plain JSON, ovaj skript odgovara JSON-om.
 *
 * Prvi put: pokreni funkciju setup() iz editora (Run > setup). Ona pravi listove i zaglavlja
 * i upisuje probne igrace. Posle toga: Deploy > New deployment > Web app,
 * Execute as: Me, Who has access: Anyone. Kopiraj URL web app-a u config.js u hub folderu.
 *
 * Verzija: 1.0 (04.11.2026)
 */

var VERSION = "1.6";
/* ID tabele (deo URL-a izmedju /d/ i /edit). Prazan string = skript vezan za tabelu (Extensions > Apps Script). */
var SHEET_ID = "16DFYiEveVmyC72g3lR94-m7R0yM2u7fYh40rrjKldsw";
function book() { return SHEET_ID ? SpreadsheetApp.openById(SHEET_ID) : SpreadsheetApp.getActiveSpreadsheet(); }
function say(msg) { Logger.log(msg); try { SpreadsheetApp.getUi().alert(msg); } catch (e) {} }
var SHEETS = {
  Players: ["id", "name", "pin", "role", "active"],
  Plan: ["date", "player", "day_type", "mode_label", "sub", "focus", "pitch_td", "pitch_hsr", "pitch_spr", "cap_pct", "speed_goal", "speed_work",
         "act_time", "act_group", "act_indiv", "mobility_json", "gym_json", "ref_td", "ref_hsr", "ref_spr", "ref_vmax", "speed_days", "last_speed", "last_min",
         "extra_json"],
  Results: ["date", "player", "td", "hsr", "spr", "vmax"],
  Log: ["ts", "date", "player", "type", "key", "value", "device"],
  Tokens: ["token", "player", "created"],
  Today: ["player", "name", "opened", "last_open", "checkin_at", "readiness", "sleep_h", "sore", "note", "gym_sets_done", "mobility_done", "focus_read"]
};

/* ------------------------------------------------------------------ setup */

function setup() {
  var ss = book();
  try { ss.setSpreadsheetTimeZone("Europe/Athens"); } catch (e) {}
  Object.keys(SHEETS).forEach(function (name) {
    var sh = ss.getSheetByName(name) || ss.insertSheet(name);
    if (sh.getLastRow() === 0) {
      sh.appendRow(SHEETS[name]);
      sh.getRange(1, 1, 1, SHEETS[name].length).setFontWeight("bold");
      sh.setFrozenRows(1);
    }
    if (name === "Plan") sh.getRange("M:M").setNumberFormat("@");
    if (name === "Log" || name === "Tokens") sh.getRange("A:A").setNumberFormat("@");
  });
  var pl = ss.getSheetByName("Players");
  if (pl.getLastRow() === 1) {
    // Probni spisak. PIN-ove promeni ovde u tabeli, app ih cita odavde.
    [
      ["__staff", "Performance staff", "2468", "staff", 1],
      ["koita", "Abubakary Koita", "1111", "player", 1],
      ["pilios", "Stavros Pilios", "2222", "player", 1],
      ["majer", "Lovro Majer", "3333", "player", 1],
      ["gacinovic", "Mijat Gacinovic", "4444", "player", 1]
    ].forEach(function (r) { pl.appendRow(r); });
  }
  var first = ss.getSheets()[0];
  if (first.getName() !== "Players" && first.getLastRow() === 0) ss.deleteSheet(first);
  say("AEK Player Hub: listovi su spremni. Sledeci korak je Deploy > New deployment > Web app.");
}

function onOpen() {
  if (SHEET_ID) return; // meni postoji samo kad je skript vezan za tabelu
  SpreadsheetApp.getUi().createMenu("AEK Hub")
    .addItem("Osvezi Today (staff pregled)", "refreshToday")
    .addItem("Setup (prvi put)", "setup")
    .addToUi();
}

/* ------------------------------------------------------------------ http */

function doGet(e) {
  return out({ ok: true, service: "aek-player-hub", version: VERSION, time: new Date().toISOString() });
}

function doPost(e) {
  var lock = LockService.getScriptLock();
  try {
    lock.waitLock(20000);
    var body = {};
    try { body = JSON.parse(e.postData.contents || "{}"); } catch (err) { return out({ ok: false, error: "bad_json" }); }
    var a = body.action;
    if (a === "ping") return out({ ok: true, version: VERSION });
    if (a === "auth") return out(auth(body));
    if (a === "feed") return out(feed(body));
    var who = whoIs(body.token);
    if (!who) return out({ ok: false, error: "auth" });
    if (a === "today") return out(today(who, body));
    if (a === "log") return out(logEvents(who, body));
    if (a === "team") return out(team(who, body));
    if (a === "history") return out(history(who, body));
    return out({ ok: false, error: "unknown_action" });
  } catch (err) {
    return out({ ok: false, error: String(err && err.message || err) });
  } finally {
    try { lock.releaseLock(); } catch (e2) {}
  }
}

function out(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}

/* ------------------------------------------------------------------ helpers */

function sheet(name) {
  var ss = book();
  return ss.getSheetByName(name) || ss.insertSheet(name);
}

function rows(name) {
  var sh = sheet(name);
  var n = sh.getLastRow();
  if (n < 2) return [];
  var head = SHEETS[name];
  var vals = sh.getRange(2, 1, n - 1, head.length).getValues();
  return vals.map(function (r) {
    var o = {};
    head.forEach(function (h, i) { o[h] = r[i]; });
    return o;
  });
}

function dayKey(d) {
  return Utilities.formatDate(d || new Date(), "Europe/Athens", "yyyy-MM-dd");
}

function cellDate(v) {
  if (v instanceof Date) return dayKey(v);
  return String(v || "").slice(0, 10);
}

function num(v) {
  if (v === "" || v === null || v === undefined) return null;
  var n = Number(v);
  return isNaN(n) ? null : n;
}

/* Sheets turns "10:30" into a time value; give it back as HH:mm text. */
function timeStr(v) {
  if (v === "" || v === null || v === undefined) return "";
  if (v instanceof Date) return Utilities.formatDate(v, book().getSpreadsheetTimeZone(), "HH:mm");
  var m = String(v).match(/(\d{1,2}):(\d{2})/);
  return m ? (m[1].length === 1 ? "0" + m[1] : m[1]) + ":" + m[2] : String(v);
}

function jsonOrNull(v) {
  if (!v) return null;
  try { return JSON.parse(v); } catch (e) { return null; }
}

/* ------------------------------------------------------------------ auth */

function auth(body) {
  var id = String(body.player || "").trim();
  var pin = String(body.pin || "").trim();
  var p = rows("Players").filter(function (r) { return String(r.id) === id && String(r.active) !== "0" && r.active !== false; })[0];
  if (!p) return { ok: false, error: "player" };
  if (String(p.pin) !== pin) return { ok: false, error: "pin" };
  var token = Utilities.getUuid();
  sheet("Tokens").appendRow([token, id, new Date().toISOString()]);
  return { ok: true, token: token, player: id, name: p.name, role: p.role || "player" };
}

function whoIs(token) {
  if (!token) return null;
  var t = rows("Tokens").filter(function (r) { return r.token === token; })[0];
  if (!t) return null;
  var p = rows("Players").filter(function (r) { return String(r.id) === String(t.player); })[0];
  if (!p) return null;
  return { id: String(p.id), name: p.name, role: p.role || "player" };
}

/* ------------------------------------------------------------------ today (player) */

function today(who, body) {
  var date = String(body.date || dayKey());
  var plan = rows("Plan").filter(function (r) { return cellDate(r.date) === date && String(r.player) === who.id; }).pop() || null;
  var result = rows("Results").filter(function (r) { return cellDate(r.date) === date && String(r.player) === who.id; }).pop() || null;
  var log = rows("Log").filter(function (r) { return cellDate(r.date) === date; });
  var mine = log.filter(function (r) { return String(r.player) === who.id; });
  var checkedIn = {};
  log.forEach(function (r) { if (r.type === "checkin") checkedIn[r.player] = 1; });
  var nPlayers = rows("Players").filter(function (r) { return r.role !== "staff" && String(r.active) !== "0"; }).length;
  return {
    ok: true, date: date, player: who.id, name: who.name,
    plan: plan ? planOut(plan) : null,
    result: result ? { td: num(result.td), hsr: num(result.hsr), spr: num(result.spr), vmax: num(result.vmax) } : null,
    state: stateFrom(mine),
    team: { total: nPlayers, checkedIn: Object.keys(checkedIn).length }
  };
}

function planOut(r) {
  return {
    dayType: r.day_type || "", modeLabel: r.mode_label || "", sub: r.sub || "", focus: r.focus || "",
    pitch: num(r.pitch_td) !== null ? { td: num(r.pitch_td), hsr: num(r.pitch_hsr), spr: num(r.pitch_spr), capPct: num(r.cap_pct), speedGoal: num(r.speed_goal), speedWork: r.speed_work || "" } : null,
    activation: { time: timeStr(r.act_time), group: r.act_group || "", indiv: String(r.act_indiv || "").split(";").map(function (s) { return s.trim(); }).filter(Boolean) },
    mobility: jsonOrNull(r.mobility_json), gym: jsonOrNull(r.gym_json),
    ref: { td: num(r.ref_td), hsr: num(r.ref_hsr), spr: num(r.ref_spr), vmax: num(r.ref_vmax) },
    speedDays: num(r.speed_days), lastSpeed: num(r.last_speed), lastMin: num(r.last_min),
    extra: jsonOrNull(r.extra_json)
  };
}

/* Rebuild a player's state for one day from their log rows (last value wins). */
function stateFrom(mine) {
  var st = { checkin: null, gym: {}, mob: {}, ack: false, opened: false, lastOpen: null, note: "", rpe: null };
  mine.sort(function (a, b) { return new Date(a.ts) - new Date(b.ts); });
  mine.forEach(function (r) {
    var t = r.type;
    if (t === "open") { st.opened = true; st.lastOpen = hhmm(r.ts); }
    else if (t === "checkin") { st.checkin = jsonOrNull(r.value); st.opened = true; }
    else if (t === "gym") { st.gym[String(r.key)] = Number(r.value) || 0; }
    else if (t === "mob") { st.mob[String(r.key)] = Number(r.value) ? 1 : 0; }
    else if (t === "ack") { st.ack = !!Number(r.value); }
    else if (t === "note") { st.note = String(r.value || ""); }
    else if (t === "rpe") { st.rpe = jsonOrNull(r.value); }   /* 14.11.2026: session effort 1-10 */
  });
  return st;
}

function hhmm(ts) {
  var d = ts instanceof Date ? ts : new Date(String(ts));
  if (isNaN(d.getTime())) return "";
  return Utilities.formatDate(d, "Europe/Athens", "HH:mm");
}

/* ------------------------------------------------------------------ log */

function logEvents(who, body) {
  var ev = body.events || [];
  if (!ev.length) return { ok: true, n: 0 };
  var sh = sheet("Log");
  var device = String(body.device || "").slice(0, 60);
  var out = ev.slice(0, 200).map(function (e) {
    return [new Date(e.ts || Date.now()).toISOString(), String(e.date || dayKey()), who.id, String(e.type || ""), String(e.key === undefined ? "" : e.key),
            typeof e.value === "object" ? JSON.stringify(e.value) : String(e.value === undefined ? "" : e.value), device];
  });
  sh.getRange(sh.getLastRow() + 1, 1, out.length, SHEETS.Log.length).setValues(out);
  return { ok: true, n: out.length };
}

/* ------------------------------------------------------------------ team (staff) */

function team(who, body) {
  if (who.role !== "staff") return { ok: false, error: "staff_only" };
  var date = String(body.date || dayKey());
  var players = rows("Players").filter(function (r) { return r.role !== "staff" && String(r.active) !== "0"; });
  var log = rows("Log").filter(function (r) { return cellDate(r.date) === date; });
  var plans = {};
  rows("Plan").filter(function (r) { return cellDate(r.date) === date; }).forEach(function (r) { plans[String(r.player)] = planOut(r); });
  var results = {};
  rows("Results").filter(function (r) { return cellDate(r.date) === date; }).forEach(function (r) { results[String(r.player)] = { td: num(r.td), hsr: num(r.hsr), spr: num(r.spr), vmax: num(r.vmax) }; });
  var out = players.map(function (p) {
    var mine = log.filter(function (r) { return String(r.player) === String(p.id); });
    return { player: String(p.id), name: p.name, state: stateFrom(mine), plan: plans[String(p.id)] || null, result: results[String(p.id)] || null };
  });
  return { ok: true, date: date, rows: out };
}

/* Staff sheet "Today": one row per player, refreshed from the menu. */
function refreshToday() {
  var date = dayKey();
  var players = rows("Players").filter(function (r) { return r.role !== "staff" && String(r.active) !== "0"; });
  var log = rows("Log").filter(function (r) { return cellDate(r.date) === date; });
  var sh = sheet("Today");
  sh.clearContents();
  sh.appendRow(SHEETS.Today);
  sh.getRange(1, 1, 1, SHEETS.Today.length).setFontWeight("bold");
  var lines = players.map(function (p) {
    var st = stateFrom(log.filter(function (r) { return String(r.player) === String(p.id); }));
    var c = st.checkin || {};
    var gymSets = Object.keys(st.gym).reduce(function (a, k) { return a + (st.gym[k] || 0); }, 0);
    var mob = Object.keys(st.mob).filter(function (k) { return st.mob[k]; }).length;
    return [p.id, p.name, st.opened ? "yes" : "no", st.lastOpen || "", c.at || "", c.at ? readiness(c) : "", c.hours || "",
            (c.zones || []).join(", "), c.note || "", gymSets, mob, st.ack ? "yes" : ""];
  });
  if (lines.length) sh.getRange(2, 1, lines.length, SHEETS.Today.length).setValues(lines);
  say("Today osvezen za " + date + " (" + lines.length + " igraca).");
}

/* Same formula as in the app: five 1-5 scales (80%) + sleep hours (20%). */
function readiness(c) {
  var keys = ["sleepq", "fatigue", "soreness", "stress", "mood"];
  var s = keys.reduce(function (a, k) { return a + (Number(c[k]) || 3); }, 0);
  var sleepAdj = Math.max(0, Math.min(1, ((Number(c.hours) || 0) - 5) / 3));
  return Math.round(((s - 5) / 20 * 0.8 + sleepAdj * 0.2) * 100);
}

/* ------------------------------------------------------------------ feed (bridge from GPS 2.5) */

function feed(body) {
  var staff = rows("Players").filter(function (r) { return r.role === "staff"; })[0];
  if (!staff || String(body.key || "") !== String(staff.pin)) return { ok: false, error: "key" };
  ensureHeaders("Plan");
  var nPlan = upsert("Plan", body.plan || [], ["date", "player"]);
  var nRes = upsert("Results", body.results || [], ["date", "player"]);
  return { ok: true, plan: nPlan, results: nRes };
}

/* 1.5: new columns (extra_json) are added to the sheet header when the script grows. */
function ensureHeaders(name) {
  var sh = sheet(name), head = SHEETS[name];
  var have = sh.getLastRow() ? sh.getRange(1, 1, 1, Math.max(sh.getLastColumn(), 1)).getValues()[0] : [];
  for (var i = 0; i < head.length; i++) {
    if (String(have[i] || "") !== head[i]) { sh.getRange(1, i + 1).setValue(head[i]).setFontWeight("bold"); }
  }
}

/* Upsert rows (objects keyed by header name) into a sheet by key columns. */
function upsert(name, items, keys) {
  if (!items.length) return 0;
  var sh = sheet(name);
  var head = SHEETS[name];
  var existing = rows(name);
  var index = {};
  existing.forEach(function (r, i) { index[keys.map(function (k) { return k === "date" ? cellDate(r[k]) : String(r[k]); }).join("|")] = i + 2; });
  var appends = [];
  items.forEach(function (it) {
    var line = head.map(function (h) { var v = it[h]; return v === undefined || v === null ? "" : (typeof v === "object" ? JSON.stringify(v) : v); });
    var k = keys.map(function (kk) { return String(it[kk]); }).join("|");
    if (index[k]) sh.getRange(index[k], 1, 1, head.length).setValues([line]);
    else appends.push(line);
  });
  if (appends.length) sh.getRange(sh.getLastRow() + 1, 1, appends.length, head.length).setValues(appends);
  return items.length;
}

/* ------------------------------------------------------------------ morning reminder (OneSignal push) */

var HUB_URL = "https://goranbasaric77-netizen.github.io/aek-player-hub/";

/* Sends the 08:30 reminder to active players who have a plan today and no check-in yet.
   Needs Script Properties ONESIGNAL_APP_ID and ONESIGNAL_KEY (REST API key, never in code). */
function sendMorningReminder() {
  var props = PropertiesService.getScriptProperties();
  var appId = props.getProperty("ONESIGNAL_APP_ID"), key = props.getProperty("ONESIGNAL_KEY");
  if (!appId || !key) { Logger.log("push: ONESIGNAL_APP_ID ili ONESIGNAL_KEY nije podesen"); return; }
  var date = dayKey();
  var planned = {}, done = {};
  rows("Plan").forEach(function (r) { if (cellDate(r.date) === date) planned[String(r.player)] = 1; });
  rows("Log").forEach(function (r) { if (cellDate(r.date) === date && r.type === "checkin") done[String(r.player)] = 1; });
  var ids = rows("Players").filter(function (p) {
    return p.role !== "staff" && String(p.active) !== "0" && planned[String(p.id)] && !done[String(p.id)];
  }).map(function (p) { return String(p.id); });
  if (!ids.length) { Logger.log("push: nikome (nema plana za danas ili su svi uradili check-in)"); return; }
  var res = UrlFetchApp.fetch("https://api.onesignal.com/notifications?c=push", {
    method: "post", contentType: "application/json", muteHttpExceptions: true,
    headers: { Authorization: "Key " + key },
    payload: JSON.stringify({
      app_id: appId, target_channel: "push", include_aliases: { external_id: ids },
      headings: { en: "AEK Player Hub" },
      contents: { en: "Your plan for today is ready. Check in before training." },
      url: HUB_URL
    })
  });
  Logger.log("push " + res.getResponseCode() + " za " + ids.length + " igraca: " + res.getContentText().slice(0, 300));
}

/* Run once from the editor: daily trigger around 08:30 Athens time (Apps Script fires within about 15 minutes). */
function setupReminders() {
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === "sendMorningReminder") ScriptApp.deleteTrigger(t);
  });
  ScriptApp.newTrigger("sendMorningReminder").timeBased().atHour(8).nearMinute(30).everyDays(1)
    .inTimezone("Europe/Athens").create();
  say("Jutarnji podsetnik je zakazan svaki dan oko 08:30 (Atina).");
}

/* ------------------------------------------------------------------ history (Progress tab) */

/* Last N days before `date` for one player: plan, GPS result and the day's state from the log.
   A player gets their own history; staff can ask for any player with body.player. */
function history(who, body) {
  var pid = (who.role === "staff" && body.player) ? String(body.player) : who.id;
  var n = Math.min(Math.max(Number(body.days) || 14, 1), 31);
  var end = String(body.date || dayKey());
  var endDate = Utilities.parseDate(end + " 12:00", "Europe/Athens", "yyyy-MM-dd HH:mm");
  var dates = [], want = {};
  for (var i = n; i >= 1; i--) {
    var d = dayKey(new Date(endDate.getTime() - i * 86400000));
    dates.push(d); want[d] = 1;
  }
  var plans = {}, results = {}, logs = {};
  rows("Plan").forEach(function (r) { var d = cellDate(r.date); if (want[d] && String(r.player) === pid) plans[d] = planOut(r); });
  rows("Results").forEach(function (r) { var d = cellDate(r.date); if (want[d] && String(r.player) === pid) results[d] = { td: num(r.td), hsr: num(r.hsr), spr: num(r.spr), vmax: num(r.vmax) }; });
  rows("Log").forEach(function (r) { var d = cellDate(r.date); if (want[d] && String(r.player) === pid) (logs[d] = logs[d] || []).push(r); });
  return { ok: true, player: pid, days: dates.map(function (d) {
    return { date: d, plan: plans[d] || null, result: results[d] || null, state: stateFrom(logs[d] || []) };
  }) };
}

/* ------------------------------------------------------------------ demo history (pilot preview) */

var DEMO_PLAYERS = ["gacinovic", "majer", "relvas"];
var DEMO_DEVICE = "demo-history";

/* Simulated check-ins, focus reads and gym sets for the pilot players on past days that have a plan.
   Plans and GPS results stay real (from GPS 2.5). Rows are tagged device "demo-history".
   Remove them all with clearDemoHistory() before the real pilot starts. */
function seedDemoHistory() {
  clearDemoHistory();
  var today = dayKey();
  var out = [];
  rows("Plan").forEach(function (r) {
    var pid = String(r.player), d = cellDate(r.date);
    if (DEMO_PLAYERS.indexOf(pid) < 0 || d >= today) return;
    var rnd = seeded(pid + d);
    var off = /day off/i.test(String(r.day_type) + " " + String(r.mode_label));
    var hh = 7, mm = 35 + Math.floor(rnd() * 40);
    if (mm >= 60) { hh = 8; mm -= 60; }
    var at = (hh < 10 ? "0" : "") + hh + ":" + (mm < 10 ? "0" : "") + mm;
    var ts = function (addMin) {
      return Utilities.parseDate(d + " " + at, "Europe/Athens", "yyyy-MM-dd HH:mm").getTime() + (addMin || 0) * 60000;
    };
    var iso = function (addMin) { return new Date(ts(addMin)).toISOString(); };
    if (rnd() < 0.93) out.push([iso(0), d, pid, "open", "today", "", DEMO_DEVICE]);
    if (rnd() < (off ? 0.6 : 0.88)) {
      var sc = function () { var x = rnd(); return x < 0.08 ? 2 : x < 0.35 ? 3 : x < 0.8 ? 4 : 5; };
      var sore = rnd() < 0.12 ? ["L hamstring"] : (rnd() < 0.08 ? ["R calf"] : []);
      var c = { hours: Math.round((6 + rnd() * 3) * 2) / 2, sleepq: sc(), fatigue: sc(), soreness: sore.length ? 2 : sc(), stress: sc(), mood: sc(), zones: sore, note: "", at: at };
      out.push([iso(2), d, pid, "checkin", "", JSON.stringify(c), DEMO_DEVICE]);
    }
    if (!off && rnd() < 0.7) out.push([iso(3), d, pid, "ack", "", "1", DEMO_DEVICE]);
    var g = jsonOrNull(r.gym_json);
    if (g && g.slots && g.slots.length) {
      var full = rnd() < 0.7;
      g.slots.forEach(function (s) {
        (s.ex || []).forEach(function (e, i) {
          var sets = parseInt(e.d, 10) || 0;
          var done = full ? sets : Math.floor(sets * (0.4 + rnd() * 0.6));
          if (done > 0) out.push([iso(240 + i), d, pid, "gym", s.s + i, String(done), DEMO_DEVICE]);
        });
      });
    }
  });
  if (out.length) {
    var sh = sheet("Log");
    sh.getRange(sh.getLastRow() + 1, 1, out.length, SHEETS.Log.length).setValues(out);
  }
  say("Demo istorija: " + out.length + " redova za " + DEMO_PLAYERS.join(", ") + ". Brisanje: clearDemoHistory.");
}

/* Deletes every Log row written by seedDemoHistory (device "demo-history"). Real player rows stay. */
function clearDemoHistory() {
  var sh = sheet("Log");
  var n = sh.getLastRow();
  if (n < 2) return;
  var vals = sh.getRange(2, 1, n - 1, SHEETS.Log.length).getValues();
  var keep = vals.filter(function (r) { return String(r[6]) !== DEMO_DEVICE; });
  if (keep.length === vals.length) return;
  sh.getRange(2, 1, n - 1, SHEETS.Log.length).clearContent();
  if (keep.length) sh.getRange(2, 1, keep.length, SHEETS.Log.length).setValues(keep);
  Logger.log("clearDemoHistory: obrisano " + (vals.length - keep.length) + " demo redova");
}

/* Small deterministic random generator (Park-Miller) so the demo looks the same every time it is seeded. */
function seeded(text) {
  var h = 7;
  for (var i = 0; i < text.length; i++) h = (h * 31 + text.charCodeAt(i)) % 2147483647;
  if (h <= 0) h += 2147483646;
  return function () { h = (h * 48271) % 2147483647; return (h - 1) / 2147483646; };
}
