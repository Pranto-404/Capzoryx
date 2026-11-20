import {useState,type FormEvent} from 'react';
import {ApiError} from './api';
import {useCurrency} from './Currency';
import {formatDate} from './format';
import {t,T} from './i18n';

type Request=<R,>(path:string,body?:unknown)=>Promise<R>;
type Row={line:number;day:string|null;signed:number|null;status:'new'|'duplicate'|'review'|'blocked'|'saved';reason:string|null;review:unknown;signature?:string};
type Manifest={rows_total:number;rows_review:number;rows_duplicate:number;currency:string};
type Preview={file:Manifest;import_id:string;rows:Row[];imported_count:number};
const reasons:Record<string,string>={
  ALREADY_IMPORTED:T('Already imported'), UNREADABLE_ROW:T('Check the date, currency and amount.'),
  BALANCE_DISCONTINUITY:T('The change in running balance differs from this amount.'),
  REPEATED_IDENTITY_IN_FILE:T('Multiple rows have the same transaction identity.'),
  REFERENCE_CONFLICT:T('This reference was previously imported with different details.'),
  DATES_OUT_OF_ORDER:T('Statement dates are out of order.'),
  DATE_OUTSIDE_WORKSPACE:T('Date is outside your workspace period.'),
  SIMILAR_CASH_ENTRY:T('A cash entry has the same date and amount.'),
};
const errors:Record<string,string>={
  STATEMENT_HEADERS_UNKNOWN:T('The statement needs a date column and an amount, debit or credit column.'),
  STATEMENT_PDF_TEXT_REQUIRED:T('Choose a PDF with selectable table text or use a CSV export.'),
  STATEMENT_USE_ONE_SHEET:T('Export one visible worksheet at a time.'),
  STATEMENT_VERIFY_DISTINCT:T('A matching cash entry appeared. Preview the statement again.'),
  STATEMENT_MAPPING_CHANGED:T('Use the same account label and date format as the original import.'),
  STATEMENT_READER_LIMIT:T('This file exceeds the reader limits. Export a smaller statement.'),
  STATEMENT_SIZE_LIMIT:T('This file exceeds the reader limits. Export a smaller statement.'),
  STATEMENT_PDF_PAGE_LIMIT:T('PDF statements can contain up to 30 pages.'),
};
function errorMessage(error:unknown){
  return error instanceof ApiError&&errors[error.code]?t(errors[error.code]):error instanceof Error?error.message:t('Request failed.');
}

async function readFile(file:File){
  if(file.size>3144000)throw new Error(t('Choose a statement smaller than 3 MiB.'));
  const url=await new Promise<string>((resolve,reject)=>{
    const reader=new FileReader();
    reader.onload=()=>resolve(String(reader.result));reader.onerror=()=>reject(new Error(t('The file could not be read.')));
    reader.readAsDataURL(file);
  });
  return url.slice(url.indexOf(',')+1);
}

export default function StatementImport({request,onSaved}:{request:Request;onSaved:()=>Promise<void>}){
  const {currency,nativeMoney}=useCurrency();
  const [bank,setBank]=useState('');
  const [file,setFile]=useState<File|null>(null);
  const [order,setOrder]=useState('DMY');
  const [preview,setPreview]=useState<Preview|null>(null);
  const [selected,setSelected]=useState<Set<number>>(new Set());
  const [page,setPage]=useState(0),[busy,setBusy]=useState(false);
  const [notice,setNotice]=useState(''),[error,setError]=useState('');
  function reset(){setPreview(null);setSelected(new Set());setError('');setNotice('');setPage(0);}
  async function inspect(e:FormEvent){
    e.preventDefault();if(!file||busy)return;
    const layout=file.name.split('.').pop()?.toLowerCase();
    if(!layout||!['csv','pdf','xlsx'].includes(layout)){setError(t('Choose a CSV, XLSX or PDF file.'));return;}
    setBusy(true);reset();
    try{
      const data=await request<Preview>('/statements/preview',{layout,currency,date_order:order,account_label:bank,data:await readFile(file)});
      setPreview(data);
    }catch(e){setError(errorMessage(e));}
    finally{setBusy(false);}
  }
  async function save(){
    if(!preview||busy||!selected.size)return;
    setBusy(true);setError('');
    let imported=0;
    try{
      for(const row of preview.rows.filter(r=>selected.has(r.line))){
        await request('/statements/confirm',{file:preview.file,import_id:preview.import_id,row:row.review,signature:row.signature,verified_distinct:row.status==='review'});
        imported++;
        setPreview(prior=>prior?{...prior,rows:prior.rows.map(item=>item.line===row.line?{...item,status:'saved'}:item)}:null);
        setSelected(prior=>{const next=new Set(prior);next.delete(row.line);return next;});
        setNotice(t('Rows recorded: {count}',{count:imported}));
      }
    }catch(e){setError(errorMessage(e));}
    finally{try{if(imported)await onSaved();}finally{setBusy(false);}}
  }
  const pageSize=25;
  const visible=preview?.rows.slice(page*pageSize,(page+1)*pageSize)||[];
  return <details className="panel data-entry"><summary>{t('Import a bank or wallet statement')}</summary>
    <p className="muted">{t('Preview up to 20,000 transactions. Select the cash entries to add. The original file and its descriptions are discarded after the preview.')}</p>
    <form onSubmit={inspect}>
      <label>{t('Account label')}<input required maxLength={64} value={bank} disabled={busy} onChange={e=>{reset();setBank(e.target.value);}}/></label>
      <p className="small muted">{t('Use the same nickname each time you import this account. Leave out account numbers.')}</p>
      <label>{t('Date format')}<select value={order} disabled={busy} onChange={e=>{reset();setOrder(e.target.value);}}>
        <option value="DMY">{t('Day / month / year')}</option><option value="MDY">{t('Month / day / year')}</option></select></label>
      <label>{t('Statement file')} ({currency})<input type="file" accept=".csv,.xlsx,.pdf" required disabled={busy} onChange={e=>{reset();setFile(e.target.files?.[0]||null);}}/></label>
      <button disabled={busy||!file||!bank.trim()}>{t('Preview statement')}</button>
    </form>
    {preview&&<>
      <p>{t('{count} rows · {duplicate} already imported · {review} need review',{count:preview.file.rows_total,duplicate:preview.file.rows_duplicate,review:preview.file.rows_review})}</p>
      <button type="button" className="secondary" disabled={busy} onClick={()=>setSelected(prior=>new Set([...prior,...visible.filter(r=>r.status==='new').map(r=>r.line)]))}>{t('Select new rows on this page')}</button>
      <ul className="people">{visible.map(row=><li key={row.line}><label className="check"><input type="checkbox" disabled={busy||!['new','review'].includes(row.status)}
        checked={selected.has(row.line)} onChange={e=>{const checked=e.target.checked;setSelected(prior=>{const next=new Set(prior);if(checked)next.add(row.line);else next.delete(row.line);return next;});}}/>
        <span><strong>{t('Row {line}',{line:row.line})} · {row.signed!==null?nativeMoney(row.signed):t('Check source row')}</strong>
          <small>{row.day&&formatDate(row.day)} {row.status==='saved'?t('Recorded'):row.reason?t(reasons[row.reason]||row.reason):''}</small>
          {row.status==='review'&&<small>{t('Select only if you verified that this is a separate transaction.')}</small>}</span></label></li>)}</ul>
      <div className="form-row"><button type="button" className="secondary" disabled={busy||!page} onClick={()=>setPage(page-1)}>{t('Previous page')}</button>
        <button type="button" className="secondary" disabled={busy||(page+1)*pageSize>=preview.rows.length} onClick={()=>setPage(page+1)}>{t('Next page')}</button>
        <button type="button" disabled={busy||!selected.size} onClick={()=>void save()}>{t('Record {count} selected rows',{count:selected.size})}</button></div>
    </>}
    {notice&&<p role="status">{notice}</p>}{error&&<p className="error" role="alert">{error}</p>}
  </details>;
}
