'use strict';
(() => {
  const key = 'icit-incident-review-replay-v1';
  const fresh = () => ({version:1,status:'new',reviewed:false,outcome:'',audit:['Replay: native review event opens DEMO-GATE-01.']});
  const allowed = ['new','reviewing','follow_up','closed'];
  const outcomes = ['', 'follow', 'authorized', 'secured', 'uncertain'];
  let state = fresh(), persistent = true;
  try {
    const saved = JSON.parse(localStorage.getItem(key));
    if (saved?.version === 1 && allowed.includes(saved.status) && typeof saved.reviewed === 'boolean' && outcomes.includes(saved.outcome) && Array.isArray(saved.audit) && saved.audit.length <= 20 && saved.audit.every(x => typeof x === 'string' && x.length < 200)) state = saved;
  } catch { persistent = false; }
  const el = id => document.getElementById(id);
  const labels = {new:'New',reviewing:'In review',follow_up:'Follow-up',closed:'Closed'};
  const say = text => { el('feedback').textContent = text; };
  function render() {
    el('case-status').textContent = labels[state.status];
    el('footage-reviewed').checked = state.reviewed;
    el('outcome').value = state.outcome;
    el('ack').disabled = state.status !== 'new';
    el('follow').disabled = !['reviewing','follow_up'].includes(state.status);
    el('close').disabled = !['reviewing','follow_up'].includes(state.status);
    el('footage-reviewed').disabled = el('outcome').disabled = state.status === 'closed';
    el('audit').replaceChildren(...state.audit.map(text => { const li=document.createElement('li');li.textContent=text;return li; }));
    try { localStorage.setItem(key,JSON.stringify(state)); } catch { persistent=false; }
    el('storage-note').textContent = persistent ? 'Replay state is saved locally in this browser. Duplicate events keep one case.' : 'Browser storage is unavailable; this replay works until the page is reloaded.';
  }
  el('footage-reviewed').addEventListener('change', e => { state.reviewed=e.target.checked;render(); });
  el('outcome').addEventListener('change', e => { state.outcome=e.target.value;render(); });
  el('ack').onclick = () => {
    if(state.status !== 'new') return;
    state.status='reviewing';state.audit.push('Review started. Check footage and authorized access.');say('Review the evidence before choosing an outcome.');render();
  };
  el('follow').onclick = () => {
    if(!['reviewing','follow_up'].includes(state.status)) return;
    if(!['follow','uncertain'].includes(state.outcome)) {say('Choose a caretaker check or “unable to verify” to record follow-up.');return;}
    const note = state.outcome==='follow' ? 'Example follow-up: await duty caretaker check.' : 'Example follow-up: unable to verify; case remains open.';
    if(state.status==='follow_up' && state.audit.at(-1)===note) {say('This follow-up is already recorded.');return;}
    state.status='follow_up';state.audit.push(note);state.audit=state.audit.slice(-20);say('Follow-up recorded in this replay. No message was sent.');render();
  };
  el('close').onclick = () => {
    if(!['reviewing','follow_up'].includes(state.status)) return;
    if(!state.reviewed || !['authorized','secured'].includes(state.outcome)) {say('Review footage and select a confirmed outcome. Uncertain cases stay open.');return;}
    state.status='closed';state.audit.push(state.outcome==='authorized' ? 'Example closure: authorized maintenance confirmed; footage reviewed.' : 'Example closure: gate secured and follow-up complete; footage reviewed.');say('Replay case closed with an explicit outcome. The lab is unchanged.');render();
  };
  el('replay').onclick = () => {say('Duplicate event ignored. DEMO-GATE-01 and its current review state are preserved.');};
  el('reset').onclick = () => {state=fresh();say('Replay reset. This changes only the browser example.');render();};
  document.querySelectorAll('[data-seek]').forEach(button => button.addEventListener('click', async () => {
    const video=document.querySelector('video');
    try {
      if(video.readyState<1) await new Promise((resolve,reject) => {video.addEventListener('loadedmetadata',resolve,{once:true});video.addEventListener('error',reject,{once:true});video.load();});
      video.currentTime=Number(button.dataset.seek);video.scrollIntoView({block:'center'});await video.play();
    } catch {say('Playback could not start automatically. Use the video controls or download the MP4.');}
  }));
  render();
})();
