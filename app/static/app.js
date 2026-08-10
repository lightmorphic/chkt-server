/* Chkt web app behaviours: inline delete confirm, repeat/location form
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
    var mode = item.alert_mode || "RING_AND_SPEAK";
    var ring = mode === "RING_AND_SPEAK" || mode === "RING_ONLY";
    var speak = mode === "RING_AND_SPEAK" || mode === "SPEAK_ONLY";
    var speakNow = function () {
      if (!speak || !("speechSynthesis" in window)) return;
      var text = item.title + (item.notes ? ". " + item.notes : "");
      var say = function () {
        var u = new SpeechSynthesisUtterance(text);
        speechSynthesis.speak(u);
      };
      if (item.pre_tone) { tone(660, 0.4, say); } else { say(); }
    };
    if (ring) { tone(880, 1.2, speakNow); } else { speakNow(); }
  }

  function tone(freq, seconds, done) {
    try {
      var ctx = new (window.AudioContext || window.webkitAudioContext)();
      var osc = ctx.createOscillator();
      var gain = ctx.createGain();
      osc.frequency.value = freq;
      gain.gain.setValueAtTime(0.25, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + seconds);
      osc.connect(gain).connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + seconds);
      osc.onended = function () { ctx.close(); if (done) done(); };
    } catch (e) {
      if (done) done();
    }
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
