import {CaptureClient} from './capture-client.mjs';
const status = document.querySelector('#status');
const send = document.querySelector('#send');
const reset = document.querySelector('#reset');
const modes = [...document.querySelectorAll('[data-mode]')];
let client, token, current, busy = false;
function say(text, state = '') { status.textContent = text; status.dataset.state = state; }
function controls() { modes.forEach(b => b.disabled = busy || !!current || !client); send.disabled = busy || !current || !client; reset.disabled = busy; }
try {
  const response = await fetch('/harness/session', {headers: {'X-Harness': 'synthetic'}, cache: 'no-store'});
  if (!response.ok) throw new Error('Local session unavailable');
  ({token} = await response.json());
  client = new CaptureClient({endpoint: location.origin, token, testLoopback: true});
  const saved = sessionStorage.getItem('hs-meta-synthetic-job');
  current = saved ? JSON.parse(saved) : null;
  say(current ? 'Saved test capture recovered. Send checks the receiver before retrying.' : 'Ready. These buttons generate fabricated media.');
} catch { say('NOT CONNECTED. No upload confirmed.', 'error'); }
controls();
for (const button of modes) button.onclick = async () => {
  busy = true; controls(); say('Generating test media…');
  try {
    const response = await fetch('/harness/capture/' + button.dataset.mode, {method: 'POST', headers: {Authorization: 'Bearer ' + token}});
    if (!response.ok) throw new Error();
    current = await response.json();
    sessionStorage.setItem('hs-meta-synthetic-job', JSON.stringify(current));
    say('SAVED LOCALLY · Synthetic ' + current.mode + '. Not uploaded.');
    busy = false; controls(); send.focus();
  } catch { say('NOT SAVED. Could not create test media.', 'error'); busy = false; controls(); }
};
send.onclick = async () => {
  busy = true; controls(); say('SENDING / CHECKING RECEIPT…');
  try {
    const response = await fetch('/harness/package/' + current.job_id, {headers: {Authorization: 'Bearer ' + token}, cache: 'no-store'});
    if (!response.ok) throw new Error();
    const receipt = await client.transmit(current.job_id, await response.blob());
    say('RECEIVED · TEST ONLY. Stored package independently read back. Receipt: ' + receipt.receipt_id, 'ok');
  } catch { say('UPLOAD NOT VERIFIED. Test file retained; Send checks before retrying.', 'error'); }
  busy = false; controls();
};
reset.onclick = () => { current = null; sessionStorage.removeItem('hs-meta-synthetic-job'); say('Ready for a new fabricated capture. Earlier test files remain on disk.'); controls(); modes[0].focus(); };
document.addEventListener('keydown', event => {
  if (!['ArrowDown', 'ArrowUp', 'ArrowLeft', 'ArrowRight'].includes(event.key)) return;
  event.preventDefault();
  const available = [...document.querySelectorAll('button:not(:disabled)')];
  if (!available.length) return;
  const index = available.indexOf(document.activeElement);
  const direction = ['ArrowDown', 'ArrowRight'].includes(event.key) ? 1 : -1;
  available[(index + direction + available.length) % available.length].focus();
});
