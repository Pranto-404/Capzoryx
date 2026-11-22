import {useEffect,useRef,useState} from 'react';
import {t} from './i18n';
import {useDataSaver} from './dataSaver';
import type {HeroScene} from './heroScene';

const currentTheme=()=>document.documentElement.dataset.theme==='dark'?'dark':'light';
const prefersStill=()=>{try{return matchMedia('(prefers-reduced-motion: reduce)').matches;}catch{return false;}};
function webgl(){
  try{const c=document.createElement('canvas');return !!(c.getContext('webgl2')||c.getContext('webgl'));}catch{return false;}
}

/** Futuristic 3D hero. Falls back to a light CSS orb in low-data mode or without WebGL. */
export function Hero3D(){
  const host=useRef<HTMLDivElement>(null);
  const saver=useDataSaver();
  const [fallback,setFallback]=useState(false);
  useEffect(()=>{
    if(saver||!webgl()){setFallback(true);return;}
    let scene:HeroScene|null=null,cancelled=false;
    const themeWatch=new MutationObserver(()=>scene?.setTheme(currentTheme()));
    import('./heroScene').then(({mountHeroScene})=>{
      if(cancelled||!host.current)return;
      scene=mountHeroScene(host.current,{theme:currentTheme(),still:prefersStill()});
      themeWatch.observe(document.documentElement,{attributes:true,attributeFilter:['data-theme']});
    }).catch(()=>setFallback(true));
    return()=>{cancelled=true;themeWatch.disconnect();scene?.dispose();};
  },[saver]);
  return <div className="hero3d" aria-hidden="true">
    <div ref={host} className={fallback?'hero3d-stage fallback':'hero3d-stage'}>{fallback&&<span className="hero3d-orb"/>}</div>
    <span className="hud hud-a">+৳5,000 · bKash</span>
    <span className="hud hud-b">{t('Cash in 7 days')} ↑</span>
    <span className="hud hud-c">{t('Bill due Friday')}</span>
  </div>;
}
