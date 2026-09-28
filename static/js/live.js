/* TRINETRA live scan transcript — Server-Sent Events driven checklist + log */
(function () {
  var cfg = window.TRINETRA || {};
  var logEl = document.getElementById("log");
  var meter = document.getElementById("meter");
  var checklist = document.getElementById("checklist");
  var statusEl = document.getElementById("run-status");
  var progressLabel = document.getElementById("progress-label");
  var findingsEl = document.getElementById("findings-count");
  var logCount = document.getElementById("log-count");
  var donePanel = document.getElementById("done-panel");
  if (!logEl) return;

  var lastSeq = 0;
  var lines = 0;

  function ts() {
    var d = new Date();
    return d.toISOString().substr(11, 8);
  }

  function append(entry) {
    var div = document.createElement("div");
    var level = entry.level || "info";
    var msg = entry.message || "";
    div.innerHTML =
      '<span class="l-ts">[' + (entry.ts || ts()) + ']</span> ' +
      '<span class="l-chip l-' + level + '">' + level.toUpperCase() + '</span> ' +
      '<span class="l-' + level + '">' + escapeHtml(msg) + "</span>";
    logEl.appendChild(div);
    lines += 1;
    logCount.textContent = lines + " lines";
    var scroller = document.getElementById("terminal-stream") || logEl;
    scroller.scrollTop = scroller.scrollHeight;
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function setCheck(id, state, text) {
    if (!id || !checklist) return;
    var row = checklist.querySelector('[data-check="' + id + '"]');
    if (!row) return;
    row.classList.remove("running", "done", "failed");
    if (state) row.classList.add(state);
    var st = row.querySelector(".st");
    if (st) st.textContent = text || state;
  }

  function updateMeter(done, total) {
    if (!meter) return;
    var segs = meter.querySelectorAll("i");
    var step = total ? Math.round((done / total) * segs.length) : 0;
    var complete = total > 0 && done >= total;
    for (var i = 0; i < segs.length; i++) {
      segs[i].classList.toggle("on", complete || i < step - 1);
      segs[i].classList.toggle("cur", !complete && i === step - 1);
    }
  }

  function renderFindings(items) {
    var box = document.getElementById("done-findings");
    if (!box) return;
    if (!items.length) {
      box.innerHTML = '<p class="pill-note" style="margin:0">No findings recorded for this target.</p>';
      return;
    }
    var html = "";
    for (var i = 0; i < items.length; i++) {
      var f = items[i];
      var detail = "";
      try {
        detail = JSON.stringify(f.detail || {}, null, 2);
      } catch (e) {
        detail = "{}";
      }
      html +=
        '<details class="finding">' +
        "<summary>" +
        '<span class="tag ' + escapeHtml(f.severity || "info") + '">' + escapeHtml(f.severity || "info") + "</span>" +
        '<span><span class="f-title">' + escapeHtml(f.title || "") + "</span></span>" +
        '<span class="f-meta">' + escapeHtml(f.check_id || "") + " · #" + (f.id || "") + "</span>" +
        "</summary><pre>" + escapeHtml(detail) + "</pre></details>";
    }
    box.innerHTML = html;
  }

  function connect() {
    var url = "/scans/" + cfg.scanId + "/events?after=" + lastSeq;
    var es = new EventSource(url);

    es.onmessage = function (ev) {
      var d;
      try {
        d = JSON.parse(ev.data);
      } catch (e) {
        return;
      }

      if (typeof d.seq === "number") {
        lastSeq = d.seq;
        append(d);
        if (d.check_id) {
          if (d.level === "step") setCheck(d.check_id, "running", "running");
          else if (d.level === "err" && /\[(\d+)\/\d+\]/.test(d.message)) setCheck(d.check_id, "failed", "failed");
          else if (d.level === "ok" && /complete in/.test(d.message)) {
            var ms = (d.message.match(/in (\d+) ms/) || [])[1];
            setCheck(d.check_id, "done", (ms || "") + " ms");
          } else if (d.level === "ok" || d.level === "warn" || d.level === "info") {
            /* keep running state during sub-steps */
          }
        }
      }

      if (typeof d.progress === "number") {
        if (statusEl) {
          statusEl.textContent = d.status;
          statusEl.style.color = d.status === "failed" ? "var(--accent)" : "var(--ok)";
        }
        if (progressLabel) progressLabel.textContent = d.checks_done + " / " + d.checks_total;
        if (findingsEl) findingsEl.textContent = d.findings;
        updateMeter(d.checks_done, d.checks_total);
      }

      if (d.done) {
        es.close();
        renderFindings(d.findings || []);
        if (donePanel) donePanel.style.display = "";
        append({ level: "ok", message: "— transcript closed · run " + d.status + " —" });
        setTimeout(function () {
          if (statusEl) statusEl.textContent = d.status;
        }, 100);
      }
    };

    es.onerror = function () {
      es.close();
      append({ level: "warn", message: "stream interrupted — retrying in 2s" });
      setTimeout(connect, 2000);
    };
  }

  append({ level: "info", message: "attached to run #" + cfg.scanId + " · waiting for first module…" });
  connect();
})();
