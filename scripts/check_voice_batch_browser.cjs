// Challenge 1 in the real web client: a week of spending typed or spoken as one note becomes separate drafts,
// the owner edits one and unticks one, and the rest are saved together.
const assert=require('node:assert/strict');
const path=require('node:path');
const readline=require('node:readline');
const {spawn}=require('node:child_process');
const {once}=require('node:events');
const {chromium}=require('../web/node_modules/playwright');

const NOTE='Shombar dokan bhara 5000 taka dilam. Tarpor transport e 300. Budhbar Rahim theke 12 hajar taka pelam, shukrobar biddut bill 1,850 taka. Aj chaa nasta 250.';
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
    const page=await context.newPage();page.setDefaultTimeout(15000);
    await page.goto(origin);
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
    assert.equal(await items.count(),5);
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
  }finally{await browser?.close();server.kill('SIGTERM');}
})().catch(error=>{console.error(error);process.exit(1);});
