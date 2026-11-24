import {useEffect,useState} from 'react';
import {accountRequest,money,parseMinor} from './api';
import {CashRadarView,type Radar} from './CashRadar';
import {formatDate} from './format';
import {LanguagePicker,t,T,useI18n} from './i18n';
import {Brand} from './Logo';
import {ThemeButton} from './Theme';

type EntryType='expense'|'income'|'bill';
type Draft={title:string;evidence:string;entry_type:EntryType;amount_minor:number;effective_on:string;needs_review:boolean};
type Preview={note:string;currency:string;voice:{drafts:Draft[];dropped:{evidence:string;reason:string}[]};
  radar:Record<'habit'|'overdue',Radar>};
type Row={draft:Draft;amount:string;include:boolean};

const labels={expense:T('Money paid'),income:T('Money received'),bill:T('Bill still to pay')};

export default function CompetitionDemo(){
  useI18n();
  const [data,setData]=useState<Preview|null>(null);
  const [error,setError]=useState('');
  const [attempt,setAttempt]=useState(0);
  const [rows,setRows]=useState<Row[]|null>(null);
  const [confirmed,setConfirmed]=useState(false);
  const [scenario,setScenario]=useState<'habit'|'overdue'>('habit');
  useEffect(()=>{
    const controller=new AbortController();
    void accountRequest<Preview>('/competition/demo',undefined,controller.signal).then(setData).catch(()=>{
      if(!controller.signal.aborted)setError(t('The sample could not load. Try again in a moment.'));
    });
    return ()=>controller.abort();
  },[attempt]);

  function update(index:number,patch:Partial<Row>){
    setRows(current=>current?.map((row,i)=>i===index?{...row,...patch}:row)??null);
    setConfirmed(false);
  }
  const picked=rows?.filter(row=>row.include)??[];
  let net=0;
  let valid=true;
  for(const row of picked){
    try{
      const amount=parseMinor(row.amount,data!.currency);
      if(amount<=0)valid=false;
      if(row.draft.entry_type!=='bill')net+=row.draft.entry_type==='income'?amount:-amount;
    }catch{valid=false;}
  }

  return <main className="competition-demo">
    <header className="competition-header">
      <Brand/>
      <div className="actions"><LanguagePicker compact id="language-demo"/><ThemeButton/><a href="/" className="button secondary">{t('Open workspace')}</a></div>
    </header>
    <h1>{t('Try Capzoryx with a sample business')}</h1>
    <p className="muted">{t('Review a shop owner’s voice note and see how a late customer payment changes the cash outlook. The sample uses fictional records and needs no account.')}</p>
    {!data&&<section className="panel">
      {error?<><p role="alert">{error}</p><button onClick={()=>{setError('');setAttempt(n=>n+1);}}>{t('Try again')}</button></>
        :<p role="status">{t('Loading the sample business…')}</p>}
    </section>}
    {data&&<>
      <section className="panel" aria-labelledby="demo-voice-heading">
        <h2 id="demo-voice-heading">{t('From voice note to drafts')}</h2>
        <label htmlFor="demo-note">{t('Sample Banglish transcript')}</label>
        <textarea id="demo-note" rows={3} value={data.note} readOnly/>
        {!rows?<button onClick={()=>setRows(data.voice.drafts.map(draft=>({draft,amount:(draft.amount_minor/100).toFixed(2),include:!draft.needs_review})))}>{t('Make drafts')}</button>
          :<>
            <ol className="batch-list">{rows.map(({draft,amount,include},i)=><li key={i}>
              <label className="check"><input type="checkbox" checked={include} onChange={e=>update(i,{include:e.target.checked})}/>
                <b>{draft.title||t(labels[draft.entry_type])}</b></label>
              <p className="batch-quote">“{draft.evidence}”</p>
              <div className="competition-draft"><span>{t(labels[draft.entry_type])} · {formatDate(draft.effective_on)}</span>
                <label>{t('Amount ({currency})',{currency:data.currency})}<input inputMode="decimal" value={amount} onChange={e=>update(i,{amount:e.target.value})}/></label>
              </div>
            </li>)}</ol>
            {data.voice.dropped.filter(item=>item.reason==='NOT_PAID').map(item=><p key={item.evidence} className="notice">
              <b>{t('Skipped because the money did not move')}</b> · “{item.evidence}”
            </p>)}
            <div className="actions">
              <button disabled={!picked.length||!valid||confirmed} onClick={()=>setConfirmed(true)}>{t('Confirm sample drafts')}</button>
              {valid&&picked.length>0&&<span>{t('Net cash movement: {amount}',{amount:money(net,data.currency)})}</span>}
            </div>
            {confirmed&&<p className="success" role="status">{t('{count} sample drafts reviewed. Open a workspace to save your own records.',{count:picked.length})}</p>}
          </>}
      </section>
      <div className="actions competition-scenarios" role="group" aria-label={t('Cash radar scenarios')}>
        <button className={scenario==='habit'?'':'secondary'} aria-pressed={scenario==='habit'} onClick={()=>setScenario('habit')}>{t('Customer usually pays late')}</button>
        <button className={scenario==='overdue'?'':'secondary'} aria-pressed={scenario==='overdue'} onClick={()=>setScenario('overdue')}>{t('Overdue payment may still arrive')}</button>
      </div>
      <CashRadarView data={data.radar[scenario]}/>
    </>}
  </main>;
}
