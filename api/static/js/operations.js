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

function logPlaceholder() {
  const box = el("job-log");
  if (!box) return "Oczekiwanie na start zadania...";
  return box.getAttribute("data-placeholder") || box.textContent.trim() || "Oczekiwanie...";
}

function setJobLog(text, isError) {
  const box = el("job-log");
  if (!box) return;
  box.textContent = text;
  box.className = "job-log" + (isError ? " job-log-error" : "");
  box.scrollTop = box.scrollHeight;
}

function appendJobLog(line) {
  const box = el("job-log");
  if (!box) return;
  const prev = box.textContent.trim();
  const placeholder = logPlaceholder();
  if (!prev || prev === placeholder) {
    box.textContent = line;
  } else {
    box.textContent = prev + "\n" + line;
  }
  box.scrollTop = box.scrollHeight;
}

function setProgress(pct, message) {
  const bar = el("job-progress-bar");
  if (bar) bar.style.width = Math.max(0, Math.min(100, pct)) + "%";
  const statusEl = el("job-status");
  if (statusEl && message) statusEl.textContent = message;
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function pollJob(jobId, jobType) {
  const fastTrain = jobType === "train_fast";
  let polls = 0;

  for (let i = 0; i < 7200; i++) {
    const job = await apiJson(`/api/jobs/${jobId}`);
    polls += 1;

    let pct = job.progress || 0;
    let msg = job.progress_message || `Status: ${job.status}`;

    if (job.status === "running" && fastTrain && pct < 15 && polls < 3) {
      pct = Math.min(12, 5 + polls * 3);
      msg = "Trening szybki — uruchamianie...";
    }

    setProgress(pct, msg);

    if (job.log_lines && job.log_lines.length) {
      setJobLog(job.log_lines.join("\n"), false);
    }

    if (job.status === "running" || job.status === "queued") {
      const delay = polls <= 2 ? 600 : fastTrain ? 900 : 1500;
      await sleep(delay);
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

async function refreshEtlSummary() {
  const section = el("etl-last-run-section");
  const pre = el("etl-last-summary");
  if (!pre) return;
  try {
    const data = await apiJson("/api/summaries/etl");
    if (data.present && data.text) {
      pre.textContent = data.text;
      if (section) section.style.display = "";
    }
  } catch (_) {}
}

async function refreshPathsStatus() {
  try {
    const st = await apiJson("/api/system/status");
    const p = st.paths || {};
    document.querySelectorAll("[data-path-key]").forEach((node) => {
      const key = node.getAttribute("data-path-key");
      const ok = p[key];
      const okEl = node.querySelector(".path-ok");
      const warnEl = node.querySelector(".path-warn");
      if (okEl) okEl.style.display = ok ? "" : "none";
      if (warnEl) warnEl.style.display = ok ? "none" : "";
      const azureNote = node.querySelector(".path-azure");
      if (azureNote) azureNote.style.display = key === "raw_csv" && p.raw_csv_azure ? "" : "none";
      const localNote = node.querySelector(".path-local");
      if (localNote) localNote.style.display = key === "raw_csv" && p.raw_csv_local ? "" : "none";
    });
  } catch (_) {}
}

async function startJob(jobType, extraBody = {}, options = {}) {
  const busy = await apiJson("/api/system/status");
  if (busy.job_busy) {
    throw new Error("Inne zadanie jest juz uruchomione.");
  }

  const placeholder = logPlaceholder();
  setProgress(0, "Uruchamianie zadania...");
  setJobLog(placeholder, false);
  await sleep(400);

  appendJobLog(`--- ${new Date().toLocaleTimeString("pl-PL")} — zlecenie: ${jobType} ---`);

  const job = await apiJson("/api/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ job_type: jobType, ...extraBody }),
  });

  appendJobLog(`Zadanie ${job.id} w kolejce (typ: ${job.job_type})`);

  const done = await pollJob(job.id, jobType);

  if (jobType.startsWith("train") || (jobType.startsWith("dvc") && jobType !== "dvc_push")) {
    try {
      await apiJson("/api/model/reload", { method: "POST" });
    } catch (_) {}
  }

  if (options.refresh === "etl") {
    await refreshEtlSummary();
    await refreshPathsStatus();
  }

  if (!options.skipReload) {
    location.reload();
  }

  return done;
}

function bindJobButtons() {
  document.querySelectorAll("[data-job]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const jobType = btn.getAttribute("data-job");
      const skipReload = btn.hasAttribute("data-skip-reload");
      const refresh = btn.getAttribute("data-refresh") || "";

      btn.disabled = true;
      document.querySelectorAll("[data-job]").forEach((b) => (b.disabled = true));
      try {
        await startJob(jobType, {}, { skipReload, refresh });
      } catch (e) {
        alert("Blad: " + e.message);
      } finally {
        document.querySelectorAll("[data-job]").forEach((b) => (b.disabled = false));
      }
    });
  });
}

document.addEventListener("DOMContentLoaded", bindJobButtons);
