/**
 * RESQ PULSE — Main Client Interactions Script
 */

document.addEventListener("DOMContentLoaded", () => {
  initSidebar();
  initThemeToggle();
  initLiveClock();
  initConfirmationModals();
  initAutoDismissFlashes();
});

/* --------------------------------------------------------------------------
   Sidebar & Mobile Drawer Controls
   -------------------------------------------------------------------------- */
function initSidebar() {
  const toggleBtn = document.getElementById("sidebarToggleBtn");
  const sidebar = document.getElementById("mainSidebar");

  if (toggleBtn && sidebar) {
    toggleBtn.addEventListener("click", () => {
      sidebar.classList.toggle("open");
    });

    // Close on outside click on mobile screens
    document.addEventListener("click", (e) => {
      if (
        window.innerWidth <= 768 &&
        sidebar.classList.contains("open") &&
        !sidebar.contains(e.target) &&
        !toggleBtn.contains(e.target)
      ) {
        sidebar.classList.remove("open");
      }
    });
  }
}

/* --------------------------------------------------------------------------
   Theme Switcher (Dark Navy / Light Mode)
   -------------------------------------------------------------------------- */
function initThemeToggle() {
  const themeBtn = document.getElementById("themeToggleBtn");
  const storedTheme = localStorage.getItem("resq_pulse_theme") || "dark";

  document.documentElement.setAttribute("data-theme", storedTheme);
  updateThemeIcon(storedTheme);

  if (themeBtn) {
    themeBtn.addEventListener("click", () => {
      const current = document.documentElement.getAttribute("data-theme") || "dark";
      const nextTheme = current === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", nextTheme);
      localStorage.setItem("resq_pulse_theme", nextTheme);
      updateThemeIcon(nextTheme);
    });
  }
}

function updateThemeIcon(theme) {
  const icon = document.getElementById("themeIcon");
  if (!icon) return;
  if (theme === "light") {
    // Show Moon
    icon.innerHTML = `<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>`;
  } else {
    // Show Sun
    icon.innerHTML = `
      <circle cx="12" cy="12" r="5"></circle>
      <line x1="12" y1="1" x2="12" y2="3"></line>
      <line x1="12" y1="21" x2="12" y2="23"></line>
      <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line>
      <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line>
      <line x1="1" y1="12" x2="3" y2="12"></line>
      <line x1="21" y1="12" x2="23" y2="12"></line>
      <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line>
      <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line>
    `;
  }
}

/* --------------------------------------------------------------------------
   Live Operation Center Clock
   -------------------------------------------------------------------------- */
function initLiveClock() {
  const clockEl = document.getElementById("liveClock");
  if (!clockEl) return;

  function update() {
    const now = new Date();
    clockEl.textContent = now.toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    }) + " UTC+05:30";
  }

  update();
  setInterval(update, 1000);
}

/* --------------------------------------------------------------------------
   Toast Notifications Generator
   -------------------------------------------------------------------------- */
function showToast(message, type = "info", duration = 4000) {
  let container = document.getElementById("toastContainer");
  if (!container) {
    container = document.createElement("div");
    container.id = "toastContainer";
    container.className = "toast-container";
    document.body.appendChild(container);
  }

  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `
    <span style="font-size: 14px; font-weight: 700;">•</span>
    <span style="flex: 1;">${message}</span>
  `;

  container.appendChild(toast);

  setTimeout(() => {
    toast.style.transition = "opacity 0.4s ease, transform 0.4s ease";
    toast.style.opacity = "0";
    toast.style.transform = "translateX(50px)";
    setTimeout(() => toast.remove(), 400);
  }, duration);
}

/* --------------------------------------------------------------------------
   Auto-dismiss Flash Banners
   -------------------------------------------------------------------------- */
function initAutoDismissFlashes() {
  const flashes = document.querySelectorAll(".flash-alert");
  flashes.forEach((f) => {
    setTimeout(() => {
      f.style.transition = "opacity 0.5s ease";
      f.style.opacity = "0";
      setTimeout(() => f.remove(), 500);
    }, 5500);
  });
}

/* --------------------------------------------------------------------------
   Consequential Action Confirmations
   -------------------------------------------------------------------------- */
function initConfirmationModals() {
  const confirmElements = document.querySelectorAll("[data-confirm]");
  confirmElements.forEach((el) => {
    el.addEventListener("click", (e) => {
      const msg = el.getAttribute("data-confirm") || "Are you sure you want to proceed?";
      if (!window.confirm(msg)) {
        e.preventDefault();
      }
    });
  });
}
