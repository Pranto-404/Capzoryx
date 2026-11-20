import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import {VerifyPassport} from './Passport';
import {ThemeProvider} from './Theme';
import {I18nProvider} from './i18n';
import './style.css';
const passport = /^\/verify\/([a-f0-9]{32})\/?$/.exec(location.pathname);
createRoot(document.getElementById('root')!).render(<StrictMode><ThemeProvider><I18nProvider>{passport ? <VerifyPassport id={passport[1]}/> : <App />}</I18nProvider></ThemeProvider></StrictMode>);
