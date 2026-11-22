import {useEffect,useMemo,useRef,useState,type KeyboardEvent} from 'react';
import {Icon} from './Icon';
import {t} from './i18n';

export type PaletteItem={id:string;label:string;icon:string;run:()=>void};

/** Ctrl/⌘+K quick jump: type a few letters of a page or action and press Enter. */
export function CommandPalette({open,items,onClose}:{open:boolean;items:PaletteItem[];onClose:()=>void}){
  const [query,setQuery]=useState('');
  const [active,setActive]=useState(0);
  const input=useRef<HTMLInputElement>(null);
  useEffect(()=>{if(open){setQuery('');setActive(0);window.setTimeout(()=>input.current?.focus(),0);}},[open]);
  const shown=useMemo(()=>{
    const q=query.trim().toLowerCase();
    return q?items.filter(i=>i.label.toLowerCase().includes(q)):items;
  },[query,items]);
  if(!open)return null;
  const choose=(item?:PaletteItem)=>{if(!item)return;onClose();item.run();};
  const onKey=(e:KeyboardEvent)=>{
    if(e.key==='Escape'){e.preventDefault();onClose();}
    else if(e.key==='ArrowDown'){e.preventDefault();setActive(a=>Math.min(a+1,shown.length-1));}
    else if(e.key==='ArrowUp'){e.preventDefault();setActive(a=>Math.max(a-1,0));}
    else if(e.key==='Enter'){e.preventDefault();choose(shown[active]);}
  };
  return <div className="palette-backdrop" onClick={onClose}>
    <div className="palette" role="dialog" aria-modal="true" aria-label={t('Find a page or action')} onClick={e=>e.stopPropagation()} onKeyDown={onKey}>
      <div className="palette-search"><Icon name="search"/><input ref={input} value={query} placeholder={t('Where do you want to go?')}
        aria-label={t('Find a page or action')} onChange={e=>{setQuery(e.target.value);setActive(0);}}/><kbd>Esc</kbd></div>
      <ul role="listbox">{shown.map((item,i)=><li key={item.id} role="option" aria-selected={i===active}>
        <button className={i===active?'active':undefined} onMouseEnter={()=>setActive(i)} onClick={()=>choose(item)}><Icon name={item.icon}/>{item.label}</button></li>)}
        {!shown.length&&<li className="muted palette-empty">{t('Nothing matches. Try another word.')}</li>}</ul>
    </div>
  </div>;
}
