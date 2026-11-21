// Only the span immediately before a named currency is eligible. Keep the original transcript on ambiguity.
const numbers=new Map<string,number>();
function add(words:string,start:number,step=1){
  words.split(' ').forEach((word,index)=>numbers.set(word.normalize('NFC'),start+index*step));
}
add('এক দুই তিন চার পাঁচ ছয় সাত আট নয় দশ এগারো বারো তেরো চৌদ্দ পনেরো ষোলো সতেরো আঠারো উনিশ',1);
add('বিশ একুশ বাইশ তেইশ চব্বিশ পঁচিশ ছাব্বিশ সাতাশ আটাশ ঊনত্রিশ',20);
add('ত্রিশ একত্রিশ বত্রিশ তেত্রিশ চৌত্রিশ পঁয়ত্রিশ ছত্রিশ সাঁইত্রিশ আটত্রিশ ঊনচল্লিশ',30);
add('চল্লিশ একচল্লিশ বিয়াল্লিশ তেতাল্লিশ চুয়াল্লিশ পঁয়তাল্লিশ ছেচল্লিশ সাতচল্লিশ আটচল্লিশ ঊনপঞ্চাশ',40);
add('পঞ্চাশ একান্ন বাহান্ন তিপ্পান্ন চুয়ান্ন পঞ্চান্ন ছাপ্পান্ন সাতান্ন আটান্ন ঊনষাট',50);
add('ষাট একষট্টি বাষট্টি তেষট্টি চৌষট্টি পঁয়ষট্টি ছেষট্টি সাতষট্টি আটষট্টি ঊনসত্তর',60);
add('সত্তর একাত্তর বাহাত্তর তিয়াত্তর চুয়াত্তর পঁচাত্তর ছিয়াত্তর সাতাত্তর আটাত্তর ঊনআশি',70);
add('আশি একাশি বিরাশি তিরাশি চুরাশি পঁচাশি ছিয়াশি সাতাশি আটাশি ঊননব্বই',80);
add('নব্বই একানব্বই বিরানব্বই তিরানব্বই চুরানব্বই পঁচানব্বই ছিয়ানব্বই সাতানব্বই আটানব্বই নিরানব্বই',90);
add('one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen',1);
add('twenty thirty forty fifty sixty seventy eighty ninety',20,10);
const hundreds=new Map<string,number>();
for(const [index,forms] of ['এক','দুই দু','তিন','চার','পাঁচ','ছয় ছ','সাত','আট','নয়'].entries()){
  for(const form of forms.split(' '))for(const ending of ['শ','শো','শত'])hundreds.set((form+ending).normalize('NFC'),(index+1)*100);
}
const hundred=new Set(['hundred','শ','শো','শত']);
const thousand=new Set(['thousand','হাজার']);
const currencyNames:Record<string,string>={'টাকা':'BDT','taka':'BDT','bdt':'BDT','dollar':'USD','dollars':'USD',
  'usd':'USD','euro':'EUR','euros':'EUR','eur':'EUR','pound':'GBP','pounds':'GBP','gbp':'GBP'};
const uncertainPrefix=new Set(
  'or to between minus negative plus point half quarter about around approximately under over than less million lakh crore বা অথবা প্রায় সাড়ে পৌনে সোয়া দেড় আড়াই লক্ষ লাখ কোটি দশমিক নয় কম বেশি'.normalize('NFC').split(' ')
);
const value=(word:string)=>numbers.get(word)??0;
const cardinal=(word:string)=>numbers.has(word)||hundreds.has(word)||hundred.has(word)||thousand.has(word)||word==='and';

// Parse one English or Bengali group from one to 999. English tens admit one additional units word.
function group(words:string[]):number {
  let base=hundreds.get(words[0])??0;
  let tail=words;
  if(base)tail=words.slice(1);
  else if(hundred.has(words[1])&&value(words[0])>=1&&value(words[0])<=9){
    base=value(words[0])*100;tail=words.slice(2);
  }
  if(base&&!tail.length)return base;
  if(base&&tail[0]==='and')tail=tail.slice(1);
  if(tail.length===1&&value(tail[0]))return base+value(tail[0]);
  if(tail.length===2&&/^[a-z]+$/.test(tail[0])&&value(tail[0])>=20&&value(tail[0])%10===0
    &&value(tail[1])>=1&&value(tail[1])<=9)return base+value(tail[0])+value(tail[1]);
  return 0;
}

export function normalizeSpokenAmount(text:string,currency:string):string {
  const tokens=[...text.matchAll(/[\p{L}\p{M}\p{N}]+/gu)];
  const words=tokens.map(token=>token[0].toLowerCase().normalize('NFC'));
  const units=words.flatMap((word,i)=>Object.hasOwn(currencyNames,word)?[i]:[]);
  if(units.length!==1||currencyNames[words[units[0]]]!==currency)return text;
  const end=units[0];
  let start=end;
  while(start>0&&cardinal(words[start-1])){
    const gap=text.slice(tokens[start-1].index!+tokens[start-1][0].length,tokens[start].index);
    if(!/^\s+$/.test(gap)&&!(gap==='-'&&/^[a-z]+$/.test(words[start-1])&&start<end))break;
    start--;
  }
  if(start===end)return text;
  const before=words[start-1]||'';
  const left=text.slice(0,tokens[start].index);
  // Reject partial parses of ranges, negatives, fractions, larger scales and compound currencies.
  if(cardinal(before)||/\p{N}/u.test(before)||/[\d০-৯–—+−-]\s*$/u.test(left)
    ||uncertainPrefix.has(before)
    ||(before==='of'&&!['amount','bill','total','payment','sum'].includes(words[start-2]))
    ||words.some(word=>/^(?:paisa|poysha|poisha|cents?|পয়সা|পয়সা)$/u.test(word)))return text;
  if(before==='থেকে'&&start>=2&&(cardinal(words[start-2])||/\p{N}/u.test(words[start-2])))return text;
  if(words.slice(end+1).some(word=>['plus','minus','instead','less','বাদ','কম','বেশি'].includes(word)))return text;
  const digits=words.slice(start,end);
  if(digits.some(word=>/[a-z]/.test(word))&&digits.some(word=>/[\u0980-\u09ff]/u.test(word)))return text;
  const split=digits.findIndex(word=>thousand.has(word));
  let amount=group(digits);
  if(split>=0){
    const major=group(digits.slice(0,split));
    let tail=digits.slice(split+1);
    if(tail[0]==='and'&&tail.length>1)tail=tail.slice(1);
    const minor=group(tail);
    if(!major||(tail.length&&!minor))return text;
    amount=major*1000+minor;
  }
  if(!amount)return text;
  const last=tokens[end-1];
  return text.slice(0,tokens[start].index)+String(amount)+text.slice(last.index!+last[0].length);
}
