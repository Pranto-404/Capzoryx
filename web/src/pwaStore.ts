import type {Session} from './types';
export type Owner = {user_id:string; business_id:string; currency:string};
export type QueuedRecord = Owner & {request_id:string;kind:'cash'|'invoice';amount_minor:number;effective_on:string;
  direction:'inflow'|'outflow';vendor_id?:string;invoice_number?:string;due_on?:string};
export interface CaptureStore {
  scope():Promise<Owner|undefined>;
  same(a:Pick<Owner,'user_id'|'business_id'>|undefined,b:Session|Owner):boolean;
  setScope(owner:Owner|null):Promise<void>;
  drafts(owner:Owner):Promise<QueuedRecord[]>;
  saveDraft(draft:QueuedRecord):Promise<void>;
  removeDraft(id:string):Promise<void>;
  share(text:string):Promise<string>;
  getShare(id:string):Promise<{id:string;owner?:Owner;text:string}|undefined>;
  removeShare(id:string):Promise<void>;
  clear():Promise<void>;
}
declare global {interface Window {capzoryxStore:CaptureStore}}
