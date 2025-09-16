/* Kiosk interactions: streamlined UI, front camera default, one-of field validation, success overlay */
(function() {
  const emailResult = document.getElementById('email-result');
  const overlay = document.getElementById('success-overlay');
  const overlayText = document.getElementById('success-text');
  const aimHint = document.getElementById('aim-hint');
  const scanBtn = document.getElementById('scan-button');

  // Ensure overlay starts hidden
  overlay?.classList.add('hidden');

  function firstName(name) {
    const n = (name || '').trim();
    if (!n) return 'Member';
    return n.split(/\s+/)[0];
  }

  // Audio chime — persistent context with iOS unlock + audible envelope
  let audioCtx = null;
  function getAudioCtx() {
    try {
      if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      if (audioCtx.state === 'suspended') audioCtx.resume();
    } catch {}
    return audioCtx;
  }
  window.addEventListener('touchstart', () => { try { getAudioCtx(); } catch {} }, { once: true });
  scanBtn?.addEventListener('click', () => { try { getAudioCtx(); } catch {} });
  function playChime() {
    try {
      const ctx = getAudioCtx();
      if (!ctx) return;
      const now = ctx.currentTime;
      const sequence = [
        { f: 880, start: now, dur: 0.12 },
        { f: 1175, start: now + 0.13, dur: 0.14 },
      ];
      sequence.forEach(({ f, start, dur }) => {
        const o = ctx.createOscillator();
        const g = ctx.createGain();
        o.type = 'triangle'; o.frequency.value = f;
        o.connect(g); g.connect(ctx.destination);
        g.gain.setValueAtTime(0.0001, start);
        g.gain.exponentialRampToValueAtTime(0.3, start + 0.02);
        g.gain.exponentialRampToValueAtTime(0.0001, start + dur);
        o.start(start); o.stop(start + dur + 0.02);
      });
    } catch {}
  }

  function showSuccess(name) {
    overlayText.textContent = `Thanks, ${firstName(name)}, enjoy your workout!`;
    overlay.classList.remove('hidden');
    playChime();
    setTimeout(() => overlay.classList.add('hidden'), 5000);
  }

  // Email-driven check-in/resend actions
  const emailForm = document.getElementById('member-email-form');
  emailForm?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const submitter = e.submitter || document.activeElement;
    const action = submitter?.dataset?.action;
    const data = Object.fromEntries(new FormData(emailForm).entries());
    const email = (data.email || '').trim();
    if (!email) { emailResult.textContent = 'Enter your email to continue.'; return; }

    if (action === 'resend') {
      const r = await fetch('/api/qr/resend', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email }) });
      const j = await r.json();
      if (j.ok) {
        emailResult.textContent = 'Check your email for your QR code.';
        emailForm.reset();
      } else {
        emailResult.textContent = j.error || 'Unable to send QR code.';
      }
      return;
    }

    // Default: attempt check-in via email lookup
    const r = await fetch('/api/checkin', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email }) });
    const j = await r.json();
    if (j.ok) {
      showSuccess(j.member_name || email);
      emailForm.reset();
      emailResult.textContent = '';
    } else {
      emailResult.textContent = j.error || 'Check-in failed.';
    }
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
  const scanWrap = document.getElementById('scan-wrap');
  const scanSupport = document.getElementById('scan-support');
  const scanResult = document.getElementById('scan-result');
  const video = document.getElementById('preview');
  const canvas = document.getElementById('frame');
  const ctx = canvas.getContext('2d');
  let mediaStream = null, rafId = null, detector = null, jsqrReady = false;
  let facing = 'user'; // default to front camera for mounted iPad
  const sampleCanvas = document.createElement('canvas');
  const sampleCtx = sampleCanvas.getContext('2d');
  const MAX_SAMPLE_W = 480;

  async function checkSupport() {
    if (scanSupport) scanSupport.textContent = '';
    const supported = 'BarcodeDetector' in window;
    if (supported) {
      try {
        const formats = await window.BarcodeDetector.getSupportedFormats();
        if (!formats.includes('qr_code')) throw new Error('No QR support');
        detector = new window.BarcodeDetector({ formats: ['qr_code'] });
      } catch { await tryLoadJsQR(); }
    } else { await tryLoadJsQR(); }
    // Update debug
    const dbg = document.getElementById('scan-debug');
    if (dbg) {
      const bd = detector ? 'yes' : 'no';
      const jq = (typeof window.jsQR === 'function') ? 'yes' : 'no';
      dbg.textContent = `BD:${bd} jsQR:${jq}`;
      dbg.classList.remove('hidden');
    }
    if (scanSupport) {
      if (detector || jsqrReady) {
        scanSupport.textContent = detector ? 'Camera ready' : 'Camera ready (fallback)';
      }
    }
  }

  async function tryLoadJsQR() {
    if (typeof window.jsQR === 'function') { jsqrReady = true; return; }
    // Prefer CDN; fallback to local if present
    await new Promise((resolve) => { const s1 = document.createElement('script'); s1.src = 'https://cdn.jsdelivr.net/npm/jsqr@1.4.0/dist/jsQR.js'; s1.onload = () => { jsqrReady = (typeof window.jsQR === 'function'); resolve(); }; s1.onerror = () => resolve(); document.head.appendChild(s1); });
    if (!jsqrReady) {
      await new Promise((resolve) => { const s2 = document.createElement('script'); s2.src = '/static/checkin/jsqr.min.js'; s2.onload = () => { jsqrReady = (typeof window.jsQR === 'function'); resolve(); }; s2.onerror = () => resolve(); document.head.appendChild(s2); });
      if (!jsqrReady) { scanSupport.textContent = 'Camera scanning not supported on this device. Use manual entry.'; scanBtn.disabled = true; }
    }
  }

  async function startScan() {
    try {
      try {
        mediaStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { exact: facing } }, audio: false });
      } catch {
        mediaStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: facing } }, audio: false });
      }
      video.srcObject = mediaStream; await video.play();
      scanBtn.classList.add('hidden'); scanWrap.classList.remove('hidden');
      if (scanSupport) scanSupport.textContent = 'Camera active';
      if (aimHint) {
        aimHint.classList.remove('hidden');
        // Auto-hide hint after a few seconds
        setTimeout(()=>aimHint.classList.add('hidden'), 6000);
      }
      tick();
    } catch { scanResult.textContent = 'Unable to access camera'; }
  }
  function stopScan() {
    if (rafId) cancelAnimationFrame(rafId);
    if (mediaStream) mediaStream.getTracks().forEach(t => t.stop());
    scanWrap.classList.add('hidden');
    scanBtn.classList.remove('hidden');
    if (aimHint) aimHint.classList.add('hidden');
    if (scanSupport) scanSupport.textContent = 'Tap to scan again';
  }

  async function tick() {
    if (!video.videoWidth) { rafId = requestAnimationFrame(tick); return; }
    canvas.width = video.videoWidth; canvas.height = video.videoHeight;
    // If using front camera, un-mirror the frame for decoders
    if (facing === 'user') {
      ctx.save();
      ctx.scale(-1, 1);
      ctx.drawImage(video, -canvas.width, 0, canvas.width, canvas.height);
      ctx.restore();
    } else {
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    }
    try {
      let raw = null;
      if (detector) {
        const bm = await createImageBitmap(canvas);
        const codes = await detector.detect(bm);
        if (codes && codes.length) raw = codes[0].rawValue || codes[0].rawValue;
      }
      if (!raw && jsqrReady) {
        const ratio = canvas.width / canvas.height;
        let sw = Math.min(MAX_SAMPLE_W, canvas.width);
        let sh = Math.floor(sw / ratio);
        sampleCanvas.width = sw; sampleCanvas.height = sh;
        if (facing === 'user') {
          sampleCtx.save();
          sampleCtx.scale(-1, 1);
          sampleCtx.drawImage(video, -sw, 0, sw, sh);
          sampleCtx.restore();
        } else {
          sampleCtx.drawImage(video, 0, 0, sw, sh);
        }
        const imgData = sampleCtx.getImageData(0, 0, sw, sh);
        const code = window.jsQR(imgData.data, imgData.width, imgData.height, { inversionAttempts: 'dontInvert' });
        if (code && code.data) raw = code.data;
      }
      if (raw) {
        stopScan();
        if (aimHint) aimHint.classList.add('hidden');
        const r = await fetch('/api/checkin', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ qr_token: raw }) });
        const j = await r.json();
        if (j.ok) { showSuccess(j.member_name || 'Member'); } else { emailResult.textContent = j.error || 'Check-in failed'; }
        return;
      }
      // Update debug dims while scanning
      const dbg = document.getElementById('scan-debug');
      if (dbg) dbg.textContent = `BD:${detector?'yes':'no'} jsQR:${typeof window.jsQR==='function'?'yes':'no'} v:${video.videoWidth}x${video.videoHeight}`;
    } catch {}
    rafId = requestAnimationFrame(tick);
  }

  checkSupport();
  scanBtn?.addEventListener('click', startScan);

  // No additional suggestions or autocomplete to avoid accidental mismatches
})();
