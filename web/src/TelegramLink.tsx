import {useEffect,useState} from 'react';
import {t,T} from './i18n';

type Request=<T,>(path:string,body?:unknown)=>Promise<T>;
type Status={configured:boolean;linked:boolean;pending:boolean;awaiting_message?:boolean;chat_label:string|null;chat_enabled:boolean;records_enabled:boolean};
type Channel='telegram'|'whatsapp';

const copy={
  telegram:{title:T('Telegram'),connect:T('Connect Telegram'),open:T('Open Telegram'),disconnect:T('Disconnect Telegram'),
    intro:T('Chat with Capzoryx in Telegram: ask about cash, dues and bills in Bangla, Banglish or English, and get bill reminders.'),
    unavailable:T('Telegram is not set up on this server yet.')},
  whatsapp:{title:T('WhatsApp'),connect:T('Connect WhatsApp'),open:T('Open WhatsApp'),disconnect:T('Disconnect WhatsApp'),
    intro:T('Chat with Capzoryx on WhatsApp the same way you would message a person: “cash koto?”, “who owes me?”.'),
    unavailable:T('WhatsApp is not set up on this server yet.')},
};

export function ChannelLink({request,channel}:{request:Request;channel:Channel}){
  const [status,setStatus]=useState<Status|null>(null);
  const [url,setUrl]=useState('');
  const [code,setCode]=useState('');
  const [busy,setBusy]=useState(false);
  const [message,setMessage]=useState('');
  const path='/channels/'+channel;
  const c=copy[channel];
  async function run(action:()=>Promise<void>){
    setBusy(true);setMessage('');
    try{await action();}
    catch(e){setMessage(e instanceof Error?e.message:t('Request failed.'));}
    finally{setBusy(false);}
  }
  async function load(){setStatus(await request<Status>(path+'/link'));}
  useEffect(()=>{void run(load);},[channel]);// eslint-disable-line react-hooks/exhaustive-deps
  const reset=async()=>{await request(path+'/unlink',{});setUrl('');setCode('');await load();};
  const toggle=(kind:'chat'|'records',on:boolean)=>run(async()=>{await request(path+'/'+kind,{enabled:on});await load();});
  async function start(){
    if(channel==='telegram'){
      const link=await request<{bot:string;code:string}>(path+'/link-code',{});
      setUrl('https://t.me/'+encodeURIComponent(link.bot)+'?start='+encodeURIComponent(link.code));
    }else{
      const link=await request<{number:string;code:string}>(path+'/link-code',{});
      setCode(link.code);
      setUrl('https://wa.me/'+encodeURIComponent(link.number)+'?text='+encodeURIComponent('LINK '+link.code));
    }
  }
  let body;
  if(!status)body=busy?<p className="muted">{t('Checking…')}</p>:<button className="secondary" disabled={busy} onClick={()=>void run(load)}>{t('Check connection')}</button>;
  else if(!status.configured)body=<p className="muted">{t(c.unavailable)}</p>;
  else if(status.linked)body=<>
    <p className="channel-state"><span className="dot on" aria-hidden="true"/>{t('Connected to {chat}',{chat:status.chat_label||t(c.title)})}</p>
    <label className="switch-row"><input type="checkbox" checked={status.chat_enabled} disabled={busy} onChange={e=>void toggle('chat',e.target.checked)}/>
      <span><b>{t('Answer questions about my books')}</b><small>{t('Totals you ask for are sent to this private chat.')}</small></span></label>
    <label className="switch-row"><input type="checkbox" checked={status.records_enabled} disabled={busy||!status.chat_enabled} onChange={e=>void toggle('records',e.target.checked)}/>
      <span><b>{t('Let me add cash entries from chat')}</b><small>{t('Each entry is shown back to you and saved only when you tap Save.')}</small></span></label>
    <div className="actions"><button className="ghost" disabled={busy} onClick={()=>void run(reset)}>{t(c.disconnect)}</button></div></>;
  else if(status.pending)body=<>
    <p>{t('Is {chat} your account?',{chat:status.chat_label||t(c.title)})}</p>
    <div className="actions"><button disabled={busy} onClick={()=>void run(async()=>{await request(path+'/confirm',{});setUrl('');setCode('');await load();})}>{t('Yes, connect it')}</button>
      <button className="ghost" disabled={busy} onClick={()=>void run(reset)}>{t('Cancel')}</button></div></>;
  else if(url)body=<>
    <ol className="steps">
      <li>{t('Open the chat and send the message.')}{code&&<> <code>{'LINK '+code}</code></>}</li>
      <li>{t('Come back here and confirm.')}</li>
    </ol>
    <div className="actions"><a className="button" href={url} target="_blank" rel="noreferrer">{t(c.open)}</a>
      <button className="secondary" disabled={busy} onClick={()=>void run(load)}>{t('I sent it')}</button></div></>;
  else body=<><p className="muted">{t(c.intro)}</p>
    <button disabled={busy} onClick={()=>void run(start)}>{t(c.connect)}</button></>;
  return <section className="panel channel"><h2>{t(c.title)}</h2>{body}{message&&<p role="status">{message}</p>}</section>;
}

export function TelegramLink({request}:{request:Request}){return <ChannelLink request={request} channel="telegram"/>;}
