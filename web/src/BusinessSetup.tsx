import {useEffect,useMemo,useRef,useState} from 'react';
import {money} from './api';
import {t,T} from './i18n';

type Request=<R,>(path:string,body?:unknown)=>Promise<R>;
type Industry={key:string;label:string;niches:string[];words:string};
type Catalog={industries:Industry[];business_types:string[];channels:string[];goals:string[];units:string[]};
type Product={id:string;name:string;category:string;variant:string;brand:string;unit:string;quantity:string|null;cost_minor:number|null;price_minor:number|null;market_key:string|null};
type Profile={identity?:Record<string,unknown>;operations?:Record<string,unknown>;goals?:Record<string,unknown>;consent?:Record<string,unknown>};
export type BusinessView={profile:Profile;step:number;completed:boolean;products:Product[];gaps:{field:string;why:string}[];currency:string;niche_category:string|null};

const STEPS=[T('Business'),T('Products'),T('Operations'),T('Goals'),T('Permissions')];
const KEYS=['identity','products','operations','goals','consent'];
const TYPE_LABEL:Record<string,string>={retail:T('Retail'),wholesale:T('Wholesale'),manufacturing:T('Manufacturing'),service:T('Service'),distribution:T('Distribution'),online:T('Online')};
const CHANNEL_LABEL:Record<string,string>={shop:T('Shop or showroom'),facebook:T('Facebook page'),website:T('Website'),marketplace:T('Marketplace (Daraz etc.)'),whatsapp:T('WhatsApp'),phone:T('Phone orders'),wholesale:T('Wholesale buyers'),field_sales:T('Field sales')};
const GOAL_LABEL:Record<string,string>={profit:T('Increase profit'),sales:T('Grow sales'),costs:T('Reduce costs'),compete:T('Compete better'),new_markets:T('Reach new markets'),inventory:T('Manage stock better'),protect_capital:T('Protect capital from price swings'),retention:T('Keep customers coming back'),grow_lean:T('Grow without much new investment')};
const MONEY_FIELDS:[string,string][]=[['monthly_revenue_minor',T('Monthly sales')],['monthly_expenses_minor',T('Monthly expenses')],['monthly_profit_minor',T('Monthly profit')],['working_capital_minor',T('Working capital now')],['inventory_value_minor',T('Stock value now')],['investment_minor',T('Starting investment')],['growth_budget_minor',T('Budget for growth')]];

const toMinor=(v:string)=>{const n=Number(v.replace(/,/g,''));return v.trim()&&Number.isFinite(n)?Math.round(n*100):null;};
const fromMinor=(v:unknown)=>typeof v==='number'?String(v/100):'';
const list=(v:string)=>v.split(/[,\n]/).map(x=>x.trim()).filter(Boolean);
const joined=(v:unknown)=>Array.isArray(v)?v.join(', '):'';
const str=(v:unknown)=>typeof v==='string'?v:'';
const errorText=(e:unknown)=>e instanceof Error?e.message:t('Request failed.');

function suggestIndustry(niche:string,industries:Industry[]){
  const words=niche.toLowerCase().split(/[^\p{L}\p{N}]+/u).filter(w=>w.length>2);
  let best:Industry|null=null,score=0;
  for(const ind of industries){
    const vocab=(ind.label+' '+ind.niches.join(' ')+' '+ind.words).toLowerCase();
    const hits=words.filter(w=>vocab.includes(w)).length;
    if(hits>score){best=ind;score=hits;}
  }
  return best;
}

/** Business setup: five short steps that each save on their own. `edit` opens any step from Settings. */
export function BusinessSetup({request,mode,onDone,onLater}:{request:Request;mode:'setup'|'edit';onDone:(view:BusinessView)=>void;onLater?:()=>void}){
  const [view,setView]=useState<BusinessView|null>(null);
  const [catalog,setCatalog]=useState<Catalog|null>(null);
  const [step,setStep]=useState(-1);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [saved,setSaved]=useState('');
  const heading=useRef<HTMLHeadingElement>(null);
  useEffect(()=>{void Promise.all([request<BusinessView>('/business'),request<Catalog>('/business/catalog')]).then(([v,c])=>{
    setView(v);setCatalog(c);setStep(mode==='edit'?0:v.step===0?-1:Math.min(v.step,4));}).catch(e=>setError(errorText(e)));},[]);// eslint-disable-line react-hooks/exhaustive-deps
  useEffect(()=>{heading.current?.focus();},[step]);
  async function save(name:string,body:unknown,next=true){
    setBusy(true);setError('');setSaved('');
    try{
      const v=await request<BusinessView>('/business/step/'+name,body);setView(v);
      if(mode==='edit'){setSaved(t('Saved.'));return;}
      if(!next)return;
      if(step===4){const done=await request<BusinessView>('/business/complete',{});onDone(done);}else setStep(step+1);
    }catch(e){setError(errorText(e));}finally{setBusy(false);}
  }
  if(!view||!catalog)return <div className={mode==='setup'?'biz-setup-overlay':undefined}><section className="panel biz-setup" role="status">{error||t('Loading…')}</section></div>;
  const body=step===-1?<Welcome start={()=>setStep(0)} later={onLater}/>:<>
    <div className="biz-progress" aria-label={t('Step {n} of {total}',{n:step+1,total:5})}>
      {STEPS.map((s,i)=><button key={s} type="button" className={i===step?'active':i<view.step?'done':''} disabled={mode==='setup'&&i>view.step}
        aria-current={i===step?'step':undefined} onClick={()=>setStep(i)}><span>{i+1}</span>{t(s)}</button>)}
    </div>
    <h2 tabIndex={-1} ref={heading}>{t(STEPS[step])}</h2>
    {step===0&&<IdentityStep key={'i'+view.step} catalog={catalog} value={view.profile.identity||{}} busy={busy} mode={mode} submit={b=>void save('identity',b)}/>}
    {step===1&&<ProductsStep view={view} catalog={catalog} request={request} setView={setView} busy={busy} mode={mode} next={()=>void save('products',{})}/>}
    {step===2&&<OperationsStep catalog={catalog} value={view.profile.operations||{}} currency={view.currency} busy={busy} mode={mode} submit={b=>void save('operations',b)}/>}
    {step===3&&<GoalsStep catalog={catalog} value={view.profile.goals||{}} currency={view.currency} busy={busy} mode={mode} submit={b=>void save('goals',b)}/>}
    {step===4&&<ConsentStep value={view.profile.consent||{}} busy={busy} mode={mode} submit={b=>void save('consent',b)}/>}
    {error&&<p className="error" role="alert">{error}</p>}
    {saved&&<p className="success" role="status">{saved}</p>}
    {mode==='setup'&&<div className="biz-nav">
      {step>0&&<button type="button" className="ghost" disabled={busy} onClick={()=>setStep(step-1)}>{t('Back')}</button>}
      {onLater&&<button type="button" className="link" onClick={onLater}>{t('Finish later')}</button>}
    </div>}
    {mode==='edit'&&!view.completed&&!!view.profile.identity&&<button type="button" className="secondary" disabled={busy} onClick={()=>void (async()=>{setBusy(true);setError('');
      try{const done=await request<BusinessView>('/business/complete',{});setView(done);setSaved(t('Your business profile is saved.'));onDone(done);}catch(e){setError(errorText(e));}finally{setBusy(false);}})()}>{t('Finish setup')}</button>}
    {mode==='edit'&&!!view.gaps.length&&<details className="biz-gaps"><summary>{t('{n} things would make the analysis more accurate',{n:view.gaps.length})}</summary>
      <ul>{view.gaps.map(g=><li key={g.field}>{g.why}</li>)}</ul></details>}
  </>;
  return mode==='setup'?<div className="biz-setup-overlay" role="dialog" aria-modal="true" aria-label={t('Set up your business')}><section className="panel biz-setup">{body}</section></div>
    :<section className="panel biz-setup biz-edit">{body}</section>;
}

function Welcome({start,later}:{start:()=>void;later?:()=>void}){
  return <div className="biz-welcome">
    <p className="eyebrow">{t('Your business assistant')}</p>
    <h1>{t('Tell us about your business once')}</h1>
    <p>{t('What you sell, where you sell it and what you want to achieve. Capzoryx uses this to follow your market, compare competitors, warn you about real risk using your own costs, and suggest next steps that fit your budget.')}</p>
    <ul className="biz-why">
      <li>{t('About 3 minutes. Only the first step is required; you can skip any numbers you do not know.')}</li>
      <li>{t('Each step is saved, so you can stop and continue later.')}</li>
      <li>{t('Your details are encrypted and visible only to the owner of this workspace.')}</li>
    </ul>
    <div className="actions"><button onClick={start}>{t('Set up my business')}</button>{later&&<button className="secondary" onClick={later}>{t('Not now')}</button>}</div>
  </div>;
}

function Chips({options,labels,value,onChange}:{options:string[];labels:Record<string,string>;value:string[];onChange:(v:string[])=>void}){
  return <div className="chips">{options.map(o=><label key={o} className={value.includes(o)?'chip on':'chip'}>
    <input type="checkbox" checked={value.includes(o)} onChange={()=>onChange(value.includes(o)?value.filter(x=>x!==o):[...value,o])}/>{t(labels[o]||o)}</label>)}</div>;
}

function Submit({busy,mode,last}:{busy:boolean;mode:'setup'|'edit';last?:boolean}){
  return <button className="biz-submit" disabled={busy}>{busy?t('Saving…'):mode==='edit'?t('Save'):last?t('Finish setup'):t('Save and continue')}</button>;
}

function IdentityStep({catalog,value,busy,mode,submit}:{catalog:Catalog;value:Record<string,unknown>;busy:boolean;mode:'setup'|'edit';submit:(b:unknown)=>void}){
  const [f,setF]=useState({name:str(value.name),industry:str(value.industry),niche:str(value.niche),country:str(value.country)||'Bangladesh',city:str(value.city),
    website:str(value.website),facebook:str(value.facebook),instagram:str(value.instagram),store:str(value.store),year:value.year_established?String(value.year_established):'',description:str(value.description)});
  const [types,setTypes]=useState<string[]>(Array.isArray(value.business_types)?value.business_types as string[]:[]);
  const set=(k:keyof typeof f)=>(e:{target:{value:string}})=>setF({...f,[k]:e.target.value});
  const guess=useMemo(()=>f.niche.length>2?suggestIndustry(f.niche,catalog.industries):null,[f.niche,catalog]);
  const niches=useMemo(()=>{const chosen=catalog.industries.find(i=>i.key===f.industry);return chosen?.niches.length?chosen.niches:catalog.industries.flatMap(i=>i.niches);},[f.industry,catalog]);
  return <form onSubmit={e=>{e.preventDefault();submit({name:f.name,industry:f.industry,niche:f.niche,business_types:types,country:f.country,city:f.city,website:f.website,
    facebook:f.facebook,instagram:f.instagram,store:f.store,year_established:f.year?Number(f.year):null,description:f.description});}}>
    <div className="form-row">
      <label>{t('Business name')}<input required minLength={2} maxLength={80} value={f.name} onChange={set('name')} placeholder="Golden Heritage BD"/></label>
      <label>{t('What exactly do you do?')}<input required minLength={2} maxLength={80} list="biz-niches" value={f.niche} onChange={set('niche')} placeholder={t('e.g. Gold trading and jewelry retail')}/></label>
    </div>
    <datalist id="biz-niches">{niches.map(n=><option key={n} value={n}/>)}</datalist>
    <label>{t('Industry')}<select required value={f.industry} onChange={set('industry')}><option value="">{t('Choose…')}</option>
      {catalog.industries.map(i=><option key={i.key} value={i.key}>{t(i.label)}</option>)}</select></label>
    {guess&&guess.key!==f.industry&&<p className="biz-hint">{t('Sounds like {industry}.',{industry:t(guess.label)})} <button type="button" className="link" onClick={()=>setF({...f,industry:guess.key})}>{t('Use this')}</button></p>}
    <fieldset className="biz-field"><legend>{t('How do you sell?')}</legend><Chips options={catalog.business_types} labels={TYPE_LABEL} value={types} onChange={setTypes}/></fieldset>
    <div className="form-row">
      <label>{t('Country')}<input required minLength={2} maxLength={60} value={f.country} onChange={set('country')}/></label>
      <label>{t('City or area')}<input required minLength={2} maxLength={80} value={f.city} onChange={set('city')} placeholder={t('e.g. Dhaka')}/></label>
    </div>
    <details className="biz-more" open={!!(f.website||f.facebook||f.description)}><summary>{t('Website, pages and description (optional)')}</summary>
      <div className="form-row">
        <label>{t('Website')}<input inputMode="url" maxLength={200} value={f.website} onChange={set('website')} placeholder="example.com"/></label>
        <label>{t('Facebook page')}<input inputMode="url" maxLength={200} value={f.facebook} onChange={set('facebook')} placeholder="facebook.com/yourpage"/></label>
      </div>
      <div className="form-row">
        <label>{t('Instagram')}<input inputMode="url" maxLength={200} value={f.instagram} onChange={set('instagram')}/></label>
        <label>{t('Online store')}<input inputMode="url" maxLength={200} value={f.store} onChange={set('store')}/></label>
        <label>{t('Year started')}<input inputMode="numeric" maxLength={4} value={f.year} onChange={set('year')}/></label>
      </div>
      <label>{t('Short description')}<textarea maxLength={600} rows={3} value={f.description} onChange={set('description')}/></label>
    </details>
    <Submit busy={busy||!types.length} mode={mode}/>
    {!types.length&&<p className="muted">{t('Choose at least one way you sell.')}</p>}
  </form>;
}

function ProductsStep({view,catalog,request,setView,busy,mode,next}:{view:BusinessView;catalog:Catalog;request:Request;setView:(v:BusinessView)=>void;busy:boolean;mode:'setup'|'edit';next:()=>void}){
  const blank={name:'',category:'',variant:'',unit:'',quantity:'',cost:'',price:''};
  const [f,setF]=useState(blank);
  const [editing,setEditing]=useState<string|null>(null);
  const [working,setWorking]=useState(false);
  const [note,setNote]=useState('');
  const [error,setError]=useState('');
  const c=view.currency;
  const set=(k:keyof typeof f)=>(e:{target:{value:string}})=>setF({...f,[k]:e.target.value});
  async function act(fn:()=>Promise<BusinessView>,done?:string){
    setWorking(true);setError('');setNote('');
    try{setView(await fn());if(done)setNote(done);}catch(e){setError(errorText(e));}finally{setWorking(false);}
  }
  const payload=()=>({name:f.name,category:f.category,variant:f.variant,unit:f.unit,quantity:f.quantity.trim()?f.quantity.replace(/,/g,''):null,cost_minor:toMinor(f.cost),price_minor:toMinor(f.price)});
  return <div>
    <p className="muted">{t('Add what you sell. Purchase cost and selling price are optional, but they let Capzoryx work out your real profit and break-even price.')}</p>
    {!!view.products.length&&<div className="table-wrap"><table className="biz-products"><thead><tr><th>{t('Product')}</th><th>{t('Quantity')}</th><th>{t('Cost')}</th><th>{t('Price')}</th><th/></tr></thead>
      <tbody>{view.products.map(p=><tr key={p.id}><td><b>{p.name}</b><small>{[p.category,p.variant].filter(Boolean).join(' · ')}{p.market_key&&<span className="pill">{t('Market price tracked')}</span>}</small></td>
        <td>{p.quantity?`${p.quantity} ${p.unit}`:p.unit||'—'}</td><td className="amount">{p.cost_minor==null?<span className="muted">{t('Not set')}</span>:money(p.cost_minor,c)}</td>
        <td className="amount">{p.price_minor==null?<span className="muted">{t('Not set')}</span>:money(p.price_minor,c)}</td>
        <td><button type="button" className="ghost small-button" onClick={()=>{setEditing(p.id);setF({name:p.name,category:p.category,variant:p.variant,unit:p.unit,quantity:p.quantity||'',cost:fromMinor(p.cost_minor),price:fromMinor(p.price_minor)});}}>{t('Edit')}</button>
          <button type="button" className="ghost small-button" disabled={working} onClick={()=>void act(()=>request<BusinessView>(`/business/products/${p.id}/delete`,{}))}>{t('Remove')}</button></td></tr>)}</tbody></table></div>}
    <form className="biz-product-form" onSubmit={e=>{e.preventDefault();void act(()=>request<BusinessView>(editing?`/business/products/${editing}`:'/business/products',payload()),editing?t('Product updated.'):t('{name} added.',{name:f.name})).then(()=>{setF(blank);setEditing(null);});}}>
      <div className="form-row">
        <label>{t('Product or service')}<input required maxLength={80} value={f.name} onChange={set('name')} placeholder={t('e.g. 22K Gold')}/></label>
        <label>{t('Category')}<input maxLength={80} value={f.category} onChange={set('category')} placeholder={t('e.g. Gold')}/></label>
        <label>{t('Unit')}<input maxLength={20} list="biz-units" value={f.unit} onChange={set('unit')} placeholder="bhori"/></label>
      </div>
      <datalist id="biz-units">{catalog.units.map(u=><option key={u} value={u}/>)}</datalist>
      <div className="form-row">
        <label>{t('Quantity in stock')}<input inputMode="decimal" value={f.quantity} onChange={set('quantity')}/></label>
        <label>{t('Purchase cost per unit ({currency})',{currency:c})}<input inputMode="decimal" value={f.cost} onChange={set('cost')} placeholder={t('optional')}/></label>
        <label>{t('Selling price per unit ({currency})',{currency:c})}<input inputMode="decimal" value={f.price} onChange={set('price')} placeholder={t('optional')}/></label>
      </div>
      <div className="actions"><button className="secondary" disabled={working||!f.name.trim()}>{editing?t('Update product'):t('Add product')}</button>
        {editing&&<button type="button" className="ghost" onClick={()=>{setEditing(null);setF(blank);}}>{t('Cancel')}</button>}
        <label className="button-like secondary">{t('Import Excel/CSV')}<input type="file" accept=".csv,text/csv" hidden onChange={e=>{const file=e.target.files?.[0];e.target.value='';if(!file)return;
          void file.text().then(text=>act(async()=>{const r=await request<BusinessView&{added:number;skipped:{row:number;reason:string}[]}>('/business/import',{csv:text});
            setNote(t('{added} added, {skipped} skipped.',{added:r.added,skipped:r.skipped.length}));return r;}));}}/></label></div>
      <small className="muted">{t('For Excel, save the sheet as CSV first. Columns: Product, Category, Unit, Quantity, Cost, Price.')}</small>
    </form>
    {note&&<p className="success" role="status">{note}</p>}
    {error&&<p className="error" role="alert">{error}</p>}
    {mode==='setup'&&<button type="button" className="biz-submit" disabled={busy||working} onClick={next}>{view.products.length?t('Save and continue'):t('Skip for now')}</button>}
  </div>;
}

function OperationsStep({catalog,value,currency,busy,mode,submit}:{catalog:Catalog;value:Record<string,unknown>;currency:string;busy:boolean;mode:'setup'|'edit';submit:(b:unknown)=>void}){
  const [modeOf,setMode]=useState(str(value.mode));
  const [channels,setChannels]=useState<string[]>(Array.isArray(value.channels)?value.channels as string[]:[]);
  const [f,setF]=useState({customers:joined(value.customers),locations:joined(value.locations),competitors:joined(value.competitors),suppliers:joined(value.suppliers),branches:value.branches==null?'':String(value.branches)});
  const [expenses,setExpenses]=useState<{name:string;amount:string}[]>(Array.isArray(value.expenses)?(value.expenses as {name:string;monthly_minor:number}[]).map(x=>({name:x.name,amount:fromMinor(x.monthly_minor)})):[]);
  const set=(k:keyof typeof f)=>(e:{target:{value:string}})=>setF({...f,[k]:e.target.value});
  return <form onSubmit={e=>{e.preventDefault();submit({mode:modeOf||null,channels,customers:list(f.customers),locations:list(f.locations),competitors:list(f.competitors),suppliers:list(f.suppliers),
    branches:f.branches?Number(f.branches):null,expenses:expenses.filter(x=>x.name.trim()&&toMinor(x.amount)!=null).map(x=>({name:x.name.trim(),monthly_minor:toMinor(x.amount)}))});}}>
    <fieldset className="biz-field"><legend>{t('Where do you sell?')}</legend><div className="chips">{(['offline','online','hybrid'] as const).map(m=><label key={m} className={modeOf===m?'chip on':'chip'}>
      <input type="radio" name="biz-mode" checked={modeOf===m} onChange={()=>setMode(m)}/>{m==='offline'?t('In person'):m==='online'?t('Online'):t('Both')}</label>)}</div></fieldset>
    <fieldset className="biz-field"><legend>{t('Sales channels')}</legend><Chips options={catalog.channels} labels={CHANNEL_LABEL} value={channels} onChange={setChannels}/></fieldset>
    <div className="form-row">
      <label>{t('Who are your customers?')}<input value={f.customers} onChange={set('customers')} placeholder={t('e.g. families, wedding buyers, shops')}/></label>
      <label>{t('Areas you serve')}<input value={f.locations} onChange={set('locations')} placeholder={t('e.g. Dhanmondi, Mirpur')}/></label>
      <label>{t('Branches')}<input inputMode="numeric" value={f.branches} onChange={set('branches')}/></label>
    </div>
    <label>{t('Competitors you know')}<input value={f.competitors} onChange={set('competitors')} placeholder={t('Names separated by commas')}/></label>
    <label>{t('Main suppliers (optional)')}<input value={f.suppliers} onChange={set('suppliers')}/></label>
    <fieldset className="biz-field"><legend>{t('Regular monthly expenses ({currency})',{currency})}</legend>
      {expenses.map((x,i)=><div key={i} className="biz-expense"><input aria-label={t('Expense')} value={x.name} placeholder={t('e.g. Shop rent')} onChange={e=>setExpenses(expenses.map((y,j)=>j===i?{...y,name:e.target.value}:y))}/>
        <input aria-label={t('Amount')} inputMode="decimal" value={x.amount} onChange={e=>setExpenses(expenses.map((y,j)=>j===i?{...y,amount:e.target.value}:y))}/>
        <button type="button" className="ghost small-button" aria-label={t('Remove')} onClick={()=>setExpenses(expenses.filter((_,j)=>j!==i))}>×</button></div>)}
      <button type="button" className="secondary small-button" onClick={()=>setExpenses([...expenses,{name:'',amount:''}])}>{t('Add an expense')}</button></fieldset>
    <Submit busy={busy} mode={mode}/>
  </form>;
}

function GoalsStep({catalog,value,currency,busy,mode,submit}:{catalog:Catalog;value:Record<string,unknown>;currency:string;busy:boolean;mode:'setup'|'edit';submit:(b:unknown)=>void}){
  const [goals,setGoals]=useState<string[]>(Array.isArray(value.goals)?value.goals as string[]:[]);
  const [nums,setNums]=useState<Record<string,string>>(Object.fromEntries(MONEY_FIELDS.map(([k])=>[k,fromMinor(value[k])])));
  const [challenges,setChallenges]=useState(str(value.challenges));
  return <form onSubmit={e=>{e.preventDefault();submit({goals,challenges,...Object.fromEntries(MONEY_FIELDS.map(([k])=>[k,toMinor(nums[k])]))});}}>
    <fieldset className="biz-field"><legend>{t('What matters most right now?')}</legend><Chips options={catalog.goals} labels={GOAL_LABEL} value={goals} onChange={setGoals}/></fieldset>
    <details className="biz-more" open={MONEY_FIELDS.some(([k])=>nums[k])}><summary>{t('Your numbers (optional, rough is fine)')}</summary>
      <div className="biz-money">{MONEY_FIELDS.map(([k,label])=><label key={k}>{t(label)} ({currency})<input inputMode="decimal" value={nums[k]} onChange={e=>setNums({...nums,[k]:e.target.value})}/></label>)}</div>
    </details>
    <label>{t('Biggest challenge right now (optional)')}<textarea rows={2} maxLength={600} value={challenges} onChange={e=>setChallenges(e.target.value)}/></label>
    <Submit busy={busy} mode={mode}/>
  </form>;
}

function ConsentStep({value,busy,mode,submit}:{value:Record<string,unknown>;busy:boolean;mode:'setup'|'edit';submit:(b:unknown)=>void}){
  const [f,setF]=useState({personalized_ai:value.personalized_ai!==false,external_research:!!value.external_research,monitoring:!!value.monitoring,alerts:!!value.alerts});
  const rows:[keyof typeof f,string,string][]=[
    ['personalized_ai',T('Use my business details for personal advice'),T('The assistant reads your profile and products to tailor answers. Nothing is shared with other users.')],
    ['external_research',T('Research my market and competitors online'),T('Only public information is searched: your industry, area and competitor names. Your costs and sales are never sent.')],
    ['monitoring',T('Keep watching market prices for me'),T('Prices linked to your products are checked in the background, even when you are signed out.')],
    ['alerts',T('Send me important alerts automatically'),T('Warnings go to the channels you turn on (Telegram, phone, email) without asking each time. Nothing is ever bought, sold or paid automatically.')],
  ];
  return <form onSubmit={e=>{e.preventDefault();submit(f);}}>
    <p className="muted">{t('Your details are stored encrypted in this workspace. You can change these choices any time in Settings → Business.')}</p>
    {rows.map(([k,title,help])=><label key={k} className="switch-row"><input type="checkbox" checked={f[k]} onChange={e=>setF({...f,[k]:e.target.checked})}/>
      <span><b>{t(title)}</b><small>{t(help)}</small></span></label>)}
    <Submit busy={busy} mode={mode} last/>
  </form>;
}
