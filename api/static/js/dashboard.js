/** Dashboard — dane z /api/dashboard (Chart.js). */

async function loadDashboard() {
  const sourceEl = document.getElementById("data-source");
  let data = {};
  try {
    const r = await fetch("/api/dashboard");
    data = await r.json();
  } catch (e) {
    if (sourceEl) sourceEl.textContent = "Blad pobierania danych: " + e.message;
    return;
  }

  if (sourceEl) {
    let msg = "Zrodlo: " + (data.source || "brak");
    if (data.sql_error) msg += " | SQL: " + data.sql_error;
    if (data.error) msg += " | " + data.error;
    if (data.hint) msg += " | " + data.hint;
    if (data.table_counts && data.table_counts.fact_rows) {
      msg += " | wiersze: " + data.table_counts.fact_rows;
    }
    sourceEl.textContent = msg;
  }

  const chartDefaults = {
    responsive: true,
    plugins: { legend: { labels: { color: "#e7ecf3" } } },
    scales: {
      x: { ticks: { color: "#8b9cb3" }, grid: { color: "#2a3548" } },
      y: { ticks: { color: "#8b9cb3" }, grid: { color: "#2a3548" } },
    },
  };

  function barChart(id, labels, values, label) {
    const canvas = document.getElementById(id);
    if (!canvas) return;
    if (!labels.length) {
      const ctx = canvas.getContext("2d");
      ctx.fillStyle = "#8b9cb3";
      ctx.font = "14px sans-serif";
      ctx.fillText("Brak danych — uruchom ETL / Przygotowanie", 10, 40);
      return;
    }
    new Chart(canvas, {
      type: "bar",
      data: {
        labels,
        datasets: [{ label, data: values, backgroundColor: "rgba(59, 130, 246, 0.7)" }],
      },
      options: chartDefaults,
    });
  }

  const loc = data.by_location || [];
  barChart(
    "chartLocation",
    loc.map((r) => r.location),
    loc.map((r) => Math.round(Number(r.avg_salary) || 0)),
    "Srednia pensja (USD)"
  );

  const edu = data.by_education || [];
  barChart(
    "chartEducation",
    edu.map((r) => r.education_level),
    edu.map((r) => Math.round(Number(r.avg_salary) || 0)),
    "Srednia pensja (USD)"
  );

  const rem = data.by_remote || [];
  barChart(
    "chartRemote",
    rem.map((r) => r.remote_work),
    rem.map((r) => Math.round(Number(r.avg_salary) || 0)),
    "Srednia pensja (USD)"
  );
}

document.addEventListener("DOMContentLoaded", loadDashboard);
