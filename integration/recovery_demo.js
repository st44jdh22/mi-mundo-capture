(() => {
 'use strict';
 let bearer = null, jobId = localStorage.getItem('mi-mundo-synthetic-last-job') || null;
 const $ = id => document.getElementById(id);
 async function api(path, method='GET', data) {
   if (!bearer) throw Error('Enter your temporary token first.');
   const response = await fetch(path, {method,
     headers:{Authorization:`Bearer ${bearer}`,...(data===undefined?{}:{'Content-Type':'application/json'})},
     ...(data===undefined?{}:{body:JSON.stringify(data)}), cache:'no-store'});
   if (!response.ok) throw Error(`Request not confirmed (${response.status}). Your synthetic server state is retained.`);
   return await response.json();
 }
 function status(message){$('connectionStatus').textContent=message}
 function renderJob(j) {
   $('jobState').textContent = j.complete_test_only?
     'All 3 synthetic destinations verified in test database. No real Drive entries were written.' :
     `${j.counts.VERIFIED}/3 synthetic destinations verified. ${j.counts.POLICY_BLOCKED || 0} held for safety review. Server continues tracking this job.`;
   $('targets').replaceChildren();
   for (const t of j.targets) {
     const section=document.createElement('div');section.className='target';
     const title=document.createElement('strong');title.textContent=t.target_key;
     const state=document.createElement('span');state.className=`state ${t.state}`;state.textContent=t.state.replaceAll('_',' ');
     section.append(title,state);$('targets').append(section);
   }
   $('approve').disabled = !j.targets.some(t=>t.state==='POLICY_BLOCKED');
 }
 function renderInbox(box) {
   $('attentionCount').textContent=String(box.attention_count);
   $('inboxBadge').textContent=String(box.attention_count);
   $('inboxBadge').hidden=box.attention_count===0;
   $('attentionPill').style.borderColor=box.attention_count?'#92505e':'#336459';
   $('inbox').replaceChildren();
   if (!box.entries.length) {
     const el=document.createElement('div');el.className='empty';el.textContent='No Inbox events yet. Run the synthetic check-in.';$('inbox').append(el);
   }
   for (const x of box.entries) {
     const el=document.createElement('article');el.className='entry'+(x.needs_attention?' attention':'');
     const meta=document.createElement('p');meta.className='meta';meta.textContent=`${x.event_type}${x.needs_attention?' · NEEDS ATTENTION':''} · ${new Date(x.created_at*1000).toLocaleString()}`;
     const body=document.createElement('p');body.className='body';body.textContent=x.message;
     el.append(meta,body);$('inbox').append(el);
   }
 }
 async function refresh() {
   if(!bearer)return;
   try {
     const messages=await api('/v1/inbox');renderInbox(messages);
     if (jobId) {
       try{const j=await api(`/v1/jobs/${encodeURIComponent(jobId)}`);renderJob(j)}
       catch(e){$('jobState').textContent=e.message}
     }
     status('Connected · last checked '+new Date().toLocaleTimeString());
     $('updated').textContent='Updated '+new Date().toLocaleTimeString();
   } catch(e){status(e.message)}
 }
 $('connect').addEventListener('click',async()=>{
   bearer=$('token').value.trim();$('token').value='';
   if(!bearer){status('Temporary token required');return}
   try {await api('/v1/inbox');$('newJob').disabled=false;$('refresh').disabled=false;
     status('Connected to synthetic service');await refresh()}
   catch(e){bearer=null;status('Connection was not verified: '+e.message)}
 });
 $('newJob').addEventListener('click',async()=>{
   $('newJob').disabled=true;
   try{const j=await api('/v1/demo/jobs','POST');jobId=j.job_id;
     localStorage.setItem('mi-mundo-synthetic-last-job',jobId);renderJob(j);
     await refresh();}
   catch(e){status(e.message)}finally{$('newJob').disabled=false}
 });
 $('approve').addEventListener('click',async()=>{
   if(!jobId)return;
   if(!confirm('Release the SYNTHETIC policy-block fixture for demonstration only? This does not approve any real record or override any safety check.'))return;
   try{const j=await api(`/v1/demo/jobs/${encodeURIComponent(jobId)}/resolve`,'POST',{reviewed:true});renderJob(j);await refresh()}
   catch(e){status(e.message)}
 });
 $('refresh').addEventListener('click',refresh);
 document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh()});
 window.addEventListener('online',refresh);
 window.setInterval(()=>{if(!document.hidden)refresh()},8000);
})();