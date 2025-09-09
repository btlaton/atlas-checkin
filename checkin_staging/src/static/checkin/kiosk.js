// Simple kiosk interactions: submit check-in, resend QR, staff unlock shortcut
(function() {
  const form = document.getElementById('checkin-form');
  const result = document.getElementById('result');
  form?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const data = Object.fromEntries(new FormData(form).entries());
    const r = await fetch('/api/checkin', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    const j = await r.json();
    if (j.ok) {
      result.textContent = `Welcome, ${j.member_name}! Enjoy your workout.`;
      form.reset();
    } else {
      result.textContent = j.error || 'Check-in failed';
    }
  });

  const rform = document.getElementById('resend-form');
  const rres = document.getElementById('resend-result');
  rform?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const data = Object.fromEntries(new FormData(rform).entries());
    const r = await fetch('/api/qr/resend', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    const j = await r.json();
    rres.textContent = j.ok ? 'Check your email for your code.' : (j.error || 'Unable to send email');
  });

  // Staff unlock: triple-tap header to go to admin login
  const logo = document.getElementById('logo');
  let taps = 0; let lastTap = 0;
  logo?.addEventListener('click', () => {
    const now = Date.now();
    if (now - lastTap < 600) {
      taps += 1;
    } else {
      taps = 1;
    }
    lastTap = now;
    if (taps >= 3) { window.location.href = '/admin/login'; }
  });

  // QR scanning with native BarcodeDetector if available
  const startBtn = document.getElementById('start-scan');
  const stopBtn = document.getElementById('stop-scan');
  const scanSupport = document.getElementById('scan-support');
  const scanResult = document.getElementById('scan-result');
  const video = document.getElementById('preview');
  const canvas = document.getElementById('frame');
  const ctx = canvas?.getContext('2d');
  let mediaStream = null;
  let rafId = null;
  let detector = null;
  let jsqrReady = false;

  async function checkSupport() {
    const supported = 'BarcodeDetector' in window;
    if (supported) {
      try {
        const formats = await window.BarcodeDetector.getSupportedFormats();
        if (!formats.includes('qr_code')) throw new Error('No QR support');
        detector = new window.BarcodeDetector({ formats: ['qr_code'] });
        scanSupport.textContent = 'Your browser supports camera QR scanning.';
      } catch (e) {
        await tryLoadJsQR();
      }
    } else {
      await tryLoadJsQR();
    }
  }

  async function tryLoadJsQR() {
    if (window.jsQR) { jsqrReady = true; scanSupport.textContent = 'Fallback scanner enabled.'; return; }
    await new Promise((resolve) => {
      const s = document.createElement('script');
      s.src = '/static/checkin/jsqr.min.js';
      s.onload = () => { jsqrReady = !!window.jsQR; resolve(); };
      s.onerror = () => resolve();
      document.head.appendChild(s);
    });
    if (jsqrReady) {
      scanSupport.textContent = 'Fallback scanner enabled.';
    } else {
      await new Promise((resolve) => {
        const s2 = document.createElement('script');
        s2.src = 'https://cdn.jsdelivr.net/npm/jsqr@1.4.0/dist/jsQR.js';
        s2.onload = () => { jsqrReady = !!window.jsQR; resolve(); };
        s2.onerror = () => resolve();
        document.head.appendChild(s2);
      });
      if (jsqrReady) {
        scanSupport.textContent = 'Fallback scanner enabled.';
      } else {
        scanSupport.textContent = 'Camera scanning not supported. Use manual entry or paste token.';
        startBtn.disabled = true;
      }
    }
  }

  async function startScan() {
    try {
      mediaStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' }, audio: false });
      video.srcObject = mediaStream;
      await video.play();
      startBtn.disabled = true; stopBtn.disabled = false;
      tick();
    } catch (e) {
      scanResult.textContent = 'Unable to access camera';
    }
  }

  function stopScan() {
    if (rafId) cancelAnimationFrame(rafId);
    if (mediaStream) mediaStream.getTracks().forEach(t => t.stop());
    startBtn.disabled = false; stopBtn.disabled = true;
  }

  async function tick() {
    if (!video.videoWidth) { rafId = requestAnimationFrame(tick); return; }
    canvas.width = video.videoWidth; canvas.height = video.videoHeight;
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    try {
      let raw = null;
      if (detector) {
        const bitmaps = await createImageBitmap(canvas);
        const codes = await detector.detect(bitmaps);
        if (codes && codes.length) {
          raw = codes[0].rawValue || codes[0].rawValue;
        }
      } else if (jsqrReady) {
        const imgData = ctx.getImageData(0, 0, canvas.width, canvas.height);
        const code = window.jsQR(imgData.data, imgData.width, imgData.height, { inversionAttempts: 'dontInvert' });
        if (code && code.data) raw = code.data;
      }
      if (raw) {
        stopScan();
        scanResult.textContent = 'Detected QR. Checking you in…';
        const r = await fetch('/api/checkin', {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ qr_token: raw })
        });
        const j = await r.json();
        result.textContent = j.ok ? `Welcome, ${j.member_name}! Enjoy your workout.` : (j.error || 'Check-in failed');
        return;
      }
    } catch (e) {}
    rafId = requestAnimationFrame(tick);
  }

  const upload = document.getElementById('upload-image');
  upload?.addEventListener('change', async () => {
    const file = upload.files && upload.files[0];
    if (!file) return;
    if (!jsqrReady) { scanResult.textContent = 'Image scanning unavailable on this device.'; return; }
    const img = new Image();
    img.onload = async () => {
      canvas.width = img.width; canvas.height = img.height; ctx.drawImage(img, 0, 0);
      const imgData = ctx.getImageData(0, 0, canvas.width, canvas.height);
      const code = window.jsQR(imgData.data, imgData.width, imgData.height, { inversionAttempts: 'dontInvert' });
      if (code && code.data) {
        const r = await fetch('/api/checkin', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ qr_token: code.data }) });
        const j = await r.json();
        result.textContent = j.ok ? `Welcome, ${j.member_name}! Enjoy your workout.` : (j.error || 'Check-in failed');
      } else {
        scanResult.textContent = 'No QR found in image.';
      }
    };
    img.src = URL.createObjectURL(file);
  });

  checkSupport();
  startBtn?.addEventListener('click', startScan);
  stopBtn?.addEventListener('click', stopScan);
})();

