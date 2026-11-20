import {useEffect, useState} from 'react';
import {t, useI18n} from './i18n';
import {currencyDigits} from './api';
import {formatDate, formatTime} from './format';

type Link = {id: string; expires_at: number};
type Send = <T>(path: string, body?: unknown) => Promise<T>;
type Summary = {id:string; key_id:string; format:string; start:string; as_of:string; issued_at:number; expires_at:number;
  currency:string; balance_minor:number; receipts_minor:number; expenses_minor:number};

export function PassportManager({request}: {request: Send}) {
  const [links, setLinks] = useState<Link[]>([]);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  useEffect(() => {
    let current = true;
    request<{passports:Link[]}>('/passport/list').then(result => {if (current) setLinks(result.passports);})
      .catch(() => {if (current) setError(t('Could not load passport links.'));}).finally(() => {if (current) setLoading(false);});
    return () => {current = false;};
  }, []); // WorkspaceContent remounts when the workspace or member changes.

  async function change(id?:string) {
    setBusy(true);
    setError('');
    try {
      if (id) {
        await request('/passport/revoke', {id});
        setLinks(rows => rows.filter(row => row.id !== id));
      } else {
        const link = await request<Link>('/passport/create', {});
        setLinks(rows => [link, ...rows]);
      }
    } catch {setError(t('Could not update the passport. Check your connection and signing configuration.'));}
    finally {setBusy(false);}
  }
  return <section className="panel"><h2>{t('Cash-flow passport')}</h2>
    <p>{t('Anyone with the link can see the cash balance and recent receipt and expense totals. Links expire after 90 days and can be revoked here.')}</p>
    <button disabled={busy || loading} onClick={() => void change()}>{t('Create a signed passport')}</button>
    {error && <p role="alert">{error}</p>}
    <ul>{links.map(link => <li key={link.id}><a href={'/verify/' + link.id} target="_blank" rel="noreferrer">{t('View passport')}</a>
      {' · '}{t('Expires {time}', {time:formatTime(link.expires_at)})}{' '}
      <button className="secondary small" disabled={busy} onClick={() => void change(link.id)}>{t('Revoke link')}</button></li>)}</ul>
  </section>;
}

const bytes = (value:string) => Uint8Array.from(atob(value), char => char.charCodeAt(0));

async function readVerified(id:string, signal:AbortSignal):Promise<Summary> {
  const [data, keys] = await Promise.all([
    fetch('/api/public/passport/' + id, {credentials:'omit', cache:'no-store', signal}),
    fetch('/.well-known/capzoryx-passport-key.json', {credentials:'omit', cache:'no-store', signal})
  ]);
  if (!data.ok || !keys.ok) throw Error();
  const {canonical, signature} = await data.json();
  const summary = JSON.parse(canonical) as Summary;
  const raw = (await keys.json())[summary.key_id];
  const key = await crypto.subtle.importKey('raw', bytes(raw), {name:'Ed25519'}, false, ['verify']);
  if (!await crypto.subtle.verify('Ed25519', key, bytes(signature), new TextEncoder().encode(canonical))
    || summary.id !== id || summary.format !== 'capzoryx-passport-v1' || summary.expires_at * 1000 <= Date.now()) throw Error();
  return summary;
}

export function VerifyPassport({id}: {id:string}) {
  useI18n();
  const [summary, setSummary] = useState<Summary|null>(null);
  const [failed, setFailed] = useState(false);
  const [qr, setQr] = useState('');
  useEffect(() => {
    const ctrl = new AbortController();
    readVerified(id, ctrl.signal).then(report => {
      if (!ctrl.signal.aborted) setSummary(report);
    }).catch(() => {if (!ctrl.signal.aborted) setFailed(true);});
    import('qrcode').then(q => q.toDataURL(location.origin + '/verify/' + id)).then(url => {
      if (!ctrl.signal.aborted) setQr(url);
    }).catch(() => {});
    return () => ctrl.abort();
  }, [id]);
  const money = (minor:number) => new Intl.NumberFormat(document.documentElement.lang, {
    style:'currency', currency:summary!.currency
  }).format(minor / 10 ** currencyDigits(summary!.currency));
  return <main className="passport-page"><article className="panel">
    <p className="eyebrow">Capzoryx</p><h1>{t('Cash-flow passport')}</h1>
    {summary ? <>
      <p className="success">{t('Signature verified')}</p>
      <p>{formatDate(summary.start)} — {formatDate(summary.as_of)}</p>
      <dl>{[[t('Cash balance'),summary.balance_minor],[t('Money received'),summary.receipts_minor],[t('Money spent'),summary.expenses_minor]].map(([label,amount]) =>
        <div key={label}><dt>{label}</dt><dd>{money(Number(amount))}</dd></div>)}</dl>
      <p>{t('Based on records entered in the workspace. This document does not verify bank balances or creditworthiness.')}</p>
      <p>{t('Expires {time}', {time:formatTime(summary.expires_at)})}</p>
      {qr && <img src={qr} width="150" height="150" alt={t('QR code to check the current passport')}/>}
      <button className="secondary passport-print" onClick={() => window.print()}>{t('Print or save PDF')}</button>
    </> : <p role="status">{failed ? t('This passport could not be verified. It may have expired or been revoked.') : t('Verifying signature…')}</p>}
  </article></main>;
}
