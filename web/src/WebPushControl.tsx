import {useEffect,useState} from 'react';
import {t} from './i18n';

type Request=<T,>(path:string,body?:unknown)=>Promise<T>;

export function WebPushControl({request,scope}:{request:Request;scope:string}){
  const [registration,setRegistration]=useState<ServiceWorkerRegistration|null>(null);
  const [identity,setIdentity]=useState('');
  const [publicKey,setPublicKey]=useState<Uint8Array<ArrayBuffer>|null>(null);
  const [busy,setBusy]=useState(false);
  const [message,setMessage]=useState('');
  const key='capzoryx-push:'+scope;
  useEffect(()=>{
    let active=true;
    if(!('serviceWorker' in navigator)||!('PushManager' in window))return;
    navigator.serviceWorker.getRegistration().then(async reg=>{
      if(!reg||!active)return;
      const existing=await reg.pushManager.getSubscription();
      if(!active)return;
      setRegistration(reg);setIdentity(existing?localStorage.getItem(key)||'':'');
      const settings=await request<{webpush:boolean;public_key:string|null}>('/notifications/push-config');
      if(!active||!settings.webpush||!settings.public_key)return;
      const encoded=settings.public_key.replace(/-/g,'+').replace(/_/g,'/');
      setPublicKey(Uint8Array.from(atob(encoded.padEnd(Math.ceil(encoded.length/4)*4,'=')),c=>c.charCodeAt(0)));
    }).catch(()=>{});
    return ()=>{active=false;};
  },[key]);
  if(!registration)return null;
  async function toggle(){
    if(!registration)return;
    setBusy(true);setMessage('');
    try{
      if(identity){
        await request('/notifications/subscriptions/'+identity+'/revoke',{});
        localStorage.removeItem(key);setIdentity('');
        if(!Object.keys(localStorage).some(k=>k.startsWith('capzoryx-push:'))){
          const existing=await registration.pushManager.getSubscription();
          if(existing)await existing.unsubscribe();
        }
      }else{
        if(!publicKey){setMessage(t('Push delivery is currently unavailable.'));return;}
        const permission=await Notification.requestPermission();
        if(permission!=='granted'){setMessage(t('Push delivery is currently unavailable.'));return;}
        const sub=await registration.pushManager.getSubscription()||await registration.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:publicKey});
        const result=await request<{id:string}>('/notifications/subscriptions',{kind:'webpush',endpoint:sub.endpoint});
        localStorage.setItem(key,result.id);setIdentity(result.id);
      }
    }catch(e){setMessage(e instanceof Error?e.message:t('Request failed.'));}
    finally{setBusy(false);}
  }
  return <div><button className="secondary" type="button" disabled={busy} onClick={()=>void toggle()}>
    {identity?t('Turn off push on this device'):t('Turn on push on this device')}</button>
    {message&&<p role="status">{message}</p>}</div>;
}
