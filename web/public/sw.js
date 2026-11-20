importScripts('/pwa-store.js');
// The production build injects the version and the hashed entry bundle and styles.
const cacheName = 'capzoryx-shell-' + self.CAPZORYX_BUILD;
const shell = self.CAPZORYX_FILES || ['/index.html','/offline.html','/offline.css','/favicon.svg','/pwa-store.js'];

async function cacheShell() {
  const cache=await caches.open(cacheName);
  await cache.addAll(shell.map(url=>new Request(url,{cache:'reload'})));
}
self.addEventListener('install', event => {
  event.waitUntil(cacheShell());
});
self.addEventListener('activate', event => {
  event.waitUntil((async()=>{
    for(const key of await caches.keys())if(key.startsWith('capzoryx-') && key!==cacheName)await caches.delete(key);
    await self.clients.claim();
  })());
});
self.addEventListener('message', event=>{
  if(event.data==='RESTORE_SHELL')event.waitUntil((async()=>{
    if(!await caches.match('/index.html'))await cacheShell();
  })());
  if(event.data==='ACTIVATE_UPDATE')event.waitUntil(self.skipWaiting());
});
async function share(request) {
  const origin = request.headers.get('Origin');
  if(request.headers.get('Sec-Fetch-Site')==='cross-site' || (origin && origin!=='null' && origin!==self.location.origin))return new Response('Cross-origin share rejected',{status:403});
  // A manifest text share uses form-urlencoded. Read a bounded stream before decoding.
  const contentType = (request.headers.get('Content-Type') || '').split(';')[0];
  if(contentType!=='application/x-www-form-urlencoded')return new Response('Expected text share',{status:415});
  const reader=request.body?.getReader();
  if(!reader)return new Response('Missing text',{status:400});
  let size=0, raw='';
  const decoder=new TextDecoder();
  for(;;){
    const {value,done}=await reader.read();
    if(done)break;
    size+=value.length;
    if(size>32768){await reader.cancel();return new Response('Share too long',{status:413});}
    raw+=decoder.decode(value,{stream:true});
  }
  const text=new URLSearchParams(raw+decoder.decode()).get('text')?.trim();
  if(!text || text.length>2000)return new Response('Expected 1–2000 characters',{status:400});
  const id=await self.capzoryxStore.share(text);
  return Response.redirect(new URL('/share?id='+id,self.location.origin).href,303);
}
self.addEventListener('fetch', event=>{
  const {request}=event, url=new URL(request.url);
  if(url.origin!==self.location.origin || url.pathname==='/api' || url.pathname.startsWith('/api/'))return;
  if(request.method==='POST' && url.pathname==='/share'){
    event.respondWith(share(request));
    return;
  }
  if(request.method!=='GET')return;
  if(request.mode==='navigate'){
    event.respondWith(fetch(request).catch(async()=>{
      // Public verification requires a fresh revocation status.
      const offline=url.pathname.startsWith('/verify/')?'/offline.html':'/index.html';
      const cached=await caches.match(offline,{ignoreVary:true});
      if(!cached)return Response.error();
      if(offline!=='/index.html')return cached;
      // A phone can still report "online" when its access point has lost connectivity.
      const html=(await cached.text()).replace('<head>','<head><meta name="capzoryx-offline" content="1">');
      const headers=new Headers(cached.headers);
      headers.delete('Content-Length');headers.delete('Content-Encoding');
      return new Response(html,{headers});
    }));
    return;
  }
  const publicFile=shell.includes(url.pathname) || /^\/assets\/[\w.-]+$/.test(url.pathname)
    || /^\/locales\/[\w-]+\.json$/.test(url.pathname) || /^\/models\/hisab-tagger[\w.-]*$/.test(url.pathname);
  if(!publicFile || url.search || request.headers.has('Authorization'))return;
  const fresh=(async()=>{
    const response=await fetch(request);
    if(response.ok && !response.redirected && !/no-store|private/i.test(response.headers.get('Cache-Control')||'')){
      const cache=await caches.open(cacheName);
      await cache.put(request,response.clone());
    }
    return response;
  })();
  event.waitUntil(fresh.then(()=>{},()=>{}));
  event.respondWith(caches.match(request,{ignoreVary:true}).then(cached=>cached || fresh));
});
