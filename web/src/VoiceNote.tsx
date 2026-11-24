import {useEffect,useRef,useState} from 'react';
import {currencyDigits,parseMinor} from './api';
import {slug} from './recordParser';
import {formatDate,todayIso} from './format';
import {Icon} from './Icon';
import {t,T,useI18n} from './i18n';

type Request=<R,>(path:string,body?:unknown)=>Promise<R>;
type EntryType='expense'|'income'|'bill';
type Draft={entry_type:EntryType;amount_minor:number;effective_on:string;memo:string;warnings:string[];evidence:string;party:string;category:string;confidence:number;due_on?:string;vendor_name?:string;invoice_number?:string};
type Split={drafts:Draft[];dropped:{evidence:string;reason:string}[];method:'ai'|'rules'};
type Row={id:string;include:boolean;type:EntryType;amount:string;date:string;note:string;party:string;warnings:string[];evidence:string;due:string;invoice:string};
type Status={speech:boolean;cloud_allowed:boolean;max_seconds:number};
type Recognition={lang:string;continuous:boolean;interimResults:boolean;start():void;stop():void;onresult:((e:{resultIndex:number;results:ArrayLike<{isFinal:boolean;0:{transcript:string}}>})=>void)|null;onend:(()=>void)|null;onerror:(()=>void)|null};

const TYPE:Record<EntryType,string>={expense:T('Money paid'),income:T('Money received'),bill:T('Bill still to pay')};
// Server warnings, listed so they are translated with the rest of the page.
export const SERVER_WARNINGS=[T('No day was said, so today is used. Change it if needed.'),T('Check the date.'),
  T('Two numbers were said here. Check that this is the right amount.'),T('Found by the backup reader. Check it, or untick it if it is not a payment.')];
const MIME=['audio/webm;codecs=opus','audio/ogg;codecs=opus','audio/mp4','audio/webm'];
const major=(minor:number,currency:string)=>{const d=currencyDigits(currency);return (minor/10**d).toFixed(d);};
const errorText=(e:unknown)=>e instanceof Error?e.message:t('Something went wrong. Please try again.');

function toBase64(blob:Blob):Promise<string>{
  return new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(String(r.result).split(',')[1]||'');r.onerror=()=>reject(r.error);r.readAsDataURL(blob);});
}

/** Challenge 1: say a whole week of spending in one note; every entry becomes its own draft to check and save. */
export function VoiceNote({request,revision,currency,onSaved}:{request:Request;revision:string;currency:string;onSaved:()=>Promise<void>|void}){
  const {code}=useI18n();
  const [status,setStatus]=useState<Status|null>(null);
  const [language,setLanguage]=useState<'bn'|'en'>(code==='en'?'en':'bn');
  const [stage,setStage]=useState<'idle'|'recording'|'listening'|'hearing'|'splitting'|'review'|'saving'|'saved'>('idle');
  const [seconds,setSeconds]=useState(0);
  const [transcript,setTranscript]=useState('');
  const [rows,setRows]=useState<Row[]>([]);
  const [dropped,setDropped]=useState<Split['dropped']>([]);
  const [method,setMethod]=useState<Split['method']|null>(null);
  const [error,setError]=useState('');
  const [result,setResult]=useState('');
  const [interim,setInterim]=useState('');
  const [level,setLevel]=useState(0);
  const wantDictation=useRef(false);
  const recorder=useRef<MediaRecorder|null>(null);
  const live=useRef<Recognition|null>(null);
  const timer=useRef<number|undefined>(undefined);
  const alive=useRef(true);
  const browser=window as unknown as {SpeechRecognition?:new()=>Recognition;webkitSpeechRecognition?:new()=>Recognition};
  const Dictation=browser.SpeechRecognition||browser.webkitSpeechRecognition;
  const maxSeconds=status?.max_seconds||180;
  const canRecord=!!status?.speech&&!!status.cloud_allowed&&typeof MediaRecorder!=='undefined'&&!!navigator.mediaDevices?.getUserMedia;

  useEffect(()=>{
    alive.current=true;
    void request<Status>('/assist/voice-note').then(s=>{if(alive.current)setStatus(s);}).catch(()=>{if(alive.current)setStatus({speech:false,cloud_allowed:false,max_seconds:180});});
    return ()=>{alive.current=false;wantDictation.current=false;clearInterval(timer.current);recorder.current?.stream.getTracks().forEach(x=>x.stop());live.current?.stop();};
  },[]);// eslint-disable-line react-hooks/exhaustive-deps

  async function record(){
    setError('');setResult('');
    let stream:MediaStream;
    try{stream=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true,autoGainControl:true}});}
    catch{setError(t('Microphone permission is off. Allow the microphone, or type the note.'));return;}
    const mimeType=MIME.find(m=>MediaRecorder.isTypeSupported(m))||'';
    const rec=new MediaRecorder(stream,{...(mimeType?{mimeType}:{}),audioBitsPerSecond:32000});
    const chunks:Blob[]=[];
    rec.ondataavailable=e=>{if(e.data.size)chunks.push(e.data);};
    rec.onstop=()=>{
      stream.getTracks().forEach(x=>x.stop());clearInterval(timer.current);
      if(!alive.current)return;
      const blob=new Blob(chunks,{type:rec.mimeType||mimeType||'audio/webm'});
      void hear(blob);
    };
    // A live sound-level bar shows the phone is hearing the owner the whole time.
    try{
      const audio=new AudioContext();const source=audio.createMediaStreamSource(stream);const meter=audio.createAnalyser();
      meter.fftSize=512;source.connect(meter);const buf=new Uint8Array(meter.fftSize);
      const tick=()=>{if(rec.state!=='recording'){void audio.close().catch(()=>{});setLevel(0);return;}
        meter.getByteTimeDomainData(buf);let peak=0;for(const v of buf)peak=Math.max(peak,Math.abs(v-128));
        setLevel(Math.min(1,peak/64));requestAnimationFrame(tick);};
      requestAnimationFrame(tick);
    }catch{/* the meter is optional */}
    recorder.current=rec;rec.start(1000);setSeconds(0);setStage('recording');
    const started=Date.now();
    timer.current=window.setInterval(()=>{const s=Math.floor((Date.now()-started)/1000);setSeconds(s);if(s>=maxSeconds)rec.stop();},250);
  }
  async function hear(blob:Blob){
    if(blob.size<1000){setStage('idle');setError(t('The recording was too short. Hold the button a little longer.'));return;}
    setStage('hearing');
    try{
      const mime=(blob.type||'audio/webm').replace(/\s+/g,'');
      const data=await request<{transcript:string}>('/assist/voice-note',{audio_b64:await toBase64(blob),mime,language,consent:true});
      if(!alive.current)return;
      setTranscript(cur=>(cur.trim()?cur.trim()+'\n':'')+data.transcript);setStage('idle');
    }catch(e){if(alive.current){setStage('idle');setError(errorText(e)+' '+t('You can also type the note, or use live dictation.'));}}
  }
  function dictate(){
    if(!Dictation)return;
    setError('');wantDictation.current=true;
    const run=()=>{
      const engine=new Dictation();engine.lang=language==='bn'?'bn-BD':'en-US';engine.continuous=true;engine.interimResults=true;
      engine.onresult=e=>{let said='',draft='';for(let i=e.resultIndex;i<e.results.length;i++){const x=e.results[i][0].transcript;if(e.results[i].isFinal)said+=x+' ';else draft+=x;}
        if(said.trim())setTranscript(cur=>(cur.trim()?cur.trim()+' ':'')+said.trim());setInterim(draft);};
      engine.onerror=()=>{/* a pause or a network blip: onend restarts while the owner has not pressed Stop */};
      // Android ends a session after each pause; keep listening until the owner presses Stop.
      engine.onend=()=>{setInterim('');if(alive.current&&wantDictation.current){try{run();return;}catch{/* give up below */}}if(alive.current)setStage(s=>s==='listening'?'idle':s);};
      live.current=engine;engine.start();
    };
    run();setStage('listening');
    const started=Date.now();setSeconds(0);
    timer.current=window.setInterval(()=>{const sec=Math.floor((Date.now()-started)/1000);setSeconds(sec);if(sec>=maxSeconds)stopDictation();},500);
  }
  function stopDictation(){wantDictation.current=false;clearInterval(timer.current);live.current?.stop();setInterim('');setStage('idle');}
  async function split(){
    setError('');setResult('');setStage('splitting');
    try{
      const data=await request<Split>('/assist/batch-drafts',{transcript:transcript.trim(),consent:!!status?.cloud_allowed});
      if(!alive.current)return;
      setRows(data.drafts.map(d=>({id:crypto.randomUUID(),include:true,type:d.entry_type,amount:major(d.amount_minor,currency),date:d.effective_on,
        note:d.memo,party:d.party,warnings:d.warnings,evidence:d.evidence,due:d.due_on||d.effective_on,invoice:d.invoice_number||''})));
      setDropped(data.dropped);setMethod(data.method);
      setStage(data.drafts.length?'review':'idle');
      if(!data.drafts.length)setError(t('No amounts were found in the note. Say or type each payment with its amount, for example “Shombar bhara 5000 taka”.'));
    }catch(e){if(alive.current){setStage('idle');setError(errorText(e));}}
  }
  const update=(id:string,patch:Partial<Row>)=>setRows(cur=>cur.map(r=>r.id===id?{...r,...patch}:r));
  const chosen=rows.filter(r=>r.include);
  const total=(type:EntryType)=>chosen.filter(r=>r.type===type).reduce((sum,r)=>{try{return sum+parseMinor(r.amount,currency);}catch{return sum;}},0);
  async function save(){
    setError('');
    const today=todayIso();
    let records;
    try{
      records=chosen.map((r,i)=>{
        const minor=parseMinor(r.amount,currency);
        if(minor<=0)throw new Error(t('Entry {n}: the amount must be more than zero.',{n:i+1}));
        if(r.type==='bill'){
          const vendor=slug(r.party)||'voice-supplier';
          if(r.date>today)throw new Error(t('Entry {n}: a bill date cannot be in the future.',{n:i+1}));
          return {request_id:r.id,kind:'invoice',amount_minor:minor,effective_on:r.date,vendor_id:vendor,invoice_number:r.invoice||`VOICE-${r.date.replaceAll('-','')}-${i+1}`,due_on:r.due<r.date?r.date:r.due,memo:r.note.slice(0,2000)};
        }
        return {request_id:r.id,kind:'cash',amount_minor:minor,effective_on:r.date,direction:r.type==='income'?'inflow':'outflow',status:r.date>today?'scheduled':'cleared',memo:r.note.slice(0,2000)};
      });
    }catch(e){setError(errorText(e));return;}
    setStage('saving');
    try{
      const done=await request<{saved:number;replayed?:boolean}>('/workspace/records/batch',{expected_revision:revision,records});
      if(!alive.current)return;
      setResult(t('{count} records added. Your balance, forecast and activity are updated.',{count:done.replayed?records.length:done.saved}));
      setStage('saved');setRows([]);setTranscript('');setDropped([]);
      await onSaved();
    }catch(e){if(alive.current){setStage('review');setError(errorText(e));}}
  }

  const busy=['recording','listening','hearing','splitting','saving'].includes(stage);
  return <section className="panel voice-note" aria-labelledby="voice-note-title">
    <p className="eyebrow">{t('Voice note')}</p>
    <h2 id="voice-note-title">{t('Say a whole week of spending at once')}</h2>
    <p className="muted">{t('Talk naturally, for example: “Shombar dokan bhara 5000 dilam, tarpor transport 300. Budhbar Rahim theke 12 hajar pelam.” Each payment becomes its own draft. You check them, then save them all together.')}</p>
    <div className="voice-controls">
      <label className="voice-lang">{t('I will speak')}<select value={language} disabled={busy} onChange={e=>setLanguage(e.target.value as 'bn'|'en')}><option value="bn">{t('Bangla or Banglish')}</option><option value="en">English</option></select></label>
      {stage==='recording'
        ?<button className="voice-record recording" onClick={()=>recorder.current?.stop()}><span className="rec-dot" aria-hidden="true"/>{t('Stop ({time})',{time:`${Math.floor(seconds/60)}:${String(seconds%60).padStart(2,'0')}`})}</button>
        :stage==='listening'
        ?<button className="voice-record recording" onClick={stopDictation}><span className="rec-dot" aria-hidden="true"/>{t('Stop dictation')}</button>
        :<>{canRecord&&<button className="voice-record" disabled={busy} onClick={()=>void record()}><Icon name="spark"/>{stage==='hearing'?t('Listening to your note…'):t('Record a voice note')}</button>}
          {!canRecord&&Dictation&&<button className="voice-record" disabled={busy} onClick={dictate}><Icon name="spark"/>{t('Start live dictation')}</button>}</>}
    </div>
    {stage==='recording'&&<div className="voice-level" aria-hidden="true"><span style={{width:`${Math.round(8+level*92)}%`}}/></div>}
    {stage==='listening'&&interim&&<p className="voice-interim" aria-live="polite">{interim}…</p>}
    {stage==='recording'&&<p className="small muted" role="status">{t('Up to {minutes} minutes. Say the day, what it was for and the amount for each payment.',{minutes:Math.round(maxSeconds/60)})}</p>}
    {status&&!status.cloud_allowed&&<p className="small muted">{t('Smart assist is off, so recordings are not sent for transcription. Use live dictation or type the note; it is split on this server without AI.')}</p>}
    {canRecord&&<p className="small muted">{t('The recording is sent to the speech service to be written down and is not stored by Capzoryx.')}</p>}
    <label htmlFor="voice-transcript">{t('What you said (you can correct it)')}</label>
    <textarea id="voice-transcript" rows={4} maxLength={4000} value={transcript} disabled={busy} onChange={e=>setTranscript(e.target.value)} placeholder={t('Your words appear here. You can also type or paste a whole week of spending.')}/>
    <div className="actions"><button disabled={busy||transcript.trim().length<3} onClick={()=>void split()}>{stage==='splitting'?t('Making drafts…'):t('Make drafts')}</button>
      {transcript&&!busy&&<button className="secondary" onClick={()=>{setTranscript('');setRows([]);setDropped([]);setStage('idle');}}>{t('Clear')}</button>}</div>
    {error&&<p className="error" role="alert">{error}</p>}
    {result&&<p className="success" role="status">{result}</p>}

    {(stage==='review'||stage==='saving')&&<div className="batch-review">
      <h3>{t('{count} drafts from your note',{count:rows.length})}</h3>
      {method==='rules'&&<p className="notice small">{t('Read without AI. Check each draft carefully.')}</p>}
      <ol className="batch-list">{rows.map((r,i)=><li key={r.id} className={r.include?undefined:'excluded'}>
        <div className="batch-head"><label className="check"><input type="checkbox" checked={r.include} onChange={e=>update(r.id,{include:e.target.checked})}/><b>{t('Entry {n}',{n:i+1})}</b></label>
          {r.warnings.length>0&&<span className="badge warn">{t('Check')}</span>}</div>
        {r.evidence&&<p className="batch-quote">“{r.evidence}”</p>}
        <div className="batch-fields">
          <label>{t('Type')}<select value={r.type} onChange={e=>update(r.id,{type:e.target.value as EntryType})}>{(Object.keys(TYPE) as EntryType[]).map(k=><option key={k} value={k}>{t(TYPE[k])}</option>)}</select></label>
          <label>{t('Amount ({currency})',{currency})}<input inputMode="decimal" value={r.amount} onChange={e=>update(r.id,{amount:e.target.value})}/></label>
          <label>{t('Date')}<input type="date" value={r.date} max={r.type==='bill'?todayIso():undefined} onChange={e=>update(r.id,{date:e.target.value})}/></label>
          {r.type==='bill'&&<label>{t('Due date')}<input type="date" value={r.due} min={r.date} onChange={e=>update(r.id,{due:e.target.value})}/></label>}
          {r.type==='bill'&&<label>{t('Supplier')}<input value={r.party} maxLength={60} onChange={e=>update(r.id,{party:e.target.value})}/></label>}
          <label className="batch-note">{t('Note')}<input value={r.note} maxLength={200} onChange={e=>update(r.id,{note:e.target.value})}/></label>
        </div>
        {r.warnings.map((w,j)=><p className="notice small" key={j}>{t(w)}</p>)}
      </li>)}</ol>
      {dropped.length>0&&<details className="batch-dropped"><summary>{t('{count} parts were not turned into drafts',{count:dropped.length})}</summary>
        <ul>{dropped.map((d,i)=><li key={i}>“{d.evidence}” · {d.reason==='AMOUNT_NOT_SAID'?t('the amount was not clearly said'):t('these words are not in the note')}</li>)}</ul></details>}
      <p className="batch-total"><span>{t('Paid {amount}',{amount:major(total('expense'),currency)+' '+currency})}</span><span>{t('Received {amount}',{amount:major(total('income'),currency)+' '+currency})}</span>{total('bill')>0&&<span>{t('Bills {amount}',{amount:major(total('bill'),currency)+' '+currency})}</span>}</p>
      <div className="actions"><button disabled={stage==='saving'||!chosen.length} onClick={()=>void save()}>{stage==='saving'?t('Saving…'):t('Save {count} records',{count:chosen.length})}</button>
        <button className="secondary" disabled={stage==='saving'} onClick={()=>{setRows([]);setStage('idle');}}>{t('Discard all')}</button></div>
      <p className="small muted">{t('Saved together: either all chosen records are added, or none are.')} {chosen.length>0&&t('Dates from {from} to {to}.',{from:formatDate(chosen.map(r=>r.date).sort()[0]),to:formatDate(chosen.map(r=>r.date).sort().at(-1)!)})}</p>
    </div>}
  </section>;
}
