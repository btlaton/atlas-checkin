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
  const detailMeta = document.getElementById('detail-meta');

  let page = 1;
  const perPage = 25;
  let total = 0;
  let totalPages = 1;
  let searchTimer = null;

  function esc(s){ return (s==null?'':String(s)).replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])); }

  function scheduleFetch() {
    if (searchTimer) clearTimeout(searchTimer);
    searchTimer = setTimeout(() => { fetchPage(); }, 200);
  }

  async function fetchPage() {
    const params = new URLSearchParams();
    if (qEl.value.trim()) params.set('q', qEl.value.trim());
    if (tierEl.value) params.set('tier', tierEl.value);
    if (statusEl.value) params.set('status', statusEl.value);
    params.set('page', page);
    params.set('per_page', perPage);
    const r = await fetch(`/api/admin/members?${params.toString()}`);
    const j = await r.json();
    if (!j.ok) { rowsEl.innerHTML = `<tr><td colspan="5">${esc(j.error||'Failed to load')}</td></tr>`; return; }
    const list = j.items || [];
    total = j.total || 0;
    totalPages = Math.max(1, Math.ceil(total / (j.per_page || perPage)));
    countEl.textContent = `${total.toLocaleString()} members`;
    pageInfo.textContent = `Page ${j.page} of ${totalPages}`;
    rowsEl.innerHTML = list.map(m => `
      <tr data-id="${m.id}">
        <td><a href="#" class="rowlink" data-id="${m.id}">${esc(m.name||'')}</a></td>
        <td>${esc(m.email_lower||'')}</td>
        <td>${esc(m.tier||'')}</td>
        <td>${esc(m.status||'')}</td>
        <td>${esc(m.updated_at||'')}</td>
      </tr>
    `).join('');
    prevBtn.disabled = (page <= 1);
    nextBtn.disabled = (page >= totalPages);
  }

  rowsEl?.addEventListener('click', async (e)=>{
    const a = e.target.closest('.rowlink');
    if (!a) return;
    e.preventDefault();
    const id = a.getAttribute('data-id');
    const r = await fetch(`/api/admin/members/${id}`);
    const j = await r.json();
    if (!j.ok) {
      detail.style.display='block';
      detailMeta.textContent = '';
      detailContent.textContent = j.error||'Failed to load detail';
      return;
    }
    const m = j.member;
    const cis = j.recent_checkins||[];
    detail.style.display = 'block';
    detailMeta.textContent = m ? `${esc((m.status||'').toUpperCase())} • Tier: ${esc(m.tier||'None')}` : '';
    detailContent.innerHTML = `
      <div class="detail-grid">
        <div><span class="label">Name</span><span>${esc(m.name||'')}</span></div>
        <div><span class="label">Email</span><span>${esc(m.email_lower||'')}</span></div>
        <div><span class="label">Phone</span><span>${esc(m.phone_e164||'')}</span></div>
        <div><span class="label">Updated</span><span>${esc(m.updated_at||'')}</span></div>
      </div>
      <div class="detail-section">
        <h3>Recent Check-ins</h3>
        <ul class="detail-list">${cis.map(ci=>`<li>${esc(ci.timestamp)} • ${esc(ci.method)}</li>`).join('') || '<li class="muted">No recent activity</li>'}</ul>
      </div>
    `;
  });

  qEl?.addEventListener('input', () => { page = 1; scheduleFetch(); });
  applyBtn?.addEventListener('click', ()=>{ page=1; fetchPage(); });
  prevBtn?.addEventListener('click', ()=>{ if(page>1){page--; fetchPage();} });
  nextBtn?.addEventListener('click', ()=>{ if(page<totalPages){ page++; fetchPage(); } });

  fetchPage();
})();
