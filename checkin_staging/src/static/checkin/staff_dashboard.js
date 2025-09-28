(function(){
  const tabButtons = Array.from(document.querySelectorAll('.tab-btn'));
  const panels = Array.from(document.querySelectorAll('.tab-panel'));
  const catalogGroups = document.getElementById('catalog-groups');
  const catalogSearch = document.getElementById('catalog-search');
  const openCatalogBtn = document.getElementById('open-catalog');
  const refreshOrdersBtn = document.getElementById('refresh-orders');
  const orderList = document.getElementById('order-list');
  const viewRecentLink = document.getElementById('view-recent-link');

  const sheet = document.getElementById('sheet');
  const sheetClose = document.getElementById('sheet-close');
  const sheetConfig = document.getElementById('sheet-config');
  const sheetSession = document.getElementById('sheet-session');
  const sheetTitle = document.getElementById('sheet-title');
  const sheetSubtitle = document.getElementById('sheet-subtitle');
  const qtyInput = document.getElementById('qty-input');
  const qtyInc = document.getElementById('qty-inc');
  const qtyDec = document.getElementById('qty-dec');
  const sheetSubmit = document.getElementById('sheet-submit');
  const sheetError = document.getElementById('sheet-error');
  const sheetTotal = document.getElementById('sheet-total');
  const sessionQrImg = document.getElementById('session-qr-img');
  const sessionStatus = document.getElementById('session-status');
  const sessionDone = document.getElementById('session-done');
  const sessionShare = document.getElementById('session-share');
  const sessionOrderNumber = document.getElementById('session-order-number');
  const sessionTotal = document.getElementById('session-total');

  const metricToday = document.getElementById('metric-today');
  const metricHour = document.getElementById('metric-hour');
  const metricMembers = document.getElementById('metric-members');
  const trendBars = document.getElementById('trend-bars');
  const trendCaption = document.getElementById('trend-caption');
  const recentList = document.getElementById('recent');
  const qaContact = document.getElementById('qa-contact');
  const qaSend = document.getElementById('qa-send');
  const qaResult = document.getElementById('qa-result');

  const currencyFmt = new Intl.NumberFormat(undefined, { style: 'currency', currency: 'USD' });
  const dateFmt = new Intl.DateTimeFormat(undefined, { weekday: 'short', month: 'short', day: 'numeric' });
  const timeFmt = new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' });

  let catalogData = null;
  let filteredCatalog = null;
  const catalogIndex = new Map();
  let activeOrder = null;
  let pollTimer = null;
  let catalogLoaded = false;

  const categoryOrder = {
    beverages: 0,
    drinks: 0,
    'beverages-drinks': 0,
    apparel: 1,
    'open-gym': 2,
    passes: 2,
    services: 3,
    'personal-training': 3,
    memberships: 4,
    'trainer-program': 5,
  };

  function showTab(id) {
    tabButtons.forEach(btn => {
      const active = btn.dataset.tabTarget === id;
      btn.classList.toggle('active', active);
      btn.setAttribute('aria-selected', active ? 'true' : 'false');
    });
    panels.forEach(panel => {
      panel.classList.toggle('active', panel.id === `tab-${id}`);
    });
    if (id === 'sale' && !catalogLoaded) {
      loadCatalog();
    }
  }

  tabButtons.forEach(btn => {
    btn.addEventListener('click', () => showTab(btn.dataset.tabTarget));
  });

  showTab('sale');

  async function loadCatalog() {
    try {
      const res = await fetch('/api/commerce/catalog');
      const json = await res.json();
      if (!json.ok) throw new Error(json.error || 'Failed to load catalog');
      catalogData = json.products || [];
      catalogIndex.clear();
      catalogData.forEach(item => {
        if (item && item.id != null) catalogIndex.set(String(item.id), item);
      });
      filteredCatalog = catalogData.slice();
      renderCatalog();
      catalogLoaded = true;
      loadRecentOrders();
    } catch (err) {
      catalogGroups.innerHTML = `<p class="muted">${(err && err.message) || 'Unable to load catalog.'}</p>`;
    }
  }

  function renderCatalog() {
    if (!filteredCatalog || filteredCatalog.length === 0) {
      catalogGroups.innerHTML = '<p class="muted">No products to show.</p>';
      return;
    }
    const grouped = new Map();
    filteredCatalog.forEach(item => {
      const key = item.product_kind || 'other';
      if (!grouped.has(key)) grouped.set(key, []);
      grouped.get(key).push(item);
    });
    const orderedKeys = Array.from(grouped.keys()).sort((a, b) => {
      const wA = categoryOrder[a] ?? 99;
      const wB = categoryOrder[b] ?? 99;
      if (wA !== wB) return wA - wB;
      return a.localeCompare(b);
    });
    const html = orderedKeys.map(key => {
      const items = grouped.get(key);
      items.sort((a, b) => a.name.localeCompare(b.name));
      const label = formatCategoryLabel(key);
      const cards = items.map(item => `
        <article class="catalog-card" data-product-id="${item.id}">
          <div class="name">${escapeHtml(item.name)}</div>
          <div class="price">${currencyFmt.format((item.prices?.[0]?.amount_cents || 0) / 100)}</div>
        </article>
      `).join('');
      return `<div class="catalog-group"><h3>${label}</h3><div class="catalog-grid">${cards}</div></div>`;
    }).join('');
    catalogGroups.innerHTML = html;
    Array.from(document.querySelectorAll('.catalog-card')).forEach(card => {
      card.addEventListener('click', () => {
        const data = catalogIndex.get(card.dataset.productId);
        if (data) openSheetForProduct(data);
      });
    });
  }

  function formatCategoryLabel(key) {
    switch (key) {
      case 'beverages':
      case 'drinks':
        return 'Drinks & Refreshments';
      case 'apparel':
        return 'Apparel';
      case 'open-gym':
        return 'Passes';
      case 'personal-training':
      case 'services':
        return 'Services';
      case 'memberships':
        return 'Memberships';
      case 'trainer-program':
        return 'Trainer Program';
      default:
        return key.slice(0,1).toUpperCase() + key.slice(1).replace('-', ' ');
    }
  }

  catalogSearch?.addEventListener('input', () => {
    const term = catalogSearch.value.trim().toLowerCase();
    if (!catalogData) return;
    if (!term) {
      filteredCatalog = catalogData.slice();
    } else {
      filteredCatalog = catalogData.filter(item => {
        return (item.name || '').toLowerCase().includes(term);
      });
    }
    renderCatalog();
  });

  openCatalogBtn?.addEventListener('click', () => {
    const firstCard = document.querySelector('.catalog-card');
    if (firstCard) {
      const data = catalogIndex.get(firstCard.dataset.productId);
      if (data) openSheetForProduct(data);
    } else {
      loadCatalog();
    }
  });

  function openSheetForProduct(product) {
    if (!product) return;
    selectedProduct = product;
    qtyInput.value = '1';
    activeOrder = null;
    updateSheetTotals();
    sheetTitle.textContent = product.name;
    sheetSubtitle.textContent = currencyFmt.format((product.prices?.[0]?.amount_cents || 0) / 100);
    showSheetView('config');
    sheet.removeAttribute('hidden');
    document.body.style.overflow = 'hidden';
  }

  function closeSheet() {
    sheet.setAttribute('hidden', '');
    document.body.style.overflow = '';
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  sheetClose?.addEventListener('click', closeSheet);
  sheet?.addEventListener('click', e => {
    if (e.target === sheet) closeSheet();
  });

  let selectedProduct = null;

  function updateSheetTotals() {
    if (!selectedProduct) return;
    const qty = Math.max(1, parseInt(qtyInput.value, 10) || 1);
    const priceCents = selectedProduct.prices?.[0]?.amount_cents || 0;
    sheetTotal.textContent = currencyFmt.format((priceCents * qty) / 100);
    sheetSubtitle.textContent = `${currencyFmt.format(priceCents / 100)} • ${selectedProduct.product_kind?.replace('-', ' ') || 'item'}`;
  }

  qtyDec?.addEventListener('click', () => {
    const val = Math.max(1, (parseInt(qtyInput.value, 10) || 1) - 1);
    qtyInput.value = String(val);
    updateSheetTotals();
  });
  qtyInc?.addEventListener('click', () => {
    const val = Math.max(1, (parseInt(qtyInput.value, 10) || 1) + 1);
    qtyInput.value = String(val);
    updateSheetTotals();
  });
  qtyInput?.addEventListener('input', updateSheetTotals);

  sheetSubmit?.addEventListener('click', async () => {
    if (!selectedProduct) return;
    const price = selectedProduct.prices?.[0];
    if (!price) {
      sheetError.textContent = 'Price missing for this product.';
      return;
    }
    const quantity = Math.max(1, parseInt(qtyInput.value, 10) || 1);
    sheetSubmit.disabled = true;
    sheetSubmit.textContent = 'Generating…';
    sheetError.textContent = '';
    try {
      const payload = {
        items: [{
          product_id: selectedProduct.id,
          price_type: price.price_type,
          quantity
        }],
        order_type: selectedProduct.product_kind === 'membership_plan' ? 'membership' : 'retail'
      };
      const res = await fetch('/api/commerce/orders', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const json = await res.json();
      if (!json.ok) throw new Error(json.error || 'Failed to create order');
      activeOrder = json.order;
      showCheckoutSession();
      loadRecentOrders();
    } catch (err) {
      sheetError.textContent = err.message || 'Unable to create order.';
    } finally {
      sheetSubmit.disabled = false;
      sheetSubmit.textContent = 'Generate Payment Link';
    }
  });

  function showSheetView(view) {
    if (view === 'config') {
      sheetConfig.removeAttribute('hidden');
      sheetConfig.classList.add('active');
      sheetSession.setAttribute('hidden', '');
      sheetSession.classList.remove('active');
    } else {
      sheetSession.removeAttribute('hidden');
      sheetSession.classList.add('active');
      sheetConfig.setAttribute('hidden', '');
      sheetConfig.classList.remove('active');
    }
  }

  function showCheckoutSession() {
    if (!activeOrder) return;
    showSheetView('session');
    updateSessionView(activeOrder);
    const qrUrl = `/staff/orders/${activeOrder.id}/qr.png?${Date.now()}`;
    sessionQrImg.src = qrUrl;
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(() => pollOrderStatus(activeOrder.id), 5000);
    pollOrderStatus(activeOrder.id);
  }

  async function pollOrderStatus(orderId) {
    try {
      const res = await fetch(`/api/commerce/orders/${orderId}`);
      const json = await res.json();
      if (!json.ok) return;
      activeOrder = json.order;
      updateSessionView(activeOrder);
      if (json.order.status === 'paid' || json.order.status === 'failed' || json.order.status === 'expired' || json.order.status === 'refunded') {
        if (pollTimer) {
          clearInterval(pollTimer);
          pollTimer = null;
        }
      }
    } catch (err) {
      console.warn('Failed to poll order', err);
    }
  }

  function updateSessionView(order) {
    const status = order.status || 'awaiting_payment';
    sessionStatus.textContent = statusLabel(status);
    sessionStatus.className = `status-badge ${status}`;
    sessionOrderNumber.textContent = `Order ${order.order_number}`;
    sessionTotal.textContent = `Total ${currencyFmt.format((order.total_cents || 0) / 100)}`;
  }

  function statusLabel(status) {
    switch ((status || '').toLowerCase()) {
      case 'paid': return 'Paid';
      case 'failed': return 'Payment failed';
      case 'expired': return 'Expired';
      case 'refunded': return 'Refunded';
      default: return 'Awaiting payment';
    }
  }

  sessionDone?.addEventListener('click', () => {
    closeSheet();
  });

  sessionShare?.addEventListener('click', async () => {
    if (!activeOrder) return;
    const url = activeOrder.checkout_url;
    if (!url) return;
    if (navigator.share) {
      try {
        await navigator.share({ title: 'Atlas Gym Checkout', url });
        return;
      } catch (err) {
        if (err && err.name === 'AbortError') return;
      }
    }
    try {
      await navigator.clipboard.writeText(url);
      sessionShare.textContent = 'Link copied';
      setTimeout(() => { sessionShare.textContent = 'Share Link'; }, 1500);
    } catch (err) {
      console.warn('Share failed', err);
    }
  });

  async function loadRecentOrders() {
    try {
      const res = await fetch('/api/commerce/orders?limit=5');
      const json = await res.json();
      if (!json.ok) throw new Error(json.error || 'Failed');
      renderRecentOrders(json.orders || []);
    } catch (err) {
      orderList.innerHTML = `<li class="muted">${err.message || 'Unable to load recent orders.'}</li>`;
    }
  }

  refreshOrdersBtn?.addEventListener('click', loadRecentOrders);

  function renderRecentOrders(orders) {
    if (!orders.length) {
      orderList.innerHTML = '<li class="muted">No orders yet</li>';
      return;
    }
    orderList.innerHTML = orders.map(order => {
      const created = order.created_at ? formatRelative(order.created_at) : '';
      return `
        <li class="order-card">
          <div class="title">${escapeHtml(order.summary || order.order_number)}</div>
          <div class="row">
            <span class="status-pill ${order.status}">${statusLabel(order.status)}</span>
            <span>${currencyFmt.format((order.total_cents || 0) / 100)}</span>
            <span>${escapeHtml(created)}</span>
          </div>
        </li>
      `;
    }).join('');
  }

  function formatRelative(ts) {
    const date = parseTs(ts);
    if (!date) return ts;
    const now = new Date();
    const diff = now - date;
    const mins = Math.round(diff / 60000);
    if (mins < 1) return 'Just now';
    if (mins < 60) return `${mins} min ago`;
    const hours = Math.round(mins / 60);
    if (hours < 24) return `${hours} hr ago`;
    return dateFmt.format(date);
  }

  function escapeHtml(str) {
    return String(str || '').replace(/[&<>]/g, s => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[s]));
  }

  function parseTs(ts) {
    if (!ts) return null;
    const normalized = String(ts).replace(' ', 'T');
    const date = new Date(normalized);
    if (!isNaN(date.getTime())) return date;
    return null;
  }

  // Metrics / Check-in section
  async function loadMetrics() {
    if (!metricToday) return;
    try {
      const res = await fetch('/api/staff/metrics');
      const json = await res.json();
      if (!json.ok) throw new Error();
      metricToday.textContent = Number(json.today_total || 0).toLocaleString();
      metricHour.textContent = Number(json.last_hour_total || 0).toLocaleString();
      metricMembers.textContent = Number(json.today_unique || 0).toLocaleString();
      renderTrend(json.trend || []);
      renderRecents(json.recent || []);
      trendCaption.textContent = `Updated ${timeFmt.format(new Date())}`;
    } catch {
      metricToday.textContent = metricHour.textContent = metricMembers.textContent = '—';
      trendBars.innerHTML = '<div class="muted">Unable to load trend</div>';
      recentList.innerHTML = '<li class="muted">Unable to load recent check-ins</li>';
    }
  }

  function renderTrend(points) {
    if (!trendBars) return;
    if (!Array.isArray(points) || !points.length) {
      trendBars.innerHTML = '<div class="muted">No activity yet</div>';
      return;
    }
    const max = Math.max(1, ...points.map(p => Number(p.count || 0)));
    trendBars.innerHTML = points.map(p => {
      const count = Number(p.count || 0);
      const height = Math.max(6, Math.round((count / max) * 140));
      const labelDate = p.date ? dateFmt.format(new Date(`${p.date}T00:00:00`)) : '';
      return `
        <div class="trend-bar">
          <div class="count">${count}</div>
          <div class="bar" style="height:${height}px"></div>
          <div class="label">${escapeHtml(labelDate)}</div>
        </div>
      `;
    }).join('');
  }

  function renderRecents(items) {
    if (!recentList) return;
    if (!Array.isArray(items) || !items.length) {
      recentList.innerHTML = '<li class="muted">No check-ins yet today</li>';
      return;
    }
    recentList.innerHTML = items.map(item => {
      const name = escapeHtml(item.name || item.member_name || 'Member');
      const when = formatRelative(item.timestamp || item.time || '');
      const method = escapeHtml((item.method || '').toUpperCase());
      return `
        <li class="recent-item">
          <div class="name">${name}</div>
          <div class="meta">
            <span>${when}</span>
            ${method ? `<span class="status-pill">${method}</span>` : ''}
          </div>
        </li>
      `;
    }).join('');
  }

  qaSend?.addEventListener('click', async () => {
    const email = qaContact.value.trim();
    if (!email) { qaResult.textContent = 'Enter a member email first.'; return; }
    if (!email.includes('@')) { qaResult.textContent = 'Use the email on file.'; return; }
    qaResult.textContent = 'Sending…';
    try {
      const res = await fetch('/api/qr/resend', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email })
      });
      const json = await res.json();
      if (!json.ok) throw new Error(json.error || 'Failed to send');
      qaResult.textContent = json.wallet ? 'Sent QR + Wallet pass.' : 'QR email sent.';
      qaContact.value = '';
    } catch (err) {
      qaResult.textContent = err.message || 'Failed to send';
    }
  });

  loadMetrics();
  setInterval(loadMetrics, 60000);
  window.addEventListener('gymsense:checkin', loadMetrics);

  viewRecentLink?.addEventListener('click', evt => {
    evt.preventDefault();
    document.getElementById('recent-orders')?.scrollIntoView({ behavior: 'smooth' });
  });

})();
