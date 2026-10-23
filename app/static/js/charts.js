/**
 * RESQ PULSE — Chart.js Operations Analytics Configuration
 */

document.addEventListener("DOMContentLoaded", () => {
  initDashboardCharts();
  initReportCharts();
});

function initDashboardCharts() {
  // 1. Emergency Trend Chart
  const trendCanvas = document.getElementById("trendChart");
  if (trendCanvas) {
    const labels = JSON.parse(trendCanvas.getAttribute("data-labels") || "[]");
    const dataPoints = JSON.parse(trendCanvas.getAttribute("data-points") || "[]");

    const ctx = trendCanvas.getContext("2d");
    new Chart(ctx, {
      type: "line",
      data: {
        labels: labels,
        datasets: [
          {
            label: "Emergencies Registered",
            data: dataPoints,
            borderColor: "#14b8a6",
            backgroundColor: "rgba(20, 184, 166, 0.15)",
            borderWidth: 2.5,
            fill: true,
            tension: 0.35,
            pointBackgroundColor: "#14b8a6",
            pointRadius: 4,
            pointHoverRadius: 6,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: "#0f172a",
            borderColor: "rgba(255, 255, 255, 0.1)",
            borderWidth: 1,
            titleColor: "#f8fafc",
            bodyColor: "#94a3b8",
            padding: 10,
          },
        },
        scales: {
          x: {
            grid: { color: "rgba(255, 255, 255, 0.05)" },
            ticks: { color: "#64748b", font: { size: 11 } },
          },
          y: {
            beginAtZero: true,
            grid: { color: "rgba(255, 255, 255, 0.05)" },
            ticks: {
              color: "#64748b",
              font: { size: 11 },
              precision: 0,
            },
          },
        },
      },
    });
  }

  // 2. Ambulance Status Distribution Doughnut Chart
  const statusCanvas = document.getElementById("statusDoughnutChart");
  if (statusCanvas) {
    const avail = parseInt(statusCanvas.getAttribute("data-avail") || "0", 10);
    const busy = parseInt(statusCanvas.getAttribute("data-busy") || "0", 10);
    const out = parseInt(statusCanvas.getAttribute("data-out") || "0", 10);

    const ctx = statusCanvas.getContext("2d");
    new Chart(ctx, {
      type: "doughnut",
      data: {
        labels: ["Available", "Busy", "Out of Service"],
        datasets: [
          {
            data: [avail, busy, out],
            backgroundColor: ["#10b981", "#f59e0b", "#64748b"],
            borderWidth: 2,
            borderColor: "#0f172a",
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: "70%",
        plugins: {
          legend: {
            position: "bottom",
            labels: {
              color: "#94a3b8",
              font: { size: 11 },
              padding: 14,
              boxWidth: 12,
            },
          },
          tooltip: {
            backgroundColor: "#0f172a",
            borderColor: "rgba(255, 255, 255, 0.1)",
            borderWidth: 1,
            titleColor: "#f8fafc",
          },
        },
      },
    });
  }
}

function initReportCharts() {
  // Category Breakdown Chart
  const catCanvas = document.getElementById("categoryChart");
  if (catCanvas) {
    const labels = JSON.parse(catCanvas.getAttribute("data-labels") || "[]");
    const counts = JSON.parse(catCanvas.getAttribute("data-counts") || "[]");

    const ctx = catCanvas.getContext("2d");
    new Chart(ctx, {
      type: "bar",
      data: {
        labels: labels,
        datasets: [
          {
            label: "Requests",
            data: counts,
            backgroundColor: ["#ef4444", "#3b82f6", "#f59e0b", "#8b5cf6"],
            borderRadius: 6,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: {
            grid: { display: false },
            ticks: { color: "#64748b", font: { size: 11 } },
          },
          y: {
            beginAtZero: true,
            grid: { color: "rgba(255, 255, 255, 0.05)" },
            ticks: { color: "#64748b", precision: 0 },
          },
        },
      },
    });
  }
}
