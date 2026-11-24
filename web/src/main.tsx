import {nativeBuild} from './apiBase';
import { lazy, StrictMode, Suspense } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import {VerifyPassport} from './Passport';
import {ThemeProvider} from './Theme';
import {I18nProvider} from './i18n';
import './style.css';
const EmailUnsubscribe=lazy(()=>import('./EmailAlerts').then(module=>({default:module.EmailUnsubscribe})));
const passport = /^\/verify\/([a-f0-9]{32})\/?$/.exec(location.pathname);
createRoot(document.getElementById('root')!).render(<StrictMode><ThemeProvider><I18nProvider>{location.pathname==='/bill-reminders/unsubscribe'?<Suspense fallback={null}><EmailUnsubscribe/></Suspense>:passport ? <VerifyPassport id={passport[1]}/> : <App />}</I18nProvider></ThemeProvider></StrictMode>);

if (!nativeBuild && import.meta.env.PROD && 'serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {});
  });
}

if(nativeBuild){
  document.documentElement.classList.add('native-app');
  void import('./nativeLinks').then(module=>module.listenToNativeLinks());
}
