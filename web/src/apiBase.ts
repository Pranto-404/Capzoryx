/** Website and installed PWA use the same-origin rewrite. The packaged Android
 * WebView can send credentials only to our canonical HTTPS API. */
declare const __CAPZORYX_NATIVE__:boolean;
export const nativeBuild = typeof __CAPZORYX_NATIVE__ !== 'undefined' && __CAPZORYX_NATIVE__;
export const publicOrigin = () => nativeBuild ? 'https://capzoryx.vercel.app' : location.origin;

export async function apiFetch(path:string, init:RequestInit={}):Promise<Response>{
  if(!nativeBuild)return fetch(path,init);
  const {nativeFetch}=await import('./nativeSession');
  return nativeFetch(path,init);
}
