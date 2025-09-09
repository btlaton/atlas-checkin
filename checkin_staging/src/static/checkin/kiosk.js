/* Kiosk interactions: scan QR with front camera, manual check-in (phone), resend QR */
(function() {
  // Manual check-in
  const form = document.getElementById('checkin-form');
  const result = document.getElementById('result');
  form?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const data = Object.fromEntries(new FormData(form).entries());
    const payload = { phone: data.phone || '' };
    const r = await fetch('/api/checkin', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    const j = await r.json();
    result.textContent = j.ok ? `Welcome, ${j.member_name}! Enjoy your workout.` : (j.error || 'Check-in failed');
    if (j.ok) form.reset();
  });

  // Resend QR
  const rform = document.getElementById('resend-form');
  const rres = document.getElementById('resend-result');
  rform?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const data = Object.fromEntries(new FormData(rform).entries());
    const payload = {};
    if (data.email) payload.email = data.email;
    if (data.phone) payload.phone = data.phone;
    const r = await fetch('/api/qr/resend', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    const j = await r.json();
    rres.textContent = j.ok ? 'Check your inbox for your QR code.' : (j.error || 'Unable to send QR code');
  });

  // Staff unlock: triple-tap header
  const logo = document.getElementById('logo');
  let taps = 0, lastTap = 0;
  logo?.addEventListener('click', () => {
    const now = Date.now();
    taps = (now - lastTap < 600) ? taps + 1 : 1; lastTap = now;
    if (taps >= 3) window.location.href = '/admin/login';
  });

  // QR scanning (front camera default)
  const scanBtn = document.getElementById('scan-button');
  const scanWrap = document.getElementById('scan-wrap');
  const scanSupport = document.getElementById('scan-support');
  const scanResult = document.getElementById('scan-result');
  const video = document.getElementById('preview');
  const canvas = document.getElementById('frame');
  const ctx = canvas.getContext('2d');
  let mediaStream = null, rafId = null, detector = null, jsqrReady = false;

  async function checkSupport() {
    const supported = 'BarcodeDetector' in window;
    if (supported) {
      try {
        const formats = await window.BarcodeDetector.getSupportedFormats();
        if (!formats.includes('qr_code')) throw new Error('No QR support');
        detector = new window.BarcodeDetector({ formats: ['qr_code'] });
        scanSupport.textContent = 'Camera scanning ready.';
      } catch { await tryLoadJsQR(); }
    } else { await tryLoadJsQR(); }
  }

  async function tryLoadJsQR() {
    if (window.jsQR) { jsqrReady = true; scanSupport.textContent = 'Fallback scanner enabled.'; return; }
    await new Promise((resolve) => { const s = document.createElement('script'); s.src = '/static/checkin/jsqr.min.js'; s.onload = () => { jsqrReady = !!window.jsQR; resolve(); }; s.onerror = () => resolve(); document.head.appendChild(s); });
    if (jsqrReady) scanSupport.textContent = 'Fallback scanner enabled.'; else {
      await new Promise((resolve) => { const s2 = document.createElement('script'); s2.src = 'https://cdn.jsdelivr.net/npm/jsqr@1.4.0/dist/jsQR.js'; s2.onload = () => { jsqrReady = !!window.jsQR; resolve(); }; s2.onerror = () => resolve(); document.head.appendChild(s2); });
      scanSupport.textContent = jsqrReady ? 'Fallback scanner enabled.' : 'Camera scanning not supported on this device. Use manual entry.';
      if (!jsqrReady) scanBtn.disabled = true;
    }
  }

  async function startScan() {
    try {
      mediaStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'user' } }, audio: false });
      video.srcObject = mediaStream; await video.play();
      scanBtn.classList.add('hidden'); scanWrap.classList.remove('hidden');
      tick();
    } catch { scanResult.textContent = 'Unable to access camera'; }
  }
  function stopScan() { if (rafId) cancelAnimationFrame(rafId); if (mediaStream) mediaStream.getTracks().forEach(t => t.stop()); scanWrap.classList.add('hidden'); scanBtn.classList.remove('hidden'); }

  async function tick() {
    if (!video.videoWidth) { rafId = requestAnimationFrame(tick); return; }
    canvas.width = video.videoWidth; canvas.height = video.videoHeight; ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    try {
      let raw = null;
      if (detector) { const bm = await createImageBitmap(canvas); const codes = await detector.detect(bm); if (codes && codes.length) raw = codes[0].rawValue || codes[0].rawValue; }
      else if (jsqrReady) { const imgData = ctx.getImageData(0, 0, canvas.width, canvas.height); const code = window.jsQR(imgData.data, imgData.width, imgData.height, { inversionAttempts: 'dontInvert' }); if (code && code.data) raw = code.data; }
      if (raw) { stopScan(); scanResult.textContent = 'Detected QR. Checking you in…'; const r = await fetch('/api/checkin', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ qr_token: raw }) }); const j = await r.json(); result.textContent = j.ok ? `Welcome, ${j.member_name}! Enjoy your workout.` : (j.error || 'Check-in failed'); return; }
    } catch {}
    rafId = requestAnimationFrame(tick);
  }

  checkSupport();
  scanBtn?.addEventListener('click', startScan);
})();

