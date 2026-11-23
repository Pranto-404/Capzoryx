import {useEffect,useState} from 'react';
import {money} from './api';
import {formatDate} from './format';
import {t,T} from './i18n';

type Request=<R,>(path:string,body?:unknown)=>Promise<R>;
type Source={url:string;title:string};
type Observation={value_minor:number;source:string;url:string;observed_at:string;fetched_at:number;kind:string;confidence:string};
type Indicator={key:string;label:string;unit:string;currency:string;source_kind:string;latest:Observation|null;status:'ok'|'stale'|'unavailable'|'needs_quote';reason:string};
type Research={status:'running'|'done'|'unavailable'|'failed';reason:string;started_at:number;finished_at:number|null;
  result:{findings:{text:string;sources:Source[]}[];competitors:{name:string;kind:string;area:string;why:string;sources:Source[]}[];sources:Source[];searches:string[]}|null};
type Market={currency:string;profile_ready:boolean;indicators:Indicator[];coverage_note:string;research:Research|null;research_allowed:boolean;research_configured:boolean;owner_competitors:string[]};

const KIND:Record<string,string>={delayed:T('Daily reference rate'),derived:T('Estimate'),owner:T('Your price'),research:T('Web research')};
const COMPETITOR:Record<string,string>={direct:T('Direct'),indirect:T('Indirect'),emerging:T('Emerging'),leader:T('Market leader'),benchmark:T('Benchmark')};
const errorText=(e:unknown)=>e instanceof Error?e.message:t('Request failed.');
const day=(iso:string)=>formatDate(iso.slice(0,10));

function Sources({list}:{list:Source[]}){
  if(!list.length)return <small className="market-unverified">{t('No source found: treat as unverified')}</small>;
  return <small className="market-sources">{list.map((s,i)=><a key={i} href={s.url} target="_blank" rel="noreferrer noopener">{s.title||t('Source')}</a>)}</small>;
}

/** The owner's market: prices that matter to their products, with where each figure came from, plus cited research. */
export function MarketPanel({request,openSettings}:{request:Request;openSettings:()=>void}){
  const [data,setData]=useState<Market|null>(null);
  const [error,setError]=useState('');
  const [busy,setBusy]=useState(false);
  const [quote,setQuote]=useState<string|null>(null);
  const load=()=>request<Market>('/market').then(setData).catch(e=>setError(errorText(e)));
  useEffect(()=>{void load();},[]);// eslint-disable-line react-hooks/exhaustive-deps
  useEffect(()=>{
    if(data?.research?.status!=='running')return;
    const id=window.setInterval(()=>void load(),4000);return()=>window.clearInterval(id);
  },[data?.research?.status]);// eslint-disable-line react-hooks/exhaustive-deps
  async function act(fn:()=>Promise<Market>){setBusy(true);setError('');try{setData(await fn());}catch(e){setError(errorText(e));}finally{setBusy(false);}}
  if(!data)return <section className="panel market-panel" role="status"><h2>{t('Your market')}</h2><p className="muted">{error||t('Checking market prices…')}</p></section>;
  const r=data.research;
  return <section className="panel market-panel" aria-labelledby="market-title">
    <div className="panel-heading"><div><p className="eyebrow">{t('Market watch')}</p><h2 id="market-title">{t('Your market')}</h2></div>
      <button className="secondary small-button" disabled={busy} onClick={()=>void act(()=>request<Market>('/market'))}>{t('Refresh')}</button></div>
    <ul className="market-list">{data.indicators.map(i=><li key={i.key}>
      <div><b>{i.label}</b><small>{i.unit}</small></div>
      <div className="market-value">
        {i.latest?<><strong>{money(i.latest.value_minor,i.currency)}</strong>
          <small><span className={'pill kind-'+i.latest.kind}>{t(KIND[i.latest.kind]||i.latest.kind)}</span> {day(i.latest.observed_at)}
            {i.latest.url?<> · <a href={i.latest.url} target="_blank" rel="noreferrer noopener">{i.latest.source}</a></>:<> · {i.latest.source}</>}</small></>
          :<strong className="muted">{i.status==='needs_quote'?t('No price yet'):t('Unavailable')}</strong>}
        {i.status==='stale'&&<small className="market-warn">{t('Out of date: the source has not updated recently.')}{i.reason&&' '+i.reason}</small>}
        {i.status==='unavailable'&&<small className="market-warn">{i.reason||t('The source could not be reached. Nothing is shown rather than a guess.')}</small>}
        {i.source_kind==='quote'&&quote!==i.key&&<button className="link" onClick={()=>setQuote(i.key)}>{t('Add today\'s price')}</button>}
      </div>
      {quote===i.key&&<QuoteForm currency={i.currency} unit={i.unit} busy={busy} cancel={()=>setQuote(null)}
        submit={b=>void act(async()=>{const next=await request<Market>('/market/quotes',{indicator:i.key,...b});setQuote(null);return next;})}/>}
    </li>)}</ul>
    {data.coverage_note&&<p className="muted small-print">{data.coverage_note}</p>}

    <h3>{t('Market research')}</h3>
    {!data.research_allowed?<p className="muted">{t('Online research is off. Turn on “Research my market and competitors online” in Settings → Business → Permissions.')} <button className="link" onClick={openSettings}>{t('Open settings')}</button></p>
    :r?.status==='running'?<p role="status" className="muted"><span className="loading-ring small-ring"/> {t('Researching your market with web search… this takes up to a minute.')}</p>
    :<>
      {(r?.status==='unavailable'||r?.status==='failed')&&<p className="notice">{r.reason}</p>}
      {r?.result&&<>
        <ul className="market-findings">{r.result.findings.map((f,i)=><li key={i}>{f.text}<Sources list={f.sources}/></li>)}</ul>
        {!!r.result.competitors.length&&<><h3>{t('Competitors found')}</h3><ul className="market-competitors">{r.result.competitors.map(c=><li key={c.name}>
          <div><b>{c.name}</b> <span className="pill">{t(COMPETITOR[c.kind]||c.kind)}</span>{c.area&&<small>{c.area}</small>}</div>
          {c.why&&<small>{c.why}</small>}<Sources list={c.sources}/></li>)}</ul></>}
        <p className="muted small-print">{t('Researched {date} from public web pages. AI summaries can be wrong; open the sources before acting.',{date:formatDate(new Date((r.finished_at||r.started_at)*1000).toISOString().slice(0,10))})}</p>
      </>}
      {!data.research_configured&&!r&&<p className="muted">{t('Web research is not set up on this server yet, so only the prices above are shown.')}</p>}
      <button className="secondary" disabled={busy} onClick={()=>void act(()=>request<Market>('/market/research',{}))}>{r?.result?t('Research again'):t('Research my market')}</button>
    </>}
    {!!data.owner_competitors.length&&<p className="muted small-print">{t('Competitors you named: {names}',{names:data.owner_competitors.join(', ')})}</p>}
    {error&&<p className="error" role="alert">{error}</p>}
  </section>;
}

function QuoteForm({currency,unit,busy,cancel,submit}:{currency:string;unit:string;busy:boolean;cancel:()=>void;submit:(b:{value_minor:number;observed_on:string;source:string})=>void}){
  const [value,setValue]=useState('');const [on,setOn]=useState(new Date().toISOString().slice(0,10));const [source,setSource]=useState('');
  const minor=Math.round(Number(value.replace(/,/g,''))*100);
  return <form className="market-quote" onSubmit={e=>{e.preventDefault();if(minor>0)submit({value_minor:minor,observed_on:on,source});}}>
    <div className="form-row">
      <label>{t('Price ({currency} {unit})',{currency,unit})}<input required inputMode="decimal" value={value} onChange={e=>setValue(e.target.value)}/></label>
      <label>{t('Date')}<input type="date" required value={on} max={new Date().toISOString().slice(0,10)} onChange={e=>setOn(e.target.value)}/></label>
      <label>{t('Where you saw it')}<input required minLength={2} maxLength={120} value={source} onChange={e=>setSource(e.target.value)} placeholder={t('e.g. BAJUS, my dealer')}/></label>
    </div>
    <div className="actions"><button disabled={busy||!(minor>0)}>{t('Save price')}</button><button type="button" className="ghost" onClick={cancel}>{t('Cancel')}</button></div>
  </form>;
}
