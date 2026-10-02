// Browser interaction tests against real static assets and synthetic API responses.
// npm install --no-save playwright; npx playwright install chromium
// node tests/browser/ui_smoke.mjs
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {spawn} from 'node:child_process';
import {mkdir, readFile} from 'node:fs/promises';
const require = createRequire(import.meta.url);
const {chromium} = require('playwright');
const origin = 'http://127.0.0.1:8876';
const server = spawn('.venv/bin/python', ['-c', 'import uvicorn; from tendergraph.api.app import create_app; uvicorn.run(create_app(use_lifespan=False), host="127.0.0.1", port=8876, log_level="error")'], {stdio: ['ignore', 'ignore', 'inherit']});
const reportDir = 'evaluation/answers/browser';
let browser;
try {
  let ready = false;
  for (let n=0; n<90; n++) {
    if (server.exitCode !== null) throw new Error('Test server exited');
    try {if ((await fetch(origin)).ok) {ready = true; break;}} catch {}
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  assert.ok(ready, 'test server ready');
  browser = await chromium.launch({headless: true, executablePath: process.env.CHROMIUM_EXECUTABLE_PATH || undefined});
  const page = await browser.newPage({viewport: {width:1440,height:1000}, acceptDownloads:true});
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const notice = {publication_number:'SYNTHETIC-001', buyer_country:'BEL', buyer_name:'Example Hospital — synthetic fixture', title:'Hospital information system — synthetic test notice', estimated_value:null, estimated_value_currency:null, earliest_deadline:null, publication_date:'2026-09-01', source_html_url:'https://ted.europa.eu/en/notice/-/detail/1-2026'};
  const match = {...notice, estimated_value:'250000', estimated_value_currency:'EUR', earliest_deadline:'2026-10-25T12:00:00Z', match_score:91.2, signals:{semantic_fit:0.88,country_fit:1,value_fit:1,deadline_fit:1,country_status:'matched',value_status:'within_range',deadline_status:'open',days_to_deadline:23}, why_matches:['Strong semantic fit with the company capabilities','Buyer country BEL is a target market'], risks:['Verify tender-specific eligibility requirements'], rrf_score:0.03, lexical_rank:2, semantic_rank:1, semantic_score:0.88};
  let failSearch = false;
  let insufficient = false;
  let mode = 'ollama';
  await page.route('**/health', route => route.fulfill({json:{status:'ok'}}));
  await page.route('**/config', route => route.fulfill({json:{answer_mode:mode, generation_model:mode==='ollama'?'Synthetic local model':null, reranking:false}}));
  await page.route('**/matches', route => {
    const request = route.request().postDataJSON();
    assert.equal(request.profile.company_name, 'Example Data Studio');
    assert.deepEqual(request.profile.target_countries, ['BEL','NLD','DEU','ITA']);
    assert.equal(request.profile.preferred_min_value, 50000);
    return route.fulfill({json:{profile_name:request.profile.company_name, query:'Data and AI consultancy Data engineering Python Azure', count:1, matches:[match]}});
  });
  await page.route('**/search', route => {
    const request = route.request().postDataJSON();
    assert.equal(request.query, 'hospital information system');
    return route.fulfill(failSearch ? {status:503,json:{detail:'Database unavailable'}} : {json:{query:request.query,count:1,results:[notice]}});
  });
  await page.route('**/ask', route => {
    assert.equal(route.request().postDataJSON().question, 'Who is the buyer?');
    return route.fulfill({json:{status:insufficient?'insufficient_evidence':'answered', mode:'ollama', answer:insufficient?'The available tender evidence is insufficient to answer the question.':'The buyer is Example Hospital [T1].', sources:insufficient?[]:[{...notice,citation_id:'T1'}], citations:insufficient?[]:['T1'], context_truncated:false}});
  });
  await page.goto(origin);
  await page.waitForFunction(() => document.getElementById('mode-pill').textContent==='Local AI');

  // Product flow: build a local company profile and receive explainable matches.
  assert.equal(await page.locator('#match-workspace').isVisible(), true);
  await page.locator('#example-profile').click();
  await page.locator('#match-button').click();
  await page.locator('.match-card').waitFor();
  assert.match(await page.locator('.fit-score').innerText(), /91%/);
  assert.match(await page.locator('.signal-grid').innerText(), /Why it matches/);
  assert.match(await page.locator('.signal-grid').innerText(), /Review before bidding/);
  assert.equal(await page.evaluate(() => Boolean(localStorage.getItem('tendergraph.companyProfile.v1'))), true);

  // Existing explorer and evidence workflow remains available.
  await page.locator('#nav-explorer').click();
  await page.getByRole('button', {name:'Hospital technology',exact:true}).click();
  await page.locator('#search-button').click();
  await page.locator('.tender-card').waitFor();
  assert.match(await page.locator('.tender-card').innerText(), /Not stated/);
  await page.locator('#question').fill('Who is the buyer?');
  await page.locator('#ask-button').click();
  await page.locator('.source-link').waitFor();
  assert.match(await page.locator('#answer-text').innerText(), /\[T1\]/);
  const downloaded = page.waitForEvent('download');
  await page.locator('#download-answer').click();
  const download = await downloaded;
  assert.equal(JSON.parse(await readFile(await download.path(),'utf8')).status, 'answered');
  await mkdir(reportDir, {recursive:true});
  await page.screenshot({path:`${reportDir}/desktop.png`,fullPage:true});
  await page.setViewportSize({width:390,height:844});
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), 'mobile has no horizontal overflow');
  await page.screenshot({path:`${reportDir}/mobile.png`,fullPage:true});
  insufficient = true;
  await page.locator('#ask-button').click();
  await page.waitForFunction(() => document.getElementById('answer-status').textContent==='Insufficient evidence');
  assert.equal(await page.locator('.source-link').count(),0);
  notice.title = '<img src=x onerror="window.injected=true">';
  notice.source_html_url = 'javascript:alert(1)';
  await page.locator('#search-button').click();
  await page.waitForFunction(() => document.querySelector('.card-title')?.textContent.startsWith('<img'));
  assert.equal(await page.locator('.tender-card img').count(),0);
  assert.equal(await page.locator('.tender-card a').count(),0);
  assert.equal(await page.evaluate(() => window.injected),undefined);
  failSearch = true;
  await page.locator('#search-button').click();
  await page.locator('#notice').waitFor({state:'visible'});
  assert.match(await page.locator('#notice').innerText(), /503/);
  assert.equal(await page.locator('#query').inputValue(),'hospital information system');
  assert.equal(await page.locator('#question').inputValue(),'Who is the buyer?');
  mode = 'evidence';
  await page.reload();
  await page.waitForFunction(() => document.getElementById('ask-button').textContent==='Show evidence →');
  assert.equal(await page.locator('#explorer-workspace').isVisible(), true);
  assert.deepEqual(errors, []);
  console.log('PASS: company profile matching, local profile persistence, fit explanations, search, citations, JSON download, abstention, untrusted text/URL, 503, preserved inputs, evidence mode, mobile overflow. Synthetic API fixtures; no database or model called.');
} finally {
  await browser?.close();
  server.kill('SIGTERM');
}
