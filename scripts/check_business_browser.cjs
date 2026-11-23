// Business setup in the real web client: acceptance tests A (new owner sees setup), B (profile and products
// are validated and saved) and E (a returning owner goes straight to the dashboard).
const {chromium}=require('../web/node_modules/playwright');
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {once}=require('node:events');
const readline=require('node:readline');
const path=require('node:path');
const fs=require('node:fs/promises');

async function openPage(page,name){
  const button=page.locator(`nav [data-tour="${name}"]`);
  await page.locator(`nav [data-tour="Overview"]`).waitFor({state:"attached"});
  if(!await button.isVisible())await page.locator('nav .more-toggle').click();
  await button.click();
}

(async()=>{
  const server=spawn(process.env.PYTHON||'python',['scripts/serve_golden_site.py'],{cwd:path.resolve(__dirname,'..'),stdio:['ignore','pipe','inherit']});
  const stopped=once(server,'exit');
  const line=readline.createInterface({input:server.stdout});
  let browser;
  try{
    const [origin]=await Promise.race([once(line,'line'),stopped.then(()=>{throw Error('Synthetic server failed to start');})]);
    let ready=false;
    for(let attempt=0;attempt<100&&!ready;attempt++){
      try{ready=(await fetch(origin+'/api/ready')).ok;}catch{}
      if(!ready)await new Promise(r=>setTimeout(r,100));
    }
    assert.ok(ready,'isolated API readiness');
    browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||undefined});
    const shots=process.env.SETUP_SHOTS;
    if(shots)await fs.mkdir(shots,{recursive:true});
    async function session(width){
      const context=await browser.newContext({viewport:{width,height:900},locale:'en-US',timezoneId:'Asia/Dhaka'});
      await context.route(/^https?:\/\//,route=>new URL(route.request().url()).origin===origin?route.continue():route.abort());
      const page=await context.newPage();
      page.setDefaultTimeout(15000);
      return page;
    }
    const shot=async(page,name)=>{if(shots)await page.screenshot({path:path.join(shots,name+'.png'),fullPage:true,animations:'disabled'});};

    const owner=await session(1280);
    await owner.goto(origin);
    await owner.getByRole('button',{name:'Create account',exact:true}).click();
    await owner.locator('#username').fill('gold_owner');
    await owner.locator('#password').fill('Fictional gold business 57!');
    await owner.getByRole('button',{name:'Create my workspace'}).click();
    await owner.getByRole('button',{name:'I saved it'}).click();

    // A: a new owner is offered business setup straight away.
    const wizard=owner.getByRole('dialog',{name:'Set up your business'});
    await wizard.getByRole('heading',{name:'Tell us about your business once'}).waitFor();
    await shot(owner,'setup-welcome');
    await wizard.getByRole('button',{name:'Set up my business'}).click();

    // B: identity, products (typed and CSV), operations, goals and permissions are validated and saved.
    await wizard.getByLabel('Business name').fill('Golden Heritage BD');
    await wizard.getByLabel('What exactly do you do?').fill('gold jewelry shop');
    await wizard.getByRole('button',{name:'Use this'}).click();
    assert.equal(await wizard.getByLabel('Industry').inputValue(),'jewelry');
    await wizard.getByText('Retail',{exact:true}).click();
    await wizard.getByLabel('City or area').fill('Dhaka');
    await shot(owner,'setup-identity');
    await wizard.getByRole('button',{name:'Save and continue'}).click();

    await wizard.getByLabel('Product or service').fill('22K Gold');
    await wizard.getByLabel('Category',{exact:true}).fill('Gold');
    await wizard.getByLabel('Unit',{exact:true}).fill('vori');
    await wizard.getByLabel('Quantity in stock').fill('5');
    await wizard.getByLabel(/Purchase cost per unit/).fill('194000');
    await wizard.getByLabel(/Selling price per unit/).fill('220,000');
    await wizard.getByRole('button',{name:'Add product'}).click();
    await wizard.getByText('Market price tracked').waitFor();
    const file=path.join(require('node:os').tmpdir(),'capzoryx-products.csv');
    await fs.writeFile(file,'Product,Category,Unit,Cost,Price\nSilver ring,Silver,pcs,1200,1800\n22K Gold,Gold,bhori,,\n');
    await wizard.locator('input[type=file]').setInputFiles(file);
    await wizard.getByText('1 added, 1 skipped.').waitFor();
    await shot(owner,'setup-products');
    await wizard.getByRole('button',{name:'Save and continue'}).click();

    await wizard.getByText('Both',{exact:true}).click();
    await wizard.getByText('Facebook page',{exact:true}).click();
    await wizard.getByLabel('Competitors you know').fill('Diamond World, Apan Jewellers');
    await wizard.getByRole('button',{name:'Save and continue'}).click();
    await wizard.getByText('Protect capital from price swings').click();
    await wizard.getByRole('button',{name:'Save and continue'}).click();
    await wizard.getByText('Send me important alerts automatically').click();
    await wizard.getByRole('button',{name:'Finish setup'}).click();
    await owner.getByText('Your business profile is saved.').waitFor();
    assert.equal(await wizard.count(),0);

    const saved=await (await owner.request.get(origin+'/api/business')).json();
    assert.ok(saved.completed);
    assert.equal(saved.profile.identity.industry,'jewelry');
    assert.deepEqual(saved.profile.operations.competitors,['Diamond World','Apan Jewellers']);
    assert.ok(saved.profile.consent.alerts);
    assert.deepEqual(saved.products.map(p=>[p.name,p.unit,p.market_key,p.cost_minor]),[['22K Gold','bhori','gold_22k',19400000],['Silver ring','piece','silver',120000]]);

    // E: signing out and back in keeps the profile and does not show setup again.
    await owner.getByRole('button',{name:'Sign out'}).click();
    await owner.locator('.auth-tabs').getByRole('button',{name:'Sign in'}).click();
    await owner.locator('#username').fill('gold_owner');
    await owner.locator('#password').fill('Fictional gold business 57!');
    await owner.locator('form button.full-width').click();
    await owner.locator('nav [data-tour="Overview"]').waitFor();
    await owner.waitForTimeout(800);
    assert.equal(await wizard.count(),0);
    assert.equal(await owner.locator('.biz-resume').count(),0);

    // The profile stays editable in Settings → Business.
    await owner.getByLabel('Search pages and settings').fill('business');
    await owner.getByRole('option').getByRole('button',{name:/Business profile/}).click();
    await owner.locator('.biz-edit').getByLabel('Business name').waitFor().catch(async e=>{console.log('DEBUG',await owner.locator('.settings-tabs [aria-selected=true]').innerText().catch(()=>'none'),'|',await owner.evaluate(()=>sessionStorage.getItem('capzoryx-settings-tab')),'|',await owner.locator('.biz-edit').count(),await owner.locator('.biz-edit').innerText().catch(()=>''));throw e;});
    assert.equal(await owner.locator('.biz-edit').getByLabel('Business name').inputValue(),'Golden Heritage BD');
    await shot(owner,'setup-settings');
    console.log('PASS business setup: new owner sees setup, profile and products saved, returning owner goes straight in');
  }finally{
    await browser?.close();
    server.kill('SIGTERM');
  }
})().catch(error=>{console.error(error);process.exit(1);});
