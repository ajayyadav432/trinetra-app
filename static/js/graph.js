/* TRINETRA relationship graph — small hand-rolled force layout on canvas */
(function () {
  var canvas = document.getElementById("graph");
  if (!canvas) return;
  var ctx = canvas.getContext("2d");
  var info = document.getElementById("node-info");
  var meta = document.getElementById("graph-meta");

  var nodes = [], edges = [], byId = {};
  var W = canvas.width, H = canvas.height;
  var selected = null, drag = null, hover = null;

  var STYLE = {
    asset: { color: "#2ea043", fill: "#0f1a13", r: 11, shape: "circle" },
    identifier: { color: "#a29d91", fill: "#1f1d18", r: 8, shape: "diamond" },
    actor: { color: "#d8452c", fill: "#2b140f", r: 12, shape: "square" }
  };

  function load() {
    fetch("/graph/api")
      .then(function (r) { return r.json(); })
      .then(function (data) {
        nodes = data.nodes || [];
        edges = data.edges || [];
        byId = {};
        nodes.forEach(function (n, i) {
          byId[n.id] = n;
          var a = (i / Math.max(1, nodes.length)) * Math.PI * 2;
          n.x = W / 2 + Math.cos(a) * (140 + (i % 5) * 22);
          n.y = H / 2 + Math.sin(a) * (110 + (i % 4) * 20);
          n.vx = 0; n.vy = 0;
          n.degree = 0;
        });
        edges.forEach(function (e) {
          if (byId[e.source]) byId[e.source].degree++;
          if (byId[e.target]) byId[e.target].degree++;
        });
        for (var k = 0; k < 400; k++) tick();
        if (meta) {
          meta.textContent = (data.stats || {}).edges + " edges · " + nodes.length + " nodes";
        }
        var stats = data.stats || {};
        if (info) {
          /* keep selection panel intact */
        }
        var statsEl = document.getElementById("graph-stats");
        if (statsEl && stats.assets !== undefined) {
          statsEl.innerHTML +=
            '<div class="flex justify-between text-outline"><span>SERVICE ASSETS:</span>' +
            '<span class="text-secondary font-bold">' + stats.assets + "</span></div>";
        }
        draw();
      });
  }

  function tick() {
    var i, j, a, b, dx, dy, dist, f;
    for (i = 0; i < nodes.length; i++) {
      a = nodes[i];
      for (j = i + 1; j < nodes.length; j++) {
        b = nodes[j];
        dx = a.x - b.x; dy = a.y - b.y;
        dist = Math.sqrt(dx * dx + dy * dy) || 0.01;
        f = 1400 / (dist * dist);
        a.vx += (dx / dist) * f; a.vy += (dy / dist) * f;
        b.vx -= (dx / dist) * f; b.vy -= (dy / dist) * f;
      }
    }
    edges.forEach(function (e) {
      a = byId[e.source]; b = byId[e.target];
      if (!a || !b) return;
      dx = b.x - a.x; dy = b.y - a.y;
      dist = Math.sqrt(dx * dx + dy * dy) || 0.01;
      var target = e.derived ? 110 : 74;
      f = (dist - target) * 0.012;
      a.vx += (dx / dist) * f; a.vy += (dy / dist) * f;
      b.vx -= (dx / dist) * f; b.vy -= (dy / dist) * f;
    });
    nodes.forEach(function (n) {
      n.vx += (W / 2 - n.x) * 0.004;
      n.vy += (H / 2 - n.y) * 0.004;
      n.vx *= 0.86; n.vy *= 0.86;
      if (drag === n) { n.vx = 0; n.vy = 0; return; }
      n.x = Math.max(24, Math.min(W - 24, n.x + n.vx));
      n.y = Math.max(24, Math.min(H - 24, n.y + n.vy));
    });
  }

  function halo(text, x, y, color) {
    ctx.save();
    ctx.font = "10px ui-monospace, Menlo, monospace";
    ctx.textAlign = "center";
    ctx.lineWidth = 3;
    ctx.lineJoin = "round";
    ctx.strokeStyle = "#0f0e0c";
    ctx.strokeText(text, x, y);
    ctx.fillStyle = color;
    ctx.fillText(text, x, y);
    ctx.restore();
  }

  function draw() {
    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = "#0f0e0c";
    ctx.fillRect(0, 0, W, H);

    ctx.strokeStyle = "#1d1b19";
    ctx.lineWidth = 1;
    for (var gx = 0; gx < W; gx += 60) {
      ctx.beginPath(); ctx.moveTo(gx, 0); ctx.lineTo(gx, H); ctx.stroke();
    }
    for (var gy = 0; gy < H; gy += 60) {
      ctx.beginPath(); ctx.moveTo(0, gy); ctx.lineTo(W, gy); ctx.stroke();
    }

    edges.forEach(function (e) {
      var a = byId[e.source], b = byId[e.target];
      if (!a || !b) return;
      ctx.save();
      ctx.strokeStyle = e.derived ? "#d8452c" : "#34322c";
      ctx.lineWidth = e.derived ? 2 : 1;
      if (e.derived) ctx.setLineDash([6, 4]);
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.stroke();
      ctx.setLineDash([]);
      if (e.derived && e.label) {
        halo(e.label, (a.x + b.x) / 2, (a.y + b.y) / 2 - 5, "#d8452c");
      }
      ctx.restore();
    });

    nodes.forEach(function (n) {
      var st = STYLE[n.type] || STYLE.asset;
      ctx.save();
      ctx.lineWidth = (n === selected || n === hover) ? 3 : 1.4;
      ctx.strokeStyle = st.color;
      ctx.fillStyle = st.fill;
      var r = st.r + (n === selected ? 4 : 0) + Math.min(4, (n.degree || 0) * 0.5);
      ctx.beginPath();
      if (st.shape === "circle") {
        ctx.arc(n.x, n.y, r, 0, Math.PI * 2);
      } else if (st.shape === "square") {
        ctx.rect(n.x - r, n.y - r, r * 2, r * 2);
      } else {
        ctx.moveTo(n.x, n.y - r);
        ctx.lineTo(n.x + r, n.y);
        ctx.lineTo(n.x, n.y + r);
        ctx.lineTo(n.x - r, n.y);
        ctx.closePath();
      }
      ctx.fill();
      ctx.stroke();

      var label = n.label.length > 26 ? n.label.slice(0, 25) + "…" : n.label;
      halo(label, n.x, n.y + r + 12, "#e6e2de");
      ctx.restore();
    });
  }

  function pos(ev) {
    var rect = canvas.getBoundingClientRect();
    return {
      x: (ev.clientX - rect.left) * (W / rect.width),
      y: (ev.clientY - rect.top) * (H / rect.height)
    };
  }

  function pick(p) {
    for (var i = nodes.length - 1; i >= 0; i--) {
      var n = nodes[i], st = STYLE[n.type] || STYLE.asset;
      var r = st.r + 6;
      if (Math.abs(n.x - p.x) < r && Math.abs(n.y - p.y) < r) return n;
    }
    return null;
  }

  canvas.addEventListener("mousedown", function (e) {
    drag = pick(pos(e));
    if (drag) selected = drag;
    loop();
    renderInfo();
  });
  window.addEventListener("mouseup", function () { drag = null; });
  canvas.addEventListener("mousemove", function (e) {
    var p = pos(e);
    if (drag) { drag.x = p.x; drag.y = p.y; }
    else {
      hover = pick(p);
      canvas.style.cursor = hover ? "pointer" : "default";
    }
    draw();
  });
  canvas.addEventListener("click", function () { renderInfo(); });

  function renderInfo() {
    if (!info) return;
    if (!selected) {
      info.innerHTML = '<p class="pill-note" style="margin:0">Nothing selected.</p>';
      return;
    }
    var n = selected;
    var rows = '<div class="kv">';
    rows += '<div class="rec-head">' + (n.type === "actor" ? "THREAT PERSONA" : n.type === "identifier" ? "REUSED IDENTIFIER" : "SERVICE ASSET") + " // NODE RECORD</div>";
    rows += "<div>type</div><div>" + n.type + "</div>";
    rows += "<div>label</div><div class='mono wrap'>" + (n.label || "") + "</div>";
    if (n.url) rows += "<div>address</div><div class='mono wrap'>" + n.url + "</div>";
    if (n.kind) rows += "<div>identifier kind</div><div>" + n.kind + "</div>";
    if (n.value) rows += "<div>value</div><div class='mono wrap'>" + (n.value || "").slice(0, 90) + "</div>";
    if (n.category) rows += "<div>category</div><div>" + n.category + "</div>";
    if (n.confidence !== undefined) rows += "<div>confidence</div><div>" + n.confidence + "%</div>";
    if (n.aliases) rows += "<div>aliases</div><div>" + n.aliases + "</div>";
    if (n.last_scan) rows += "<div>last scan</div><div>" + n.last_scan + "</div>";
    if (n.source) rows += "<div>source</div><div>" + n.source + "</div>";
    rows += "<div>edges</div><div>" + (n.degree || 0) + "</div>";
    rows += "</div>";
    info.innerHTML = rows;
  }

  var running = false;
  function loop() {
    if (running) return;
    running = true;
    (function step() {
      if (!drag) tick();
      draw();
      if (drag) requestAnimationFrame(step);
      else running = false;
    })();
  }

  var reload = document.getElementById("reload");
  if (reload) reload.addEventListener("click", function (e) {
    e.preventDefault();
    for (var i = 0; i < 300; i++) tick();
    draw();
  });

  load();
  window.addEventListener("resize", draw);
})();
