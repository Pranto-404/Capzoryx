import {useState} from 'react';
import {t,useI18n} from './i18n';

type Request=<T,>(path:string,body?:unknown)=>Promise<T>;

export function ReminderDraft({request,id}:{request:Request;id:string}){
  const {code}=useI18n();
  const [language,setLanguage]=useState(code==='bn'?'bn':'en');
  const [draft,setDraft]=useState('');
  const [busy,setBusy]=useState(false);
  const [notice,setNotice]=useState('');
  async function prepare(){
    setBusy(true);setNotice('');setDraft('');
    try{
      const result=await request<{message:string}>('/copilot/message',{receivable_id:id,language});
      setDraft(result.message);
    }catch(e){setNotice(e instanceof Error?e.message:t('Request failed.'));}
    finally{setBusy(false);}
  }
  async function share(){
    try{
      if(navigator.share)await navigator.share({text:draft});
      else{await navigator.clipboard.writeText(draft);setNotice(t('Reminder copied.'));}
    }catch(e){if(!(e instanceof Error&&e.name==='AbortError'))setNotice(t('Select the reminder text and copy it.'));}
  }
  return <details><summary>{t('Draft a reminder')}</summary>
    <label>{t('Reminder language')}<select value={language} disabled={busy} onChange={e=>{setLanguage(e.target.value);setDraft('');setNotice('');}}>
      <option value="bn">বাংলা</option><option value="en">English</option>
    </select></label>
    <button type="button" className="secondary" disabled={busy} onClick={()=>void prepare()}>{t('Prepare reminder')}</button>
    {draft&&<><label>{t('Review your reminder')}<textarea readOnly value={draft}/></label>
      <button type="button" onClick={()=>void share()}>{typeof navigator.share==='function'?t('Share reminder…'):t('Copy reminder')}</button></>}
    {notice&&<p role="status">{notice}</p>}
  </details>;
}
