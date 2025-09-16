(function(){
  const kpiTotal = document.getElementById('kpi-total');
  const kpiUnique = document.getElementById('kpi-unique');
  const spark = document.getElementById('spark');
  const recent = document.getElementById('recent');
  const qaContact = document.getElementById('qa-contact');
  const qaSend = document.getElementById('qa-send');
  const qaResult = document.getElementById('qa-result');

  function esc(s){ return (s==null?'':String(s)).replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])); }

  async function load() {
    try {
      const r = await fetch('/api/staff/metrics');
      const j = await r.json();
      if (!j.ok) { kpiTotal.textContent='—'; kpiUnique.textContent='—'; recent.innerHTML = '<li class="muted">Failed to load</li>'; return; }
      kpiTotal.textContent = j.today_total;
      kpiUnique.textContent = j.today_unique;
      drawSpark(j.trend||[]);
      recent.innerHTML = (j.recent||[]).map(x=>`<li><b>${esc(x.name||'Member')}</b> — ${esc(x.method||'')} • ${esc(x.timestamp||'')}</li>`).join('') || '<li class="muted">No check-ins yet</li>';
    } catch {
      // ignore
    }
  }

  function drawSpark(points){
    const w=200, h=56, pad=6;
    if (!Array.isArray(points) || points.length===0) { spark.innerHTML=''; return; }
    const max = Math.max(1, ...points.map(p=>p.count||0));
    const step = (w - pad*2) / Math.max(1, points.length-1);
    let d = '';
    points.forEach((p, i) => {
      const x = pad + i*step;
      const y = h - pad - (p.count||0)/max*(h - pad*2);
      d += (i===0?`M ${x} ${y}`:` L ${x} ${y}`);
    });
    spark.innerHTML = `
      <polyline fill="none" stroke="#39FF14" stroke-width="2" points="${points.map((p,i)=>{
        const x = pad + i*step; const y = h - pad - (p.count||0)/max*(h - pad*2); return `${x},${y}`; }).join(' ')}"/>
    `;
  }

  qaSend?.addEventListener('click', async ()=>{
    const v = qaContact.value.trim();
    if (!v) { qaResult.textContent = 'Enter an email first.'; return; }
    if (!v.includes('@')) { qaResult.textContent = 'Use the member email on file.'; return; }
    qaResult.textContent = 'Sending…';
    const body = { email: v };
    try {
      const r = await fetch('/api/qr/resend', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body) });
      const j = await r.json();
      qaResult.textContent = j.ok ? 'Sent.' : (j.error || 'Failed to send');
    } catch { qaResult.textContent = 'Failed to send'; }
  });

  load();
})();
