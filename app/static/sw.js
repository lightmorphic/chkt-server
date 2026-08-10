/* Chkt service worker: shows pushed reminder notifications and opens the app. */
self.addEventListener("push", function (event) {
  var data = {};
  try { data = event.data.json(); } catch (e) { /* fall through */ }
  event.waitUntil(
    self.registration.showNotification(data.title || "Reminder", {
      body: data.body || "",
      icon: "/static/icon-192.png",
      badge: "/static/icon-192.png",
      tag: data.reminderId || "chkt",
    })
  );
});

self.addEventListener("notificationclick", function (event) {
  event.notification.close();
  event.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true }).then(function (list) {
      for (var i = 0; i < list.length; i++) {
        if ("focus" in list[i]) return list[i].focus();
      }
      return clients.openWindow("/");
    })
  );
});
