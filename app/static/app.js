/* CHKT web app behaviours: inline delete confirm, repeat/location form
   panels, PWA + push registration, and the in-page talking alert loop. */
(function () {
  "use strict";

  var csrf = document.body.dataset.csrf || "";

  /* ---- Inline delete confirm: button arms red, second click submits. ---- */
  document.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-confirm]");
    if (!btn) return;
    if (btn.dataset.armed !== "1") {
      e.preventDefault();
      btn.dataset.armed = "1";
      btn.classList.add("danger-armed");
      setTimeout(function () {
        btn.dataset.armed = "";
        btn.classList.remove("danger-armed");
      }, 4000);
    }
  });

  /* Nag interval reveals its give-up-after control (wizard and edit form). */
  document.querySelectorAll("[data-nag-select]").forEach(function (select) {
    select.addEventListener("change", function () {
      var stop = select.closest("form").querySelector("[data-nag-stop]");
      if (stop) stop.hidden = select.value === "0";
    });
  });

  /* ---- Edit form: show only the controls for the chosen repeat kind. ---- */
  var repeatSelect = document.querySelector("[data-repeat-select]");
  function syncRepeatPanels() {
    document.querySelectorAll("[data-repeat-panel]").forEach(function (panel) {
      panel.hidden = panel.dataset.repeatPanel !== repeatSelect.value;
    });
  }
  if (repeatSelect) {
    repeatSelect.addEventListener("change", syncRepeatPanels);
    syncRepeatPanels();
  }

  var locSelect = document.querySelector("[data-loc-select]");
  function syncLocPanel() {
    var panel = document.querySelector("[data-loc-panel]");
    if (panel) panel.hidden = locSelect.value === "NONE";
  }
  if (locSelect) {
    locSelect.addEventListener("change", syncLocPanel);
    syncLocPanel();
  }

  var useLocation = document.querySelector("[data-use-location]");
  if (useLocation) {
    useLocation.addEventListener("click", function () {
      if (!navigator.geolocation) return;
      navigator.geolocation.getCurrentPosition(function (pos) {
        document.getElementById("f-lat").value = pos.coords.latitude.toFixed(6);
        document.getElementById("f-lon").value = pos.coords.longitude.toFixed(6);
      });
    });
  }

  /* ---- Voice add: same structured phrases as the app's record widget.
     ---- Runs entirely in the browser; nothing is sent anywhere until Save. */
  (function () {
    var btn = document.getElementById("voice-add");
    if (!btn) return;
    var SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) {
      btn.disabled = true;
      btn.title = "Voice input needs a browser with speech recognition (Chrome or Edge).";
      return;
    }

    function addDays(d, n) { var r = new Date(d); r.setDate(r.getDate() + n); return r; }
    function withTime(d, h, m) { var r = new Date(d); r.setHours(h, m, 0, 0); return r; }
    function nextWeekday(now, targetDow) {
      var diff = (targetDow - now.getDay() + 7) % 7;
      return addDays(now, diff === 0 ? 7 : diff);
    }
    function extractTitle(raw) {
      var t = raw.replace(/^to /, "").trim().replace(/\.+$/, "");
      return t || null;
    }

    // Mirrors org.chkt.app.domain.PhraseParser exactly: same shapes, same
    // "next occurrence" rule for a bare hour like "at 10".
    function parsePhrase(rawInput, now) {
      var raw = rawInput.trim().toLowerCase();
      if (raw.indexOf("remind me") === 0) raw = raw.slice(9).trim();
      if (!raw) return null;

      var repeatKind = "NONE", weekday = null, date = null, time = null, ambiguousHour = false, m;
      var DOW = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"];

      if ((m = /^every (day|morning|evening|week)\b/.exec(raw))) {
        repeatKind = m[1] === "week" ? "WEEKLY" : "DAILY";
        if (repeatKind === "WEEKLY") weekday = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"][now.getDay()];
        raw = raw.slice(m[0].length).trim();
      }

      if ((m = /^tomorrow\b/.exec(raw))) {
        date = addDays(now, 1);
        raw = raw.slice(m[0].length).trim();
      }
      if (!date && (m = /^on (monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b/.exec(raw))) {
        date = nextWeekday(now, DOW.indexOf(m[1]));
        raw = raw.slice(m[0].length).trim();
      }

      if ((m = /^in (\d+) (minute|minutes|hour|hours|day|days)\b/.exec(raw))) {
        var n = parseInt(m[1], 10);
        var due = new Date(now);
        if (m[2].indexOf("minute") === 0) due.setMinutes(due.getMinutes() + n);
        else if (m[2].indexOf("hour") === 0) due.setHours(due.getHours() + n);
        else due.setDate(due.getDate() + n);
        due.setSeconds(0, 0);
        var titleIn = extractTitle(raw.slice(m[0].length).trim());
        return titleIn ? { title: titleIn, dueAt: due, repeatKind: "NONE" } : null;
      }

      if ((m = /^at (\d{1,2})(?::(\d{2}))?\s*(am|pm|o'?clock)?\b/.exec(raw))) {
        var hour = parseInt(m[1], 10);
        var minute = m[2] ? parseInt(m[2], 10) : 0;
        if (m[3] === "pm") { if (hour < 12) hour += 12; }
        else if (m[3] === "am") { if (hour === 12) hour = 0; }
        else { ambiguousHour = hour >= 1 && hour <= 12; }
        if (hour < 0 || hour > 23 || minute < 0 || minute > 59) return null;
        time = { hour: hour % 24, minute: minute };
        raw = raw.slice(m[0].length).trim();
      }

      if (!date && (m = /^on (monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b/.exec(raw))) {
        date = nextWeekday(now, DOW.indexOf(m[1]));
        raw = raw.slice(m[0].length).trim();
      }
      if (!date && (m = /^tomorrow\b/.exec(raw))) {
        date = addDays(now, 1);
        raw = raw.slice(m[0].length).trim();
      }

      var title = extractTitle(raw);
      if (!title || !time) return null;

      if (ambiguousHour && !date) {
        var base = time.hour % 12;
        for (var dayOffset = 0; dayOffset <= 1; dayOffset++) {
          var candidates = [base, base + 12];
          for (var ci = 0; ci < candidates.length; ci++) {
            var c = withTime(addDays(now, dayOffset), candidates[ci] % 24, time.minute);
            if (c > now) return { title: title, dueAt: c, repeatKind: repeatKind, weekday: weekday };
          }
        }
        return null;
      }

      var due2 = withTime(date || now, time.hour, time.minute);
      if (due2 <= now) {
        if (!date) due2 = withTime(addDays(now, 1), time.hour, time.minute);
        else return null;
      }
      return { title: title, dueAt: due2, repeatKind: repeatKind, weekday: weekday };
    }

    function pad(n) { return (n < 10 ? "0" : "") + n; }
    function toLocalInputValue(d) {
      return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()) +
        "T" + pad(d.getHours()) + ":" + pad(d.getMinutes());
    }

    function applyParsed(p) {
      document.getElementById("f-title").value = p.title.charAt(0).toUpperCase() + p.title.slice(1);
      document.getElementById("f-due").value = toLocalInputValue(p.dueAt);
      var repeatSelect = document.querySelector("[data-repeat-select]");
      if (repeatSelect) {
        repeatSelect.value = p.repeatKind;
        repeatSelect.dispatchEvent(new Event("change"));
        if (p.repeatKind === "WEEKLY" && p.weekday) {
          document.querySelectorAll('input[name="weekday"]').forEach(function (cb) {
            cb.checked = cb.value === p.weekday;
          });
        }
      }
    }

    var status = document.getElementById("voice-status");
    var recognizing = false;
    btn.addEventListener("click", function () {
      if (recognizing) return;
      var rec = new SR();
      rec.lang = "en-US";
      rec.interimResults = false;
      rec.maxAlternatives = 1;
      recognizing = true;
      btn.textContent = "Listening…";
      if (status) status.hidden = true;
      rec.onresult = function (e) {
        var text = e.results[0][0].transcript;
        var parsed = parsePhrase(text, new Date());
        if (status) {
          status.hidden = false;
          status.textContent = parsed
            ? "Heard: \"" + text + "\", filled in below, check and save."
            : "Heard: \"" + text + "\", couldn't work out a time. Try \"remind me at 2pm to feed the cat\".";
        }
        if (parsed) applyParsed(parsed);
      };
      rec.onerror = function () {
        if (status) { status.hidden = false; status.textContent = "Didn't catch that, try again."; }
      };
      rec.onend = function () {
        recognizing = false;
        btn.textContent = "Add by voice";
      };
      rec.start();
    });
  })();

  /* ---- Devices page: live "Last sync" so connecting a phone shows up
     ---- without a manual refresh. Polls while the tab is visible. ---- */
  (function () {
    var rows = document.querySelectorAll("[data-device-row]");
    if (!rows.length) return;

    var MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
    function pad(n) { return (n < 10 ? "0" : "") + n; }
    function formatMillis(ms) {
      var d = new Date(ms);
      return pad(d.getDate()) + " " + MONTHS[d.getMonth()] + " " + d.getFullYear() +
        ", " + pad(d.getHours()) + ":" + pad(d.getMinutes());
    }

    function poll() {
      fetch("/devices/status", { headers: { "X-CSRF": csrf } })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (data) {
          if (!data) return;
          var byId = {};
          (data.keys || []).forEach(function (k) { byId[k.id] = k.last_used_at; });
          rows.forEach(function (row) {
            var id = row.dataset.keyId;
            var now = byId[id];
            if (now == null) return;
            var before = row.dataset.lastUsed;
            if (String(now) === before) return;
            row.dataset.lastUsed = now;
            var cell = row.querySelector("[data-last-sync]");
            if (!cell) return;
            cell.textContent = formatMillis(now);
            // A device just connected, including its very first time (was
            // "never"): a quick flash of the same green tone as a confirmed
            // connection, then it settles back to normal.
            cell.classList.add("just-synced");
            setTimeout(function () { cell.classList.remove("just-synced"); }, 2500);
          });
        })
        .catch(function () { /* offline; try again next tick */ });
    }
    setInterval(function () {
      if (document.visibilityState === "visible") poll();
    }, 4000);
  })();

  /* ---- PWA: register the service worker, offer push. ---- */
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/static/sw.js").then(function (reg) {
      if (!("PushManager" in window) || Notification.permission === "denied") return;
      Notification.requestPermission().then(function (permission) {
        if (permission !== "granted") return;
        fetch("/web/vapid").then(function (r) { return r.json(); }).then(function (data) {
          if (!data.key) return;
          reg.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: urlB64ToUint8Array(data.key)
          }).then(function (sub) {
            fetch("/web/subscribe", {
              method: "POST",
              headers: { "Content-Type": "application/json", "X-CSRF": csrf },
              body: JSON.stringify(sub.toJSON())
            });
          }).catch(function () { /* push unavailable; polling still works */ });
        });
      });
    }).catch(function () { /* no PWA support; the site still works */ });
  }

  function urlB64ToUint8Array(base64String) {
    var padding = "=".repeat((4 - (base64String.length % 4)) % 4);
    var base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
    var raw = atob(base64);
    var arr = new Uint8Array(raw.length);
    for (var i = 0; i < raw.length; i++) arr[i] = raw.charCodeAt(i);
    return arr;
  }

  /* ---- The talking part: poll for fired reminders, tone + speak + overlay. ---- */
  var overlay = document.getElementById("alert-overlay");
  if (!overlay) return;

  var since = Date.now();
  var queue = [];
  var current = null;

  function poll() {
    fetch("/web/fired?since=" + since, { headers: { "X-CSRF": csrf } })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (!data) return;
        since = data.now;
        (data.fired || []).forEach(function (f) { queue.push(f); });
        if (!current) showNext();
      })
      .catch(function () { /* offline; try again next tick */ });
  }
  setInterval(poll, 20000);

  function showNext() {
    current = queue.shift() || null;
    if (!current) { overlay.classList.remove("open"); return; }
    document.getElementById("alert-title").textContent = current.title;
    document.getElementById("alert-notes").textContent = current.notes || "";
    buildSnoozeButtons();
    overlay.classList.add("open");
    announce(current);
  }

  function announce(item) {
    // Quiet hours: the reminder still appears (Done/Snooze work as normal),
    // it just doesn't ring or speak, matching the app's silent channel.
    if (item.quiet) return;
    // Vibration API is mobile-browser-only; no-ops harmlessly elsewhere.
    if (item.vibrate && navigator.vibrate) navigator.vibrate([400, 250, 400, 250, 400]);
    var mode = item.alert_mode || "NOTIFY_AND_SPEAK";
    var speak = mode === "NOTIFY_AND_SPEAK" || mode === "SPEAK_ONLY";
    if (!speak || !("speechSynthesis" in window)) return;
    // Notes show in the overlay but aren't spoken — matches the app.
    speechSynthesis.speak(new SpeechSynthesisUtterance(item.title));
  }

  function act(path, body) {
    var form = new FormData();
    form.append("csrf", csrf);
    Object.keys(body || {}).forEach(function (k) { form.append(k, body[k]); });
    return fetch(path, { method: "POST", body: form });
  }

  document.getElementById("alert-done").addEventListener("click", function () {
    if (current) act("/reminder/" + current.reminder_id + "/done");
    speechSynthesis && speechSynthesis.cancel();
    showNext();
  });

  function buildSnoozeButtons() {
    var wrap = document.getElementById("alert-snoozes");
    wrap.textContent = "";
    [[10, "10 min"], [30, "30 min"], [60, "1 hr"], [180, "3 hrs"], [720, "12 hrs"], [1440, "1 day"]]
      .forEach(function (pair) {
        var b = document.createElement("button");
        b.type = "button";
        b.textContent = pair[1];
        b.addEventListener("click", function () {
          if (current) act("/reminder/" + current.reminder_id + "/snooze", { minutes: pair[0] });
          speechSynthesis && speechSynthesis.cancel();
          showNext();
        });
        wrap.appendChild(b);
      });
  }
})();
