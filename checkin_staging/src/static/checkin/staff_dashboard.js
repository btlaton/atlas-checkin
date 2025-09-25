(function(){
  const metricToday = document.getElementById('metric-today');
  const metricHour = document.getElementById('metric-hour');
  const metricMembers = document.getElementById('metric-members');
  const trendBars = document.getElementById('trend-bars');
  const trendCaption = document.getElementById('trend-caption');
  const recentList = document.getElementById('recent');
  const qaContact = document.getElementById('qa-contact');
  const qaSend = document.getElementById('qa-send');
  const qaResult = document.getElementById('qa-result');

  const dateFmt = new Intl.DateTimeFormat(undefined, { weekday: 'short', month: 'short', day: 'numeric' });
  const timeFmt = new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' });

  function parseTs(ts) {
    if (!ts) return null;
    let str = String(ts).replace(' ', 'T');
    // If no timezone info, treat as local by not appending Z
    const date = new Date(str);
    if (!isNaN(date.getTime())) return date;
    return null;
  }

  function formatRecentTimestamp(ts) {
    const d = parseTs(ts);
    if (!d) return ts;
    const now = new Date();
    const sameDay = d.toDateString() === now.toDateString();
    const diffMs = now - d;
    const diffMinutes = Math.round(diffMs / 60000);
    if (diffMinutes < 60 && diffMinutes >= 0) {
      if (diffMinutes <= 1) return 'Just now';
      return `${diffMinutes} min ago`;
    }
    if (sameDay) {
      return `Today • ${timeFmt.format(d)}`;
    }
    const yesterday = new Date(now);
    yesterday.setDate(now.getDate() - 1);
    if (d.toDateString() === yesterday.toDateString()) {
      return `Yesterday • ${timeFmt.format(d)}`;
    }
    return `${dateFmt.format(d)} • ${timeFmt.format(d)}`;
  }

  function esc(s){ return (s==null?'':String(s)).replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])); }

  async function loadMetrics() {
    try {
      const r = await fetch('/api/staff/metrics');
      const j = await r.json();
      if (!j.ok) { renderFallback(); return; }
      metricToday.textContent = Number(j.today_total || 0).toLocaleString();
      metricHour.textContent = Number(j.last_hour_total || 0).toLocaleString();
      metricMembers.textContent = Number(j.today_unique || 0).toLocaleString();
      renderTrend(j.trend || []);
      renderRecents(j.recent || []);
      const nowLabel = timeFmt.format(new Date());
      trendCaption.textContent = `Updated ${nowLabel}`;
    } catch {
      renderFallback();
    }
  }

  function renderFallback() {
    metricToday.textContent = '—';
    metricHour.textContent = '—';
    metricMembers.textContent = '—';
    trendBars.innerHTML = '<div class="muted">Unable to load trend</div>';
    recentList.innerHTML = '<li class="muted">Unable to load recent check-ins</li>';
  }

  function renderTrend(points) {
    if (!Array.isArray(points) || points.length === 0) {
      trendBars.innerHTML = '<div class="muted">No activity yet</div>';
      return;
    }
    const max = Math.max(1, ...points.map(p => Number(p.count || 0)));
    trendBars.innerHTML = points.map(p => {
      const count = Number(p.count || 0);
      const height = Math.max(6, Math.round((count / max) * 140));
      const labelDate = p.date ? dateFmt.format(new Date(String(p.date) + 'T00:00:00')) : '';
      return `
        <div class="trend-bar">
          <div class="count">${count}</div>
          <div class="bar" style="height:${height}px"></div>
          <div class="label">${esc(labelDate)}</div>
        </div>
      `;
    }).join('');
  }

  function renderRecents(items) {
    if (!Array.isArray(items) || items.length === 0) {
      recentList.innerHTML = '<li class="muted">No check-ins yet today</li>';
      return;
    }
    recentList.innerHTML = items.map(item => {
      const name = esc(item.name || item.member_name || 'Member');
      const method = esc((item.method || '').toUpperCase());
      const when = formatRecentTimestamp(item.timestamp || item.time || '');
      return `
        <li class="recent-item">
          <div class="name">${name}</div>
          <div class="meta">
            <span class="time-label">${esc(when)}</span>
            ${method ? `<span class="badge">${method}</span>` : ''}
          </div>
        </li>
      `;
    }).join('');
  }

  qaSend?.addEventListener('click', async () => {
    const v = qaContact.value.trim();
    if (!v) { qaResult.textContent = 'Enter an email first.'; return; }
    if (!v.includes('@')) { qaResult.textContent = 'Use the member email on file.'; return; }
    qaResult.textContent = 'Sending…';
    try {
      const r = await fetch('/api/qr/resend', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ email: v }) });
      const j = await r.json();
      if (j.ok) {
        qaResult.textContent = j.wallet ? 'Email sent with QR + Apple Wallet pass.' : 'QR email sent.';
        qaContact.value = '';
      } else {
        qaResult.textContent = j.error || 'Failed to send';
      }
    } catch {
      qaResult.textContent = 'Failed to send';
    }
  });

  loadMetrics();
  setInterval(loadMetrics, 60000);
  window.addEventListener('gymsense:checkin', loadMetrics);
})();
