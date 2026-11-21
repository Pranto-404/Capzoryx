import assert from 'node:assert/strict';
import { randomBytes, randomUUID } from 'node:crypto';
import { readFile } from 'node:fs/promises';

const manifest = new URL('../.github/staging-website.json', import.meta.url);
const release = JSON.parse(await readFile(manifest, 'utf8'));
// Fix the origin so the synthetic workspace can only be created on staging.
const origin = 'https://capzoryx-qa.vercel.app';
const headers = { 'X-SafeLedger-Client': 'web', Origin: origin, 'Content-Type': 'application/json' };

async function request(path, body) {
  const response = await fetch(origin + path, {
    headers,
    redirect: 'error',
    signal: AbortSignal.timeout(90000),
    method: body === undefined ? 'GET' : 'POST',
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  assert.ok(response.ok, path + ' returned HTTP ' + response.status);
  if (path === '/api/auth/signup') {
    headers.Cookie = response.headers.getSetCookie().map(cookie => cookie.split(';')[0]).join('; ');
    assert.ok(headers.Cookie, 'Signup did not establish a session');
  }
  return response.json();
}

const [site, health, ready] = await Promise.all([
  request('/.well-known/capzoryx-website.json'), request('/api/health'), request('/api/ready'),
]);
assert.equal(site.commit, release.website);
assert.equal(health.build_commit, release.api);
assert.equal(ready.status, 'ready');
assert.equal(ready.database, 'libsql');
console.log('Verified website and API revisions and Turso readiness.');

if (process.argv.includes('--exercise')) {
  const speech = await request('/voice-pack/whisper-tiny-v1/manifest.json');
  assert.equal(speech.version, 'whisper-tiny-v1');
  assert.ok(speech.files['tiny-encoder.int8.onnx'].bytes > 0);
  assert.ok(speech.files['tiny-decoder.int8.onnx'].bytes > 0);
  const banglaSpeech = await request('/voice-pack/vosk-bn-v1/manifest.json');
  assert.equal(banglaSpeech.version, 'vosk-bn-v1');
  assert.ok(Object.values(banglaSpeech.files).some(file => file.bytes > 1000000));
  const session = await request('/api/auth/signup', {
    username: 'qa_web_' + randomBytes(5).toString('hex'),
    password: randomBytes(24).toString('base64') + 'a!7',
  });
  try {
    const email = await request('/api/notifications/bill-email');
    assert.equal(email.enabled, false);
    assert.equal(email.verified, false);
    console.log('QA bill email transport configured:', email.configured);
    const push = await request('/api/notifications/push-config');
    assert.equal(push.webpush, true);
    assert.equal(Buffer.from(push.public_key, 'base64url').length, 65);
    const bundle = await request('/api/workspace');
    const day = bundle.snapshot.as_of;
    const item = await request('/api/workspace/records', {
      request_id: randomUUID(), expected_revision: bundle.dataset_revision,
      kind: 'cash', amount_minor: 50000, effective_on: day, direction: 'inflow',
    });
    const corrected = await request('/api/workspace/cash-corrections', {
      request_id: randomUUID(), expected_business_id: session.business_id,
      expected_user_id: session.user_id, original_id: item.source_id,
      previous_source_id: item.source_id, confirmed: true,
      replacement: { effective_on: day, amount_minor: 45000, direction: 'inflow', status: 'cleared' },
    });
    assert.ok(corrected.id);
    const facts = await request('/api/copilot/briefing');
    assert.equal(facts.balance_minor, 45000);
    const yesterday = new Date(Date.parse(day + 'T00:00:00Z') - 86400000).toISOString().slice(0, 10);
    const customer = await request('/api/workspace/customers', { request_id: randomUUID(), name: 'QA fictional shop' });
    const debt = await request('/api/workspace/receivables', {
      request_id: randomUUID(), customer_id: customer.id, amount_minor: 10000,
      issued_on: yesterday, due_on: yesterday, currency: bundle.snapshot.currency,
    });
    const review = await request('/api/copilot/agent-review');
    assert.equal(review.collections[0].receivable_id, debt.id);
    assert.equal(review.collections[0].open_minor, 10000);
    const reminder = await request('/api/copilot/message', { receivable_id: debt.id, language: 'bn' });
    assert.ok(reminder.message.includes('১০০'));
    const handoff = await request('/api/copilot/message/approve', {
      receivable_id: debt.id, language: 'bn', request_id: randomUUID(), reviewed_message: reminder.message,
    });
    assert.equal(handoff.message, reminder.message);
    const flags = await request('/api/workspace/features/passport_issue', { enabled: false });
    assert.equal(flags.simulation_only, true);
    assert.equal(flags.features.find(feature => feature.name === 'passport_issue').enabled, false);
  } finally {
    await request('/api/auth/logout', {});
  }
  console.log('Verified synthetic cash entry, correction, briefing, agent collection review, Bangla reminder, workspace control and sign-out.');
}
