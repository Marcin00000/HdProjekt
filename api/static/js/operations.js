/** Panel operacji — zadania, pasek postepu, logi na zywo. */

async function apiJson(url, options = {}) {
  const r = await fetch(url, {
    headers: { Accept: "application/json", ...(options.headers || {}) },
    ...options,
  });
  const body = await r.json().catch(() => ({}));
  if (!r.ok) {
    const msg = body.detail || body.error || r.statusText;
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return body;
}

function el(id) {
  return document.getElementById(id);
}

function setJobLog(text, isError) {
  const box = el("job-log");
  if (!box) return;
  box.textContent = text;
  box.className = "job-log" + (isError ? " job-log-error" : "");
  box.scrollTop = box.scrollHeight;
}

function setProgress(pct, message) {
  const bar = el("job-progress-bar");
  if (bar) bar.style.width = Math.max(0, Math.min(100, pct)) + "%";
  const statusEl = el("job-status");
  if (statusEl && message) statusEl.textContent = message;
}

async function pollJob(jobId) {
  for (let i = 0; i < 7200; i++) {
    const job = await apiJson(`/api/jobs/${jobId}`);
    setProgress(job.progress || 0, job.progress_message || `Status: ${job.status}`);
    if (job.log_lines && job.log_lines.length) {
      setJobLog(job.log_lines.join("\n"), false);
    }
    if (job.status === "running" || job.status === "queued") {
      await new Promise((r) => setTimeout(r, 1500));
      continue;
    }
    if (job.status === "success") {
      setProgress(100, "Zakonczono pomyslnie");
      if (job.log_lines?.length) setJobLog(job.log_lines.join("\n"), false);
      else if (job.result) setJobLog(JSON.stringify(job.result, null, 2), false);
      return job;
    }
    const errText = job.error || "Zadanie nie powiodlo sie";
    if (job.log_lines?.length) setJobLog(job.log_lines.join("\n") + "\n\n" + errText, true);
    else setJobLog(errText, true);
    throw new Error(errText.split("\n")[0]);
  }
  throw new Error("Przekroczono czas oczekiwania na zadanie");
}

async function startJob(jobType, extraBody = {}) {
  const busy = await apiJson("/api/system/status");
  if (busy.job_busy) {
    throw new Error("Inne zadanie jest juz uruchomione.");
  }
  setProgress(0, "Uruchamianie...");
  setJobLog("", false);
  const job = await apiJson("/api/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ job_type: jobType, ...extraBody }),
  });
  setJobLog(`Zadanie ${job.id} (${job.job_type})...\n`, false);
  const done = await pollJob(job.id);
  if (jobType.startsWith("train") || jobType.startsWith("dvc")) {
    try {
      await apiJson("/api/model/reload", { method: "POST" });
    } catch (_) {}
  }
  return done;
}

function bindJobButtons() {
  document.querySelectorAll("[data-job]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const jobType = btn.getAttribute("data-job");
      btn.disabled = true;
      document.querySelectorAll("[data-job]").forEach((b) => (b.disabled = true));
      try {
        await startJob(jobType);
        if (!window.skipJobReload) location.reload();
      } catch (e) {
        alert("Blad: " + e.message);
      } finally {
        document.querySelectorAll("[data-job]").forEach((b) => (b.disabled = false));
      }
    });
  });
}

document.addEventListener("DOMContentLoaded", bindJobButtons);
