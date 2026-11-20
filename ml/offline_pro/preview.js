// This page is served only on loopback. No production account or ledger is available here.
const button=id=>document.getElementById(id);
const load=button('load'),stop=button('stop'),prompt=button('prompt'),ask=button('ask');
const status=button('state'),answer=button('answer');
let engine;

load.onclick=async()=>{
  load.disabled=true;
  try {
    const adapter=await navigator.gpu?.requestAdapter();
    if(!adapter?.features.has('shader-f16'))throw Error('This model requires WebGPU and shader-f16 support.');
    const model=await (await fetch('/pack.json')).json();
    status.textContent='Preparing the local model…';
    const {CreateMLCEngine}=await import('/runtime.js');
    engine=await CreateMLCEngine(model.id,{
      appConfig:{model_list:[{model_id:model.id,model:location.origin+model.path,model_lib:location.origin+model.path+model.kernel,overrides:{context_window_size:1024}}]},
      initProgressCallback:report=>{status.textContent=report.text;}
    });
    stop.disabled=prompt.disabled=ask.disabled=false;
    status.textContent='Ready. Review generated wording before using it.';
    prompt.focus();
  }catch(error){
    status.textContent=error instanceof Error?error.message:'Model initialization failed.';
    load.disabled=false;
  }
};
stop.onclick=async()=>{
  stop.disabled=ask.disabled=prompt.disabled=true;
  try {await engine?.unload();}finally{engine=undefined;answer.textContent='';prompt.value='';status.textContent='Model unloaded.';load.disabled=false;}
};
document.querySelector('form').onsubmit=async event=>{
  event.preventDefault();
  const text=prompt.value.trim();
  if(!engine||!text)return;
  ask.disabled=stop.disabled=true;
  answer.textContent='';status.textContent='Drafting locally…';
  try{
    const result=await engine.chat.completions.create({messages:[
      {role:'system',content:'Draft a short payment reminder using only the supplied text. Preserve amounts, names and dates exactly. Do not add account details or send a message. /no_think'},
      {role:'user',content:text}
    ],temperature:0,max_tokens:200});
    answer.textContent=result.choices[0]?.message.content||'No draft returned.';
    status.textContent='Review the amount, dates and names before sharing.';
  }catch(error){status.textContent=error instanceof Error?error.message:'Generation failed.';}
  finally{ask.disabled=stop.disabled=false;}
};
