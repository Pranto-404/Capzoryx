import {useEffect,useState} from 'react';
import {t} from './i18n';
import {formatDate} from './format';

const taka=(minor:number)=>'৳'+(minor/100).toLocaleString('en-IN',{maximumFractionDigits:2});

type Request=<T,>(path:string,body?:unknown)=>Promise<T>;
type Draft={id:string;source:string;amount_minor:number;direction:'inflow'|'outflow';party:string;day:string};
type Status={enabled:boolean;last_seen:number|null;pending:Draft[]};

export function SmsInbox({request}:{request:Request}){
  const [status,setStatus]=useState<Status|null>(null);
  const [url,setUrl]=useState('');
  const [busy,setBusy]=useState(false);
  const [message,setMessage]=useState('');
  const path='/inbox/sms';
  async function run(action:()=>Promise<void>){
    setBusy(true);setMessage('');
    try{await action();}catch(e){setMessage(e instanceof Error?e.message:t('Request failed.'));}finally{setBusy(false);}
  }
  const load=async()=>setStatus(await request<Status>(path));
  useEffect(()=>{void run(load);},[]);// eslint-disable-line react-hooks/exhaustive-deps
  const act=(id:string,action:'save'|'skip')=>run(async()=>{await request(`${path}/drafts/${id}/${action}`,{});await load();});
  return <section id="payment-sms" className="panel channel"><h2>{t('Payment SMS')}</h2>
    <p className="muted">{t('Forward bKash, Nagad, Rocket and bank SMS from your Android phone. Capzoryx reads each payment and asks before saving it. OTP and PIN messages are ignored.')}</p>
    {url?<>
      <ol className="steps">
        <li>{t('Install a free SMS forwarding app, for example “SMS to URL Forwarder”.')}</li>
        <li>{t('Add a rule that forwards messages from bKash, Nagad, Rocket and your bank to this link:')}
          <input readOnly value={url} onFocus={e=>e.currentTarget.select()} aria-label={t('Forwarding link')}/></li>
        <li>{t('Keep this link private. Anyone with it can send drafts to your inbox.')}</li>
      </ol>
      <div className="actions"><button className="secondary" onClick={()=>void navigator.clipboard?.writeText(url)}>{t('Copy link')}</button>
        <button className="ghost" onClick={()=>setUrl('')}>{t('Done')}</button></div></>:
    status?.enabled?<p className="channel-state"><span className="dot on" aria-hidden="true"/>{status.last_seen?t('Receiving SMS'):t('Waiting for the first SMS')}</p>:null}
    {!!status?.pending.length&&<ul className="sms-list">{status.pending.map(d=><li key={d.id}>
      <div><b>{d.source}</b> · {d.direction==='inflow'?t('Received'):t('Paid')} <b>{taka(d.amount_minor)}</b>
        {d.party&&<> · {d.party}</>}<small>{formatDate(d.day)}</small></div>
      <div className="actions"><button disabled={busy} onClick={()=>void act(d.id,'save')}>{t('Save')}</button>
        <button className="ghost" disabled={busy} onClick={()=>void act(d.id,'skip')}>{t('Skip')}</button></div></li>)}</ul>}
    {!url&&<div className="actions">
      <button className={status?.enabled?'secondary':''} disabled={busy} onClick={()=>void run(async()=>{setUrl((await request<{url:string}>(path+'/link',{})).url);await load();})}>{status?.enabled?t('Make a new link'):t('Set up SMS forwarding')}</button>
      {status?.enabled&&<button className="ghost" disabled={busy} onClick={()=>void run(async()=>{await request(path+'/unlink',{});await load();})}>{t('Turn off')}</button>}
    </div>}
    {message&&<p role="status">{message}</p>}
  </section>;
}
