(function(){
  const tabButtons = Array.from(document.querySelectorAll('.tab-btn'));
  const panels = Array.from(document.querySelectorAll('.tab-panel'));

  // Quick sale elements
  const openCatalogBtn = document.getElementById('open-catalog');
  const refreshOrdersBtn = document.getElementById('refresh-orders');
  const orderList = document.getElementById('order-list');

  const sheet = document.getElementById('sheet');
  const sheetClose = document.getElementById('sheet-close');
  const sheetProductsView = document.getElementById('sheet-products-view');
  const sheetSearch = document.getElementById('sheet-search');
  const sheetProductGroups = document.getElementById('sheet-product-groups');
  const sheetConfig = document.getElementById('sheet-config');
  const sheetSession = document.getElementById('sheet-session');
  const sheetTitle = document.getElementById('sheet-title');
  const sheetSubtitle = document.getElementById('sheet-subtitle');
  const qtyInput = document.getElementById('qty-input');
  const qtyInc = document.getElementById('qty-inc');
  const qtyDec = document.getElementById('qty-dec');
  const sheetTotal = document.getElementById('sheet-total');
  const sheetSubmit = document.getElementById('sheet-submit');
  const sheetError = document.getElementById('sheet-error');

  const sessionStatus = document.getElementById('session-status');
  const sessionQrImg = document.getElementById('session-qr-img');
  const sessionDone = document.getElementById('session-done');
  const sessionShare = document.getElementById('session-share');
  const sessionOrderNumber = document.getElementById('session-order-number');
  const sessionTotal = document.getElementById('session-total');

  // Metrics / check-in elements
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

  let catalogLoaded = false;
  let catalogData = [];
  let filteredCatalog = [];
  const catalogIndex = new Map();
  const categoryOrder = {
    beverages: 0,
    drinks: 0,
    apparel: 1,
    'open-gym': 2,
    passes: 2,
    services: 3,
    'personal-training': 3,
    memberships: 4,
    'trainer-program': 5,
  };

  let selectedProduct = null;
  let activeOrder = null;
  let pollTimer = null;

  function showTab(target) {
    tabButtons.forEach(btn => {
      const active = btn.dataset.tabTarget === target;
      btn.classList.toggle('active', active);
      btn.setAttribute('aria-selected', active ? 'true' : 'false');
    });
    panels.forEach(panel => {
      panel.classList.toggle('active', panel.id === `tab-${target}`);
    });
    if (target === 'sale' && !catalogLoaded) {
      loadCatalog();
    }
  }

  tabButtons.forEach(btn => btn.addEventListener('click', () => showTab(btn.dataset.tabTarget)));
  showTab('sale');

  async function loadCatalog() {
    try {
      const res = await fetch('/api/commerce/catalog');
      const json = await res.json();
      if (!json.ok) throw new Error(json.error || 'Unable to load catalog');
      catalogData = (json.products || []).filter(prod => (prod.prices || []).length);
      catalogIndex.clear();
      catalogData.forEach(item => catalogIndex.set(String(item.id), item));
      filteredCatalog = catalogData.slice();
      renderProductSheet();
      catalogLoaded = true;
      loadRecentOrders();
    } catch (err) {
      sheetProductGroups.innerHTML = `<p class="muted">${(err && err.message) || 'Unable to load catalog.'}</p>`;
    }
  }

  function renderProductSheet() {
    if (!filteredCatalog.length) {
      sheetProductGroups.innerHTML = '<p class="muted">No products found.</p>';
      return;
    }
    const grouped = new Map();
    filteredCatalog.forEach(item => {
      const key = item.product_kind || 'other';
      if (!grouped.has(key)) grouped.set(key, []);
      grouped.get(key).push(item);
    });
    const orderedKeys = Array.from(grouped.keys()).sort((a, b) => {
      const wa = categoryOrder[a] ?? 99;
      const wb = categoryOrder[b] ?? 99;
      if (wa !== wb) return wa - wb;
      return a.localeCompare(b);
    });
    sheetProductGroups.innerHTML = orderedKeys.map(key => {
      const label = formatCategoryLabel(key);
      const items = grouped.get(key).sort((a, b) => a.name.localeCompare(b.name));
      const list = items.map(item => {
        const price = currencyFmt.format((item.prices?.[0]?.amount_cents || 0) / 100);
        return `<button class="item" data-product-id="${item.id}"><span class="name">${escapeHtml(item.name)}</span><span class="price">${price}</span></button>`;
      }).join('');
      return `<div class="sheet-group"><h3>${escapeHtml(label)}</h3><div class="list">${list}</div></div>`;
    }).join('');

    sheetProductGroups.querySelectorAll('.item').forEach(btn => {
      btn.addEventListener('click', () => {
        const product = catalogIndex.get(btn.dataset.productId);
        if (product) {
          showSheetView('config');
          openSheetForProduct(product);
        }
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
        return key.charAt(0).toUpperCase() + key.slice(1).replace('-', ' ');
    }
  }

  function showSheetView(view) {
    const views = [sheetProductsView, sheetConfig, sheetSession];
    views.forEach(v => {
      if (!v) return;
      if ((view === 'products' && v === sheetProductsView) ||
          (view === 'config' && v === sheetConfig) ||
          (view === 'session' && v === sheetSession)) {
        v.removeAttribute('hidden');
        if (v.classList.contains('sheet-view')) v.classList.add('active');
      } else {
        v.setAttribute('hidden', '');
        if (v.classList.contains('sheet-view')) v.classList.remove('active');
      }
    });
  }

  function openSheet() {
    sheet.removeAttribute('hidden');
    document.body.style.overflow = 'hidden';
  }

  function closeSheet() {
    sheet.setAttribute('hidden', '');
    document.body.style.overflow = '';
    selectedProduct = null;
    activeOrder = null;
    sheetError.textContent = '';
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
    if (catalogLoaded && sheetSearch) {
      sheetSearch.value = '';
      filteredCatalog = catalogData.slice();
      renderProductSheet();
    }
    if (sessionShare) {
      sessionShare.disabled = false;
      sessionShare.style.display = '';
      sessionShare.textContent = 'Share Link';
    }
    if (sessionQrImg) {
      sessionQrImg.src = '';
    }
  }

  sheetClose?.addEventListener('click', closeSheet);
  sheet?.addEventListener('click', evt => {
    if (evt.target === sheet) closeSheet();
  });

  openCatalogBtn?.addEventListener('click', () => {
    if (!catalogLoaded) {
      sheetProductGroups.innerHTML = '<p class="muted">Loading catalog…</p>';
      showSheetView('products');
      openSheet();
      if (sheetSearch) sheetSearch.value = '';
      loadCatalog().then(() => {
        sheetSearch?.focus({ preventScroll: true });
      });
    } else {
      filteredCatalog = catalogData.slice();
      renderProductSheet();
      sheetSearch.value = '';
      showSheetView('products');
      openSheet();
      sheetSearch?.focus({ preventScroll: true });
    }
  });

  sheetSearch?.addEventListener('input', () => {
    const term = sheetSearch.value.trim().toLowerCase();
    if (!term) {
      filteredCatalog = catalogData.slice();
    } else {
      filteredCatalog = catalogData.filter(item => (item.name || '').toLowerCase().includes(term));
    }
    renderProductSheet();
  });

  function openSheetForProduct(product) {
    selectedProduct = product;
    qtyInput.value = '1';
    sheetTitle.textContent = product.name;
    const unitPrice = product.prices?.[0]?.amount_cents || 0;
    sheetSubtitle.textContent = `${currencyFmt.format(unitPrice / 100)} • ${formatCategoryLabel(product.product_kind || 'item')}`;
    updateSheetTotals();
    sheetError.textContent = '';
  }

  function updateSheetTotals() {
    if (!selectedProduct) return;
    const qty = Math.max(1, parseInt(qtyInput.value, 10) || 1);
    const unit = selectedProduct.prices?.[0]?.amount_cents || 0;
    sheetTotal.textContent = currencyFmt.format((unit * qty) / 100);
  }

  qtyDec?.addEventListener('click', () => {
    const next = Math.max(1, (parseInt(qtyInput.value, 10) || 1) - 1);
    qtyInput.value = String(next);
    updateSheetTotals();
  });
  qtyInc?.addEventListener('click', () => {
    const next = Math.max(1, (parseInt(qtyInput.value, 10) || 1) + 1);
    qtyInput.value = String(next);
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
      showSheetView('session');
      updateSessionView(activeOrder);
      if (activeOrder.checkout_url) {
        sessionQrImg.src = `/staff/orders/${activeOrder.id}/qr.png?${Date.now()}`;
      }
      if (pollTimer) clearInterval(pollTimer);
      pollTimer = setInterval(() => pollOrderStatus(activeOrder.id), 5000);
      pollOrderStatus(activeOrder.id);
      loadRecentOrders();
    } catch (err) {
      sheetError.textContent = err.message || 'Unable to create order.';
    } finally {
      sheetSubmit.disabled = false;
      sheetSubmit.textContent = 'Generate Payment Link';
    }
  });

  async function pollOrderStatus(orderId) {
    try {
      const res = await fetch(`/api/commerce/orders/${orderId}`);
      const json = await res.json();
      if (!json.ok) return;
      activeOrder = json.order;
      updateSessionView(activeOrder);
      const terminal = ['paid', 'failed', 'expired', 'refunded'];
      if (terminal.includes((activeOrder.status || '').toLowerCase())) {
        if (pollTimer) {
          clearInterval(pollTimer);
          pollTimer = null;
        }
        loadRecentOrders();
      }
    } catch (err) {
      console.warn('Order poll failed', err);
    }
  }

  function updateSessionView(order) {
    const status = (order.status || '').toLowerCase();
    sessionStatus.textContent = statusLabel(status);
    sessionStatus.className = `status-badge ${status}`;
    sessionOrderNumber.textContent = `Order ${order.order_number}`;
    sessionTotal.textContent = `Total ${currencyFmt.format((order.total_cents || 0) / 100)}`;
    const hasUrl = Boolean(order.checkout_url);
    sessionShare.disabled = !hasUrl;
    sessionShare.style.display = hasUrl ? '' : 'none';
  }

  function statusLabel(status) {
    switch (status) {
      case 'paid': return 'Paid';
      case 'failed': return 'Payment failed';
      case 'expired': return 'Expired';
      case 'refunded': return 'Refunded';
      default: return 'Awaiting payment';
    }
  }

  sessionDone?.addEventListener('click', closeSheet);

  sessionShare?.addEventListener('click', async () => {
    if (!activeOrder || !activeOrder.checkout_url) return;
    const url = activeOrder.checkout_url;
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

  refreshOrdersBtn?.addEventListener('click', loadRecentOrders);

  async function loadRecentOrders() {
    try {
      const res = await fetch('/api/commerce/orders?limit=10');
      const json = await res.json();
      if (!json.ok) throw new Error(json.error || 'Unable to load recent orders');
      renderRecentOrders(json.orders || []);
    } catch (err) {
      orderList.innerHTML = `<li class="muted">${err.message || 'Unable to load recent orders.'}</li>`;
    }
  }

  function renderRecentOrders(orders) {
    const visible = (orders || []).filter(o => (o.status || '').toLowerCase() !== 'awaiting_payment');
    if (!visible.length) {
      orderList.innerHTML = '<li class="muted">No completed orders yet</li>';
      return;
    }
    orderList.innerHTML = visible.map(order => {
      const when = order.created_at ? formatRelative(order.created_at) : '';
      const guest = order.guest_name || order.guest_email;
      return `
        <li class="order-card">
          <div class="title">${escapeHtml(order.summary || order.order_number)}</div>
          <div class="row">
            <span class="status-pill ${order.status}">${statusLabel(order.status)}</span>
            <span>${currencyFmt.format((order.total_cents || 0) / 100)}</span>
            ${guest ? `<span>${escapeHtml(guest)}</span>` : ''}
            <span>${escapeHtml(when)}</span>
          </div>
        </li>
      `;
    }).join('');
  }

  function formatRelative(ts) {
    const date = parseTimestamp(ts);
    if (!date) return ts;
    const now = new Date();
    const diffMs = now - date;
    const diffMin = Math.round(diffMs / 60000);
    if (diffMin < 1) return 'Just now';
    if (diffMin < 60) return `${diffMin} min ago`;
    const diffHr = Math.round(diffMin / 60);
    if (diffHr < 24) return `${diffHr} hr ago`;
    return dateFmt.format(date);
  }

  function escapeHtml(str) {
    return String(str || '').replace(/[&<>]/g, s => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[s]));
  }

  function parseTimestamp(ts) {
    if (!ts) return null;
    try {
      const normalized = String(ts).replace(' ', 'T');
      const date = new Date(normalized);
      if (!isNaN(date.getTime())) return date;
    } catch {}
    return null;
  }

  // Check-in metrics
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
})();
