/** Monitoring — symulacja driftu z wyborem scenariusza. */

document.addEventListener("DOMContentLoaded", () => {
  const btn = document.getElementById("btn-simulate-drift");
  if (!btn) return;

  btn.addEventListener("click", async () => {
    const scenario = document.getElementById("drift-scenario")?.value || "location_shift";
    const countRaw = document.getElementById("drift-count")?.value;
    const count = countRaw ? parseInt(countRaw, 10) : 150;

    btn.disabled = true;
    document.querySelectorAll("[data-job]").forEach((b) => (b.disabled = true));
    try {
      await startJob(
        "simulate_drift",
        { scenario, count },
        { skipReload: true, refresh: "" }
      );
      const st = await apiJson("/api/monitoring/status");
      if (st.metrics?.drift_alert) {
        alert("Wykryto drift — odswiez strone (F5), aby zobaczyc raport.");
      }
      location.reload();
    } catch (e) {
      alert("Blad: " + e.message);
    } finally {
      btn.disabled = false;
      document.querySelectorAll("[data-job]").forEach((b) => (b.disabled = false));
    }
  });
});
