(function(){
  const btn = document.getElementById('start');
  const res = document.getElementById('result');
  function v(id){ const el=document.getElementById(id); return el?el.value.trim():''; }
  btn?.addEventListener('click', async ()=>{
    res.textContent = 'Creating checkout…';
    const body = {
      name: v('name'),
      email: v('email'),
      phone: v('phone'),
      birthday: v('birthday'),
      address: v('address'),
      price_id: v('price')
    };
    try {
      const r = await fetch('/api/signup/checkout_session', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body) });
      const j = await r.json();
      if (!j.ok) { res.textContent = j.error || 'Failed to create Checkout session'; return; }
      window.location.href = j.url;
    } catch (e){ res.textContent = 'Failed to create Checkout session'; }
  });
})();

