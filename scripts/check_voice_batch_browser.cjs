// Challenge 1 in the real web client: a week of spending typed or spoken as one note becomes separate drafts,
// the owner edits one and unticks one, and the rest are saved together.
const assert=require('node:assert/strict');
const path=require('node:path');
const readline=require('node:readline');
const {spawn}=require('node:child_process');
const {once}=require('node:events');
const {chromium}=require('../web/node_modules/playwright');

const NOTE='Shombar dokan bhara 5000 taka dilam. Tarpor transport e 300. Budhbar Rahim theke 12 hajar taka pelam, shukrobar biddut bill 1,850 taka. Karim 2000 taka dey nai. Aj chaa nasta 250.';
(async()=>{
  const server=spawn(process.env.PYTHON||'python',['scripts/serve_golden_site.py'],{cwd:path.resolve(__dirname,'..'),stdio:['ignore','pipe','inherit']});
  const line=readline.createInterface({input:server.stdout});
  let browser;
  try{
    const [origin]=await once(line,'line');
    for(let i=0;i<100;i++){try{if((await fetch(origin+'/api/ready')).ok)break;}catch{}await new Promise(r=>setTimeout(r,100));}
    browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||undefined});
    const context=await browser.newContext({viewport:{width:390,height:860},locale:'en-US',timezoneId:'Asia/Dhaka'});
    await context.route(/^https?:\/\//,r=>new URL(r.request().url()).origin===origin?r.continue():r.abort());
    let primary=0,alternate=0;
    await context.route('**/api/assist/voice-note',route=>{
      if(route.request().method()==='GET')return route.fulfill({json:{speech:true,cloud_allowed:true,max_seconds:180,simulation_only:true}});
      const capture=route.request().postDataJSON();
      assert.equal(capture.language,'bn');
      if(capture.mode==='primary'){
        primary++;
        return route.fulfill({status:503,json:{error:{code:'SPEECH_SERVICE_BUSY'}}});
      }
      alternate++;
      return route.fulfill({json:{transcript:'আমি ৳৫০ দিয়ে নাস্তা কিনলাম।',engine:'whisper',simulation_only:true}});
    });
    await context.addInitScript(()=>{
      Object.defineProperty(navigator.mediaDevices,'getUserMedia',{value:async()=>({getTracks:()=>[{stop(){}}]})});
      Object.defineProperty(window,'MediaRecorder',{value:class {
        static isTypeSupported(){return true;}
        mimeType='audio/webm';
        state='inactive';
        constructor(stream){this.stream=stream;}
        start(){this.state='recording';}
        stop(){
          this.state='inactive';
          this.ondataavailable?.({data:new Blob([new Uint8Array(2000)],{type:this.mimeType})});
          this.onstop?.();
        }
      }});
    });
    const page=await context.newPage();page.setDefaultTimeout(15000);
    await page.goto(origin);
    await page.getByRole('link',{name:'Try the sample demo'}).click();
    await page.getByRole('button',{name:'Make drafts'}).click();
    assert.equal(await page.locator('.competition-demo .batch-list>li').count(),4);
    await page.getByRole('button',{name:'Confirm sample drafts'}).click();
    await page.getByText(/4 sample drafts reviewed/).waitFor();
    await page.getByText('Alert',{exact:true}).waitFor();
    await page.getByRole('button',{name:'Overdue payment may still arrive'}).click();
    await page.getByText('Watch',{exact:true}).waitFor();
    await page.getByRole('button',{name:'Seven-day spending sample'}).click();
    await page.getByRole('button',{name:'Make drafts'}).click();
    await page.locator('.competition-demo .batch-list>li').nth(6).waitFor();
    assert.equal(await page.locator('.competition-demo .batch-list>li').count(),7);
    await page.getByText(/21,950\.00/).waitFor();
    await page.getByRole('link',{name:'Open workspace'}).click();
    console.log('PASS public competition walkthrough: confirmed sample drafts and switched radar scenarios without an account');
    await page.getByRole('button',{name:'Create account',exact:true}).click();
    await page.locator('#username').fill('voice_week');await page.locator('#password').fill('Fictional voice business 57!');
    await page.getByRole('button',{name:'Create my workspace'}).click();
    await page.getByRole('button',{name:'I saved it'}).click();
    await page.getByRole('button',{name:/Later|Not now|Skip|Maybe later/}).first().click({timeout:6000}).catch(()=>{});
    await page.locator('nav [data-tour="Data"]').click();
    const panel=page.locator('.voice-note');
    await panel.getByLabel('What you said (you can correct it)').fill(NOTE);
    await panel.getByRole('button',{name:'Make drafts'}).click();
    const items=panel.locator('.batch-list>li');
    await items.first().waitFor();
    assert.equal(await items.count(),5);  // "Karim 2000 taka dey nai" (not paid) is not a draft
    await panel.locator('.voice-summary .voice-day').first().waitFor();
    assert.match(await panel.locator('.voice-totals').innerText(),/12,000\.00/);
    assert.equal(await items.nth(2).getByLabel('Type').inputValue(),'income');
    await items.nth(1).getByLabel(/^Amount/).fill('350');            // the owner corrects transport
    await items.nth(4).getByRole('checkbox').uncheck();               // and leaves the tea out
    const wide=await page.evaluate(()=>document.documentElement.scrollWidth);
    assert.ok(wide<=392,`page is ${wide}px wide on a phone`);
    await panel.getByRole('button',{name:'Save 4 records'}).click();
    await panel.locator('.success').waitFor();
    assert.match(await panel.locator('.success').innerText(),/4 records added/);
    const snap=await page.evaluate(async()=>(await (await fetch('/api/workspace',{credentials:'same-origin',headers:{'X-SafeLedger-Client':'web'}})).json()).snapshot);
    assert.equal(snap.income_minor,1200000);
    assert.equal(snap.expenses_minor,500000+35000+185000);
    console.log('PASS voice note: one note became 5 drafts, edited and saved 4 together');
    await panel.getByRole('button',{name:'Record a voice note',exact:true}).click();
    await panel.getByRole('button',{name:/^Stop \(/}).click();
    await panel.getByText(/recording is still available to replay or retry/i).waitFor();
    await panel.getByRole('button',{name:'Try another transcription'}).click();
    await panel.getByRole('button',{name:'Make drafts'}).click();
    await panel.getByLabel(/^Amount/).waitFor();
    assert.equal(await panel.getByLabel(/^Amount/).inputValue(),'50.00');
    assert.equal(await panel.locator('.batch-list input[type=checkbox]').isChecked(),false);
    assert.equal(primary,1);
    assert.equal(alternate,1);
    console.log('PASS Bangla recording retained after provider failure and retried without recording again');
  }finally{await browser?.close();server.kill('SIGTERM');}
})().catch(error=>{console.error(error);process.exit(1);});
