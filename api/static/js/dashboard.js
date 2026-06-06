/** Dashboard — dane z /api/dashboard (Chart.js). */

const chartInstances = {};

function destroyCharts() {
  Object.keys(chartInstances).forEach((id) => {
    if (chartInstances[id]) {
      chartInstances[id].destroy();
      delete chartInstances[id];
    }
  });
}

async function loadDashboard() {
  const sourceEl = document.getElementById("data-source");
  destroyCharts();

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
      msg += " | wiersze: " + Number(data.table_counts.fact_rows).toLocaleString("pl-PL");
    }
    sourceEl.textContent = msg;
  }

  const chartDefaults = {
    responsive: true,
    maintainAspectRatio: true,
    plugins: { legend: { display: false } },
    scales: {
      x: { ticks: { color: "#8b9cb3", maxRotation: 45 }, grid: { color: "#2a3548" } },
      y: { ticks: { color: "#8b9cb3" }, grid: { color: "#2a3548" } },
    },
  };

  function barChart(id, labels, values, label, horizontal) {
    const canvas = document.getElementById(id);
    if (!canvas) return;
    const parent = canvas.parentElement;
    if (!labels.length) {
      const ctx = canvas.getContext("2d");
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = "#8b9cb3";
      ctx.font = "14px sans-serif";
      ctx.fillText("Brak danych", 10, 40);
      return;
    }
    chartInstances[id] = new Chart(canvas, {
      type: "bar",
      data: {
        labels,
        datasets: [{ label, data: values, backgroundColor: "rgba(59, 130, 246, 0.75)" }],
      },
      options: {
        ...chartDefaults,
        indexAxis: horizontal ? "y" : "x",
      },
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

  const ind = data.by_industry || [];
  barChart(
    "chartIndustry",
    ind.map((r) => r.industry),
    ind.map((r) => Math.round(Number(r.avg_salary) || 0)),
    "Srednia pensja (USD)",
    true
  );

  const comp = data.by_company_size || [];
  barChart(
    "chartCompany",
    comp.map((r) => r.company_size),
    comp.map((r) => Math.round(Number(r.avg_salary) || 0)),
    "Srednia pensja (USD)"
  );

  const rem = data.by_remote || [];
  barChart(
    "chartRemote",
    rem.map((r) => r.remote_work),
    rem.map((r) => Math.round(Number(r.avg_salary) || 0)),
    "Srednia pensja (USD)"
  );

  const exp = data.by_experience || [];
  barChart(
    "chartExperience",
    exp.map((r) => r.exp_bucket || r.label),
    exp.map((r) => Math.round(Number(r.avg_salary) || 0)),
    "Srednia pensja (USD)"
  );

  const jobs = data.by_job_title || [];
  barChart(
    "chartJobTitle",
    jobs.map((r) => r.job_title),
    jobs.map((r) => Math.round(Number(r.avg_salary) || 0)),
    "Srednia pensja (USD)",
    true
  );

  const dist = data.salary_distribution || [];
  barChart(
    "chartSalaryDist",
    dist.map((r) => r.bin),
    dist.map((r) => r.count),
    "Liczba ofert"
  );
}

document.addEventListener("DOMContentLoaded", loadDashboard);
