import {LocalVoice} from './LocalVoice';
import {Icon} from './Icon';
import {useRef,useState} from 'react';
import {useCurrency} from './Currency';
import {DraftCard} from './DraftCard';
import {prepareDocumentPhoto} from './format';
import {parseRecordForDraft} from './recordParser';
import type {Draft,Profile} from './types';
import {t,useI18n} from './i18n';

type Props={request:<T>(path:string,body?:unknown)=>Promise<T>;revision:string;onSaved:()=>Promise<void>|void;profile:Profile|null;cloudAvailable:boolean};

/** The fast way to add records: photograph a bill or receipt, or just type or say what happened. */
export function QuickAdd({request,revision,onSaved,profile,cloudAvailable}:Props){
  const {currency,digits}=useCurrency();
  const {code}=useI18n();
  const [photoText,setPhotoText]=useState('');
  const [text,setText]=useState('');const [busy,setBusy]=useState<''|'photo'|'text'>('');const [error,setError]=useState('');
  const [draft,setDraft]=useState<Draft|null>(null);const [preview,setPreview]=useState('');
  const file=useRef<HTMLInputElement>(null);const gallery=useRef<HTMLInputElement>(null);
  const smart=!!profile?.smart_assist&&cloudAvailable;
  async function scan(f:File|undefined){
    if(!f)return;setError('');setDraft(null);setPhotoText('');setPreview('');setBusy('photo');
    try{
      const image=await prepareDocumentPhoto(f);setPreview(image);
      const {readPhotoText,draftFromBill}=await import('./billPhoto');
      const recognized=await readPhotoText(image,code);
      setPhotoText(recognized.trim().slice(0,3000));
      const result=draftFromBill(recognized,currency);
      if(result)setDraft(result);
      else setError(t('No unambiguous total in the workspace currency was found. Check the photo and enter the record manually.'));
    }catch(e){setError(e instanceof Error?e.message:t('The photo could not be read.'));}
    finally{setBusy('');if(file.current)file.current.value='';if(gallery.current)gallery.current.value='';}
  }
  async function read(){
    const sentence=text.trim();if(!sentence)return;setError('');setDraft(null);setPhotoText('');setPreview('');setBusy('text');
    try{
      const local=await parseRecordForDraft(sentence,{currency,digits});
      if(local){setDraft(local);return;}
      if(!smart)throw new Error(t('I could not understand that. Try something like "I paid Rahman 5000 for freight yesterday".'));
      const r=await request<{draft:Draft}>('/assist/extract',{text:sentence});
      if(!r.draft.ok)throw new Error(t('I could not find an amount or a payment in that. Try something like "I paid Rahman 5000 for freight yesterday".'));
      setDraft(r.draft);
    }catch(e){setError(e instanceof Error?e.message:t('Could not read that.'));}
    finally{setBusy('');}
  }
  return <section className="panel quick-add" aria-labelledby="quick-add-title">
    <div className="panel-heading"><div><p className="eyebrow">{t('THE FAST WAY')}</p><h2 id="quick-add-title">{t('Add by photo or by typing')}</h2></div></div>
    <div className="quick-grid">
      <div className="quick-box">
        <h3><Icon name="camera"/> {t('Photograph a bill or receipt')}</h3>
        <p className="small muted">{t('Read the total on this device. English and Bangla language files download on first use.')}</p>
        <input ref={file} id="document-photo" type="file" accept="image/*" capture="environment" hidden onChange={e=>void scan(e.target.files?.[0])}/>
        <input ref={gallery} id="document-gallery" type="file" accept="image/*" hidden onChange={e=>void scan(e.target.files?.[0])}/>
        <div className="actions"><button disabled={busy!==''} onClick={()=>file.current?.click()}>{busy==='photo'?t('Reading your photo…'):t('Take a photo')}</button><button className="secondary" disabled={busy!==''} onClick={()=>gallery.current?.click()}>{t('Choose from gallery')}</button></div>
        {photoText&&<details><summary>{t('Text read from the photo')}</summary><p>{photoText}</p></details>}
        {preview&&busy==='photo'&&<img className="scan-preview" src={preview} alt={t('Your photo being read')}/>}
      </div>
      <div className="quick-box">
        <h3><Icon name="pen"/> {t('Type it like a message')}</h3>
        <label htmlFor="quick-text" className="sr-only">{t('Describe the payment or bill')}</label>
        <textarea id="quick-text" rows={3} maxLength={400} value={text} onChange={e=>setText(e.target.value)} placeholder={'e.g. "I paid Rahman 5000 for freight yesterday"\n"Received 20,000 from Karim Traders"\n"Bill from Dhaka Packaging 12000 due in 10 days"'}/>
        <LocalVoice onText={setText}/>
        <button disabled={busy!==''||!text.trim()} onClick={()=>void read()}>{busy==='text'?t('Reading…'):t('Read it')}</button>
      </div>
    </div>
    <p className="coming-soon small"><span className="soon-badge">{t('Coming soon')}</span>{t('Import from a bank or wallet message, or from a statement file.')}</p>
    {error&&<p className="error" role="alert">{error}</p>}
    {draft&&<div className={preview?'scan-compare has-photo':'scan-compare'}>{preview&&<figure className="scan-photo"><img src={preview} alt={t('Your photo')}/><figcaption className="small muted">{t('Compare with your photo before adding')}</figcaption></figure>}<DraftCard key={JSON.stringify(draft)} draft={draft} revision={revision} request={request} onDiscard={()=>{setDraft(null);setPreview('');}} onSaved={async()=>{await onSaved();setText('');setPreview('');}}/></div>}
  </section>;
}
