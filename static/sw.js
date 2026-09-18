const CACHE = 'delistock-v2';
const ASSETS = ['/', '/static/manifest.json'];
self.addEventListener('install', e => { e.waitUntil(caches.open(CACHE).then(c => c.addAll(ASSETS))); self.skipWaiting(); });
self.addEventListener('activate', e => { e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))); self.clients.claim(); });
self.addEventListener('fetch', e => {
  if (e.request.url.includes('/api/')) { e.respondWith(fetch(e.request).catch(() => new Response(JSON.stringify({ok:false}), {headers:{'Content-Type':'application/json'}}))); return; }
  e.respondWith(fetch(e.request).then(r => { const rc=r.clone(); caches.open(CACHE).then(c=>c.put(e.request,rc)); return r; }).catch(() => caches.match(e.request)));
});
