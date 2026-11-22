import {ChannelLink} from './TelegramLink';

type Request=<T,>(path:string,body?:unknown)=>Promise<T>;
export function WhatsAppLink({request}:{request:Request}){return <ChannelLink request={request} channel="whatsapp"/>;}
