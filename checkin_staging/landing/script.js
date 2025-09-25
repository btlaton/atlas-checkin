const navToggle = document.getElementById('navToggle');
const siteHeader = document.querySelector('.site-header');

navToggle?.addEventListener('click', () => {
  siteHeader.classList.toggle('open');
});

// Smooth scroll for internal anchors
document.querySelectorAll('a[href^="#"]').forEach(link => {
  link.addEventListener('click', evt => {
    const targetId = link.getAttribute('href');
    if (targetId.length > 1) {
      evt.preventDefault();
      const target = document.querySelector(targetId);
      if (target) {
        target.scrollIntoView({ behavior: 'smooth', block: 'start' });
        siteHeader.classList.remove('open');
      }
    }
  });
});
