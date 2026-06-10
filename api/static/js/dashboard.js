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

// Paleta kolorow dla wykresow kategorycznych
const PALETTE = [
  "#3b82f6", "#06b6d4", "#8b5cf6", "#10b981",
  "#f59e0b", "#ef4444", "#ec4899", "#6366f1",
  "#14b8a6", "#f97316", "#84cc16", "#a855f7",
];

function paletteColors(n) {
  return Array.from({ length: n }, (_, i) => PALETTE[i % PALETTE.length]);
}

function fmtUSD(val) {
  if (val == null || isNaN(val)) return "";
  if (val >= 1000) return "$" + Math.round(val / 1000) + "k";
  return "$" + Math.round(val);
}

async function loadDashboard() {
  const sourceEl = document.getElementById("data-source");
  destroyCharts();

  // Stan ladowania
  document.querySelectorAll(".chart-loading").forEach(el => el.style.display = "flex");

  let data = {};
  try {
    const r = await fetch("/api/dashboard");
    data = await r.json();
  } catch (e) {
    if (sourceEl) sourceEl.textContent = "Blad pobierania danych: " + e.message;
    document.querySelectorAll(".chart-loading").forEach(el => el.style.display = "none");
    return;
  }

  document.querySelectorAll(".chart-loading").forEach(el => el.style.display = "none");

  if (sourceEl) {
    let msg = "Zrodlo: " + (data.source || "brak");
    if (data.sql_error) msg += " \u00b7 SQL: " + data.sql_error;
    if (data.error) msg += " \u00b7 " + data.error;
    if (data.hint) msg += " \u00b7 " + data.hint;
    sourceEl.textContent = msg;
  }

  // KPI cards
  const overall = data.overall || {};
  const factRows = (data.table_counts && data.table_counts.fact_rows) || overall.total_records;
  const fmtBig = (n) => n != null ? "$" + Math.round(n).toLocaleString("pl-PL") : "\u2014";
  const fmtN   = (n) => n != null ? Number(n).toLocaleString("pl-PL") : "\u2014";
  const setKpi = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
  setKpi("kpi-records", fmtN(overall.total_records ?? factRows));
  setKpi("kpi-avg",     fmtBig(overall.avg_salary));
  setKpi("kpi-median",  fmtBig(overall.median_salary));
  setKpi("kpi-source",  (data.source || "\u2014")
    .replace("silver_parquet+azure_sql", "silver + SQL")
    .replace("silver_parquet", "silver")
    .replace("azure_sql", "SQL")
    .replace("gold_parquet", "gold")
    .replace("raw_csv", "raw CSV"));
  const hintEl = document.getElementById("kpi-source-hint");
  if (hintEl) hintEl.textContent = data.sql_error ? "SQL: " + data.sql_error : (data.hint || "");

  // Wspolne ustawienia osi
  const axisStyle = {
    ticks: { color: "#8b9cb3", font: { size: 11 } },
    grid: { color: "rgba(42,53,72,0.8)" },
    border: { color: "transparent" },
  };

  const tooltip = {
    backgroundColor: "#0f1419",
    borderColor: "#2a3548",
    borderWidth: 1,
    titleColor: "#e7ecf3",
    bodyColor: "#8b9cb3",
    padding: 10,
    callbacks: {
      label: (ctx) => {
        const v = ctx.parsed.x ?? ctx.parsed.y;
        return " " + (v >= 1000 ? "$" + Math.round(v).toLocaleString("pl-PL") : v);
      },
    },
  };

  const tooltipCount = {
    ...tooltip,
    callbacks: {
      label: (ctx) => " " + (ctx.parsed.x ?? ctx.parsed.y).toLocaleString("pl-PL") + " ofert",
    },
  };

  function barChart(id, labels, values, { horizontal = false, multicolor = false, formatY = true, tooltipCfg } = {}) {
    const canvas = document.getElementById(id);
    if (!canvas) return;
    if (!labels.length) {
      canvas.parentElement.querySelector(".chart-empty")?.style && (canvas.parentElement.querySelector(".chart-empty").style.display = "block");
      return;
    }
    const colors = multicolor ? paletteColors(labels.length) : Array(labels.length).fill("#3b82f6");
    const hoverColors = multicolor ? paletteColors(labels.length).map(c => c + "cc") : Array(labels.length).fill("#60a5fa");

    const xAxis = { ...axisStyle };
    const yAxis = { ...axisStyle };
    if (formatY) {
      if (horizontal) {
        xAxis.ticks = { ...xAxis.ticks, callback: (v) => fmtUSD(v) };
      } else {
        yAxis.ticks = { ...yAxis.ticks, callback: (v) => fmtUSD(v) };
      }
    }

    chartInstances[id] = new Chart(canvas, {
      type: "bar",
      data: {
        labels,
        datasets: [{
          data: values,
          backgroundColor: colors,
          hoverBackgroundColor: hoverColors,
          borderRadius: 4,
          borderSkipped: false,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: true,
        indexAxis: horizontal ? "y" : "x",
        plugins: {
          legend: { display: false },
          tooltip: tooltipCfg || tooltip,
        },
        scales: horizontal
          ? { x: xAxis, y: { ...axisStyle, ticks: { ...axisStyle.ticks, maxRotation: 0 } } }
          : { x: { ...axisStyle, ticks: { ...axisStyle.ticks, maxRotation: 30 } }, y: yAxis },
      },
    });
  }

  // Lokalizacja
  const loc = data.by_location || [];
  barChart("chartLocation",
    loc.map(r => r.location),
    loc.map(r => Math.round(Number(r.avg_salary) || 0)),
    { horizontal: true, multicolor: true }
  );

  // Rozklad pensji — gradient
  const dist = data.salary_distribution || [];
  if (dist.length) {
    const canvas = document.getElementById("chartSalaryDist");
    if (canvas) {
      const ctx = canvas.getContext("2d");
      const grad = ctx.createLinearGradient(0, 0, canvas.width || 400, 0);
      grad.addColorStop(0, "#3b82f6");
      grad.addColorStop(1, "#8b5cf6");
      chartInstances["chartSalaryDist"] = new Chart(canvas, {
        type: "bar",
        data: {
          labels: dist.map(r => r.bin),
          datasets: [{ data: dist.map(r => r.count), backgroundColor: grad, borderRadius: 3, borderSkipped: false }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: true,
          plugins: { legend: { display: false }, tooltip: tooltipCount },
          scales: {
            x: { ...axisStyle, ticks: { ...axisStyle.ticks, maxRotation: 45, font: { size: 9 } } },
            y: { ...axisStyle, ticks: { ...axisStyle.ticks, callback: (v) => v >= 1000 ? (v/1000)+"k" : v } },
          },
        },
      });
    }
  }

  // Wyksztalcenie
  const edu = data.by_education || [];
  barChart("chartEducation",
    edu.map(r => r.education_level),
    edu.map(r => Math.round(Number(r.avg_salary) || 0)),
    { multicolor: true }
  );

  // Doswiadczenie
  const exp = data.by_experience || [];
  barChart("chartExperience",
    exp.map(r => r.exp_bucket || r.label),
    exp.map(r => Math.round(Number(r.avg_salary) || 0)),
    {}
  );

  // Top stanowiska
  const jobs = data.by_job_title || [];
  barChart("chartJobTitle",
    jobs.map(r => r.job_title),
    jobs.map(r => Math.round(Number(r.avg_salary) || 0)),
    { horizontal: true, multicolor: true }
  );

  // Branza
  const ind = data.by_industry || [];
  barChart("chartIndustry",
    ind.map(r => r.industry),
    ind.map(r => Math.round(Number(r.avg_salary) || 0)),
    { horizontal: true, multicolor: true }
  );

  // Wielkosc firmy
  const comp = data.by_company_size || [];
  barChart("chartCompany",
    comp.map(r => r.company_size),
    comp.map(r => Math.round(Number(r.avg_salary) || 0)),
    { multicolor: true }
  );

  // Praca zdalna
  const rem = data.by_remote || [];
  barChart("chartRemote",
    rem.map(r => r.remote_work),
    rem.map(r => Math.round(Number(r.avg_salary) || 0)),
    { multicolor: true }
  );
}

document.addEventListener("DOMContentLoaded", loadDashboard);
