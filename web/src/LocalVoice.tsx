import {useEffect, useRef, useState} from 'react';
import {t, useI18n} from './i18n';

type Recognition = {
  processLocally:boolean; lang:string; continuous:boolean; interimResults:boolean;
  start():void; stop():void; abort():void;
  onresult:((event:{results:{[i:number]:{[i:number]:{transcript:string}}}})=>void)|null;
  onerror:(()=>void)|null; onend:(()=>void)|null;
};
type Speech = {new(): Recognition; available?:(input:{langs:string[];processLocally:boolean})=>Promise<string>};

export function LocalVoice({onText}: {onText:(text:string)=>void}) {
  const {code} = useI18n();
  const [recording, setRecording] = useState(false);
  const [notice, setNotice] = useState('');
  const active = useRef<Recognition|null>(null);
  const alive = useRef(true);
  const timer = useRef<number|undefined>(undefined);
  const browser = window as unknown as {SpeechRecognition?:Speech; webkitSpeechRecognition?:Speech};
  const SpeechRecognition = browser.SpeechRecognition || browser.webkitSpeechRecognition;
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      window.clearTimeout(timer.current);
      const engine = active.current;
      if (engine) {engine.onresult = null; engine.onerror = null; engine.onend = null; engine.abort();}
    };
  }, []);
  if (!SpeechRecognition?.available) return null;
  async function begin() {
    if (!SpeechRecognition || active.current) return;
    const lang = code === 'bn' ? 'bn-BD' : code === 'en' ? 'en-US' : code;
    setNotice('');
    try {
      const engine = new SpeechRecognition();
      if (!('processLocally' in engine) || await SpeechRecognition.available?.({langs:[lang], processLocally:true}) !== 'available') {
        if (alive.current) setNotice(t('On-device speech is unavailable for this language. You can type the record.'));
        return;
      }
      if (!alive.current || active.current) return;
      engine.processLocally = true;
      engine.lang = lang;
      engine.continuous = false;
      engine.interimResults = false;
      engine.onresult = event => onText(event.results[0][0].transcript.slice(0,400));
      engine.onerror = () => setNotice(t('Could not hear the record. Try again or type it.'));
      engine.onend = () => {window.clearTimeout(timer.current); active.current = null; setRecording(false);};
      engine.start();
      active.current = engine;
      setRecording(true);
      timer.current = window.setTimeout(() => engine.stop(), 30000);
    } catch {if (alive.current) setNotice(t('Microphone unavailable. You can type the record.'));}
  }
  return <><button className="secondary" type="button" onClick={() => recording ? active.current?.stop() : void begin()}>
    {recording ? t('Stop recording') : t('Dictate on this device')}</button>{notice && <p role="status">{notice}</p>}</>;
}
