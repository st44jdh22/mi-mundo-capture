/** Mi Mundo Inbox: client-side statuses for local SYNTHETIC Outbox.
 * Pure projection: NO server push, Post Office routing, personal data or
 * claim of persistent private cloud storage.
 */
import {STATES} from './offline-outbox.mjs';
export const INBOX_KINDS=Object.freeze({
 PENDING:'PENDING',ACTION:'ACTION',CHECKING:'CHECKING',TEST_ACK:'TEST_ACK',UNKNOWN:'UNKNOWN'
});
export function statusMessage(item,{online=true}={}){
 if(!item||typeof item.jobId!=='string')throw Error('Missing outbox item');
 const short=item.jobId.slice(0,8);
 const base={id:item.jobId,source:'LOCAL_TEST_OUTBOX',kind:INBOX_KINDS.UNKNOWN,
  heading:'Item '+short,priority:'normal',description:'Status unknown; original local package requires review.',
  primaryAction:null,remoteVerified:false,durableVerified:false,updatedAt:item.updatedAt};
 switch(item.state){
  case STATES.QUEUED:
   return {...base,kind:INBOX_KIN.PENDING,heading:'Saved locally — not sent',
    description:online?'Your synthetic package is held on this device. Tap Send to test transmission.':'No internet connection. Your synthetic package remains in the local Outbox.',
    primaryAction:online?'SEND_TEST':null,priority:'attention'};
  case STATES.SENDING:
   return {...base,kind:INBOX_KINDS.CHECKING,heading:'Checking upload receipt',
    description:'The transmission result is not yet confirmed. Do not delete the original.',priority:'normal'};
  case STATES.UNCONFIRMED:
   return {...base,kind:INBOX_KINDS.ACTION,heading:'Delivery not confirmed',
    description:'Original test package retained locally. '+(item.lastError||'Connection unavailable.')+
      (online?' Check the receipt and retry.':' Retry when connected.'),
    primaryAction:online?'RETRY_TEST':null,priority:'attention'};
  case STATES.NEEDS_REVIEW:
   return {...base,kind:INBOX_KINDS.ACTION,heading:'Your attention is needed',
    description:'The synthetic job is paused pending review. Original remains local.',
    primaryAction:online?'RETRY_TEST':null,priority:'attention'};
  case STATES.TEST_RECEIVED:
   return {...base,kind:INBOX_KINDS.TEST_ACK,heading:'Temporary test receiver confirmed',
    description:'Checksum and test receipt matched. TEST ONLY: no permanent cloud archive, no department update.',
    remoteVerified:true,durableVerified:false,priority:'normal'};
  default:return base;
 }
}
export function inboxProjection(items,opts={}){
 return items.map(item=>statusMessage(item,opts))
  .sort((a,b)=>(b.priority==='attention')-(a.priority==='attention')||
               b.updatedAt.localeCompare(a.updatedAt));
}
// Build DOM using textContent only to avoid inserting untrusted message HTML.
export function renderLocalInbox(container,items,{online=true,onAction=null}={}){
 if(!container)throw Error('Inbox container required');
 container.replaceChildren();
 const messages=inboxProjection(items,{online});
 if(!messages.length){const empty=document.createElement('p');
  empty.textContent='No synthetic test messages yet.';container.append(empty);return messages}
 for(const message of messages){
  const section=document.createElement('section');section.className='inbox-entry';
  const title=document.createElement('strong');title.textContent=message.heading;
  const body=document.createElement('p');body.textContent=message.description;
  section.append(title,body);
  if(message.primaryAction&&typeof onAction==='function'){
   const button=document.createElement('button');button.type='button';
   button.textContent=message.primaryAction==='SEND_TEST'?'Send synthetic test':'Check and retry test';
   button.onclick=()=>onAction(message.id,message.primaryAction);
   section.append(button);
  }
  container.append(section)
 }
 return messages;
}
