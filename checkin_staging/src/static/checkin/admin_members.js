(function(){
  const qEl = document.getElementById('q');
  const tierEl = document.getElementById('tier');
  const statusEl = document.getElementById('status');
  const applyBtn = document.getElementById('apply');
  const rowsEl = document.getElementById('rows');
  const countEl = document.getElementById('count');
  const pageInfo = document.getElementById('pageinfo');
  const prevBtn = document.getElementById('prev');
  const nextBtn = document.getElementById('next');
  const detail = document.getElementById('detail');
  const detailContent = document.getElementById('detail-content');

  let page = 1;
  const perPage = 25;

  function esc(s){ return (s==null?'':String(s)).replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])); }

  async function fetchPage() {
    const params = new URLSearchParams();
    if (qEl.value.trim()) params.set('q', qEl.value.trim());
    if (tierEl.value) params.set('tier', tierEl.value);
    if (statusEl.value) params.set('status', statusEl.value);
    params.set('page', page);
    params.set('per_page', perPage);
    const r = await fetch(`/api/admin/members?${params.toString()}`);
    const j = await r.json();
    if (!j.ok) { rowsEl.innerHTML = `<tr><td colspan="6">${esc(j.error||'Failed to load')}</td></tr>`; return; }
    const list = j.items || [];
    countEl.textContent = `${j.total||0} members`;
    pageInfo.textContent = `Page ${j.page} of ${Math.max(1, Math.ceil((j.total||0)/j.per_page))}`;
    rowsEl.innerHTML = list.map(m => `
      <tr data-id="${m.id}">
        <td><a href="#" class="rowlink" data-id="${m.id}">${esc(m.name||'')}</a></td>
        <td>${esc(m.email_lower||'')}</td>
        <td>${esc(m.phone_e164||'')}</td>
        <td>${esc(m.tier||'')}</td>
        <td>${esc(m.status||'')}</td>
        <td>${esc(m.updated_at||'')}</td>
      </tr>
    `).join('');
  }

  rowsEl?.addEventListener('click', async (e)=>{
    const a = e.target.closest('.rowlink');
    if (!a) return;
    e.preventDefault();
    const id = a.getAttribute('data-id');
    const r = await fetch(`/api/admin/members/${id}`);
    const j = await r.json();
    if (!j.ok) { detail.style.display='block'; detailContent.textContent = j.error||'Failed to load detail'; return; }
    const m = j.member;
    const cis = j.recent_checkins||[];
    detail.style.display = 'block';
    detailContent.innerHTML = `
      <div><b>Name:</b> ${esc(m.name||'')}</div>
      <div><b>Email:</b> ${esc(m.email_lower||'')}</div>
      <div><b>Phone:</b> ${esc(m.phone_e164||'')}</div>
      <div><b>Tier:</b> ${esc(m.tier||'')}</div>
      <div><b>Status:</b> ${esc(m.status||'')}</div>
      <div><b>Updated:</b> ${esc(m.updated_at||'')}</div>
      <div style="margin-top:8px;"><b>Recent Check-Ins:</b></div>
      <ul>${cis.map(ci=>`<li>${esc(ci.timestamp)} — ${esc(ci.method)}</li>`).join('')||'<li class="muted">None</li>'}</ul>
    `;
  });

  applyBtn?.addEventListener('click', ()=>{ page=1; fetchPage(); });
  prevBtn?.addEventListener('click', ()=>{ if(page>1){page--; fetchPage();} });
  nextBtn?.addEventListener('click', ()=>{ page++; fetchPage(); });

  fetchPage();
})();

