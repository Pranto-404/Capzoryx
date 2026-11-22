import {useState} from 'react';
import {t} from './i18n';

type Request=<T,>(path:string,body?:unknown)=>Promise<T>;
type Status={configured:boolean;linked:boolean;pending:boolean;chat_label:string|null;chat_enabled:boolean};

export function TelegramLink({request}:{request:Request}){
  const [status,setStatus]=useState<Status|null>(null);
  const [url,setUrl]=useState('');
  const [busy,setBusy]=useState(false);
  const [message,setMessage]=useState('');
  const path='/channels/telegram';
  async function run(action:()=>Promise<void>){
    setBusy(true);setMessage('');
    try{await action();}
    catch(e){setMessage(e instanceof Error?e.message:t('Request failed.'));}
    finally{setBusy(false);}
  }
  async function load(){setStatus(await request<Status>(path+'/link'));}
  return <section className="panel"><h2>{t('Telegram assistant and reminders')}</h2>
    {!status?<button className="secondary" disabled={busy} onClick={()=>void run(load)}>{t('Check Telegram connection')}</button>:
      !status.configured?<p>{t('Telegram delivery is currently unavailable.')}</p>:
      status.linked?<><p>{t('Workspace updates go to {chat}.',{chat:status.chat_label||'Telegram'})}</p>
        <p>{t('Book replies share requested totals with Telegram in this private chat. Reminders contain no transaction details.')}</p>
        {status.chat_enabled&&<p>{t('Send /balance, /bills, /dues or /forecast to the bot.')}</p>}
        <div className="actions">
          <button className="secondary" disabled={busy} aria-pressed={status.chat_enabled} onClick={()=>void run(async()=>{
            await request(path+'/chat',{enabled:!status.chat_enabled});await load();
          })}>{status.chat_enabled?t('Turn off Telegram book replies'):t('Turn on Telegram book replies')}</button>
          <button className="secondary" disabled={busy} onClick={()=>void run(async()=>{await request(path+'/unlink',{});setUrl('');await load();})}>{t('Disconnect Telegram')}</button>
        </div></>:
      status.pending?<><p>{t('Confirm that {chat} is your Telegram account.',{chat:status.chat_label||'Telegram'})}</p>
        <div className="actions"><button disabled={busy} onClick={()=>void run(async()=>{await request(path+'/confirm',{});setUrl('');await load();})}>{t('Confirm Telegram alerts')}</button>
        <button className="secondary" disabled={busy} onClick={()=>void run(async()=>{await request(path+'/unlink',{});setUrl('');await load();})}>{t('Cancel')}</button></div></>:
      url?<><a href={url} target="_blank" rel="noreferrer">{t('Start a private chat with the bot')}</a>
        <button className="secondary" disabled={busy} onClick={()=>void run(load)}>{t('Check for confirmation')}</button></>:
      <><p>{t('Connect a private Telegram chat for bill and workspace reminders. Book replies are optional.')}</p>
        <button disabled={busy} onClick={()=>void run(async()=>{
          const link=await request<{bot:string;code:string}>(path+'/link-code',{});
          setUrl('https://t.me/'+encodeURIComponent(link.bot)+'?start='+encodeURIComponent(link.code));
        })}>{t('Connect Telegram')}</button></>}
    {message&&<p role="status">{message}</p>}
  </section>;
}
