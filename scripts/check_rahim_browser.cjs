// Run the actual web client, finance engine and an isolated public passport verifier.
const {chromium}=require('../web/node_modules/playwright');
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {once}=require('node:events');
const readline=require('node:readline');
const path=require('node:path');
const fs=require('node:fs/promises');

(async()=>{
  const server=spawn(process.env.PYTHON||'python',['scripts/serve_golden_site.py'],{cwd:path.resolve(__dirname,'..'),stdio:['ignore','pipe','inherit']});
  const stopped=once(server,'exit');
  const line=readline.createInterface({input:server.stdout});
  let browser;
  try{
    const [origin]=await Promise.race([once(line,'line'),stopped.then(()=>{throw Error('Synthetic server failed to start');})]);
    assert.match(origin,/^http:\/\/127\.0\.0\.1:[0-9]+$/);
    // A free port is reserved before FastAPI runs its schema migrations.
    let ready=false;
    for(let attempt=0;attempt<100&&!ready;attempt++){
      try{ready=(await fetch(origin+'/api/ready')).ok;}catch{}
      if(!ready)await new Promise(r=>setTimeout(r,100));
    }
    assert.ok(ready,'isolated API readiness');
    browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||undefined});
    async function session(){
      const context=await browser.newContext({viewport:{width:390,height:844},locale:'en-US',timezoneId:'Asia/Dhaka'});
      await context.route(/^https?:\/\//,route=>new URL(route.request().url()).origin===origin?route.continue():route.abort());
      const page=await context.newPage();
      page.setDefaultTimeout(15000);
      return page;
    }
    // Capture only post-login synthetic scenes; the signup recovery code stays private.
    async function frame(page,locator,name){
      const dir=process.env.CAPZORYX_DEMO_FRAMES;
      if(!dir)return;
      await fs.mkdir(dir,{recursive:true});
      await locator.scrollIntoViewIfNeeded();
      await page.screenshot({path:path.join(dir,name+'.png'),animations:'disabled'});
    }
    const owner=await session();
    await owner.goto(origin);
    await owner.locator('#try-sentence').fill('আজ ৫০০০ টাকা খরচ করলাম');
    await owner.getByRole('button',{name:'Preview record'}).click();
    await owner.locator('#try-record [role="status"]').filter({hasText:'5,000.00'}).waitFor();
    await owner.getByRole('button',{name:'Create account',exact:true}).click();
    await owner.locator('#username').fill('rahim_synthetic');
    await owner.locator('#password').fill('Fictional demo business 57!');
    await owner.getByRole('button',{name:'Create my workspace'}).click();
    await owner.locator('dialog[open]').getByRole('button',{name:/skip/i}).click();
    await owner.getByRole('button',{name:'I saved it'}).click();
    await owner.getByRole('button',{name:'Try a sample business'}).click();
    await owner.getByRole('heading',{name:'Cover the cash gap'}).waitFor();
    const bundle=await (await owner.request.get(origin+'/api/workspace')).json();
    assert.equal(bundle.snapshot.balance_minor,15000000);
    assert.equal(bundle.month.minimum_balance_minor,-36000000);
    assert.equal(bundle.month.closing_balance_minor,24000000);
    await owner.getByRole('button',{name:'Show records for Cleared income'}).click();
    const sources=owner.locator('#cash-sources');
    for(const e of bundle.events.filter(e=>e.status==='cleared' && e.direction==='inflow'))
      await sources.getByText(e.source_record_id,{exact:false}).waitFor();
    await owner.getByRole('button',{name:'Cash briefing',exact:true}).click();
    await owner.locator('#briefing-report').getByText(/Available cash is.*150,000.00/).waitFor();
    await owner.locator('nav [data-tour="Settings"]').click();
    const lowData=owner.getByRole('checkbox',{name:'Reduce background downloads'});
    await lowData.check(); assert.equal(await owner.evaluate(()=>localStorage.getItem('capzoryx-data-saver')),'on');
    await owner.getByRole('tab',{name:'Data & workspaces'}).click();
    await owner.getByRole('button',{name:'View feature settings'}).click();
    const issue=owner.getByRole('checkbox',{name:'Issue public passports'});
    await Promise.all([owner.waitForResponse(r=>r.url().endsWith('/features/passport_issue')&&r.request().method()==='POST'),issue.click()]);
    const switches=async()=>(await (await owner.request.get(origin+'/api/workspace/features')).json()).features;
    assert.equal((await switches()).find(flag=>flag.name==='passport_issue').enabled,false);
    await Promise.all([owner.waitForResponse(r=>r.url().endsWith('/features/passport_issue')&&r.request().method()==='POST'),issue.click()]); await owner.locator('nav [data-tour="Overview"]').click();
    assert.equal((await switches()).find(flag=>flag.name==='passport_issue').enabled,true);
    const asOf=new Date(bundle.snapshot.as_of+'T00:00:00Z');
    const day=(offset)=>new Date(asOf.getTime()+offset*86400000).toISOString().slice(0,10);
    assert.equal(bundle.month.first_shortfall_on,day(6));
    await frame(owner,owner.getByRole('heading',{name:'Cover the cash gap'}),'01-outlook');
    await owner.locator('nav [data-tour="Cash flow"]').click();
    const preview=owner.waitForResponse(res=>res.url()===origin+'/api/copilot/gap-fix'&&res.request().method()==='POST');
    await owner.getByRole('button',{name:'Find a collection plan'}).click();
    const {plan}=await (await preview).json();
    assert.deepEqual(plan.actions,[{kind:'collect_early',source_id:'sample-sample-export',scheduled_on:day(25),collect_by:day(6),amount_minor:36000000}]);
    assert.equal(plan.remaining_gap_minor,0);assert.equal(plan.forecast.closing_balance_minor,24000000);
    await frame(owner,owner.getByRole('button',{name:'Accept and create collection tasks'}),'02-plan');
    await owner.getByRole('button',{name:'Accept and create collection tasks'}).click();
    await owner.getByRole('button',{name:'Mark task done'}).waitFor();
    await frame(owner,owner.getByRole('button',{name:'Mark task done'}),'03-task');
    const after=await (await owner.request.get(origin+'/api/workspace')).json();
    assert.equal(after.snapshot.balance_minor,bundle.snapshot.balance_minor);
    await owner.getByRole('button',{name:'Activity',exact:true}).first().click();
    owner.once('dialog',async dialog=>{assert.ok(dialog.message().startsWith('Create a public passport?'));await dialog.accept();});
    await owner.getByRole('button',{name:'Create a signed passport'}).click();
    const link=owner.getByRole('link',{name:'View passport'}).first();
    const href=await link.getAttribute('href');
    const guest=await session();
    const publicUrl=new URL(href,origin);
    assert.equal(publicUrl.origin,origin);
    await guest.goto(publicUrl.href);
    await guest.getByText('Signature verified',{exact:true}).waitFor();
    await guest.getByAltText('QR code to check the current passport').waitFor();
    await frame(guest,guest.getByText('Signature verified',{exact:true}),'04-passport');
    const published=await (await guest.request.get(origin+'/api/public/passport/'+href.split('/').pop())).json();
    assert.equal(published.summary.balance_minor,15000000);
    assert.equal(published.summary.receipts_minor,5000000);assert.equal(published.summary.expenses_minor,2000000);
    owner.once('dialog',async dialog=>{assert.ok(dialog.message().startsWith('Revoke this passport?'));await dialog.accept();});
    await owner.getByRole('button',{name:'Revoke link'}).click();
    await link.waitFor({state:'hidden'});
    await guest.reload();await guest.getByText(/This passport could not be verified/).waitFor();
    await frame(guest,guest.getByText(/This passport could not be verified/),'05-revoked');
    console.log('PASS Rahim signup, sample cash flow, collection proof, task, public QR and revocation');
  }finally{
    await browser?.close();
    line.close();
    if(server.exitCode===null&&server.signalCode===null)server.kill('SIGTERM');
    await stopped;
  }
})().catch(err=>{console.error(err.message);process.exitCode=1;});
