"""Pillar 1 — hidden-service misconfiguration & infrastructure checks.

Every check receives a Context, may emit progress sub-steps (so the UI can show
exactly what is happening), and returns a list of finding dicts.
"""

import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Comment

from . import torclient

SENSITIVE_PATHS = [
    "/.env", "/.git/config", "/server-status", "/server-info", "/phpinfo.php",
    "/info.php", "/.DS_Store", "/config.php.bak", "/.htpasswd", "/backup.sql",
    "/wp-config.php.bak", "/adminer.php", "/.well-known/security.txt", "/security.txt",
    "/trace.axd", "/elmah.axd", "/debug", "/console", "/actuator/env",
]

DIR_PATHS = ["/", "/images/", "/static/", "/assets/", "/uploads/", "/backup/", "/files/"]

SEC_HEADERS = [
    ("Strict-Transport-Security", "HSTS", "high"),
    ("Content-Security-Policy", "CSP", "high"),
    ("X-Frame-Options", "clickjacking guard", "medium"),
    ("X-Content-Type-Options", "MIME sniffing guard", "medium"),
    ("Referrer-Policy", "referrer leakage control", "low"),
    ("Permissions-Policy", "feature policy", "low"),
]


class Context:
    def __init__(self, url, route, session, emit, add_finding):
        self.url = url
        self.route = route
        self.session = session
        self.parsed = urlparse(url)
        self.emit = emit
        self.add_finding = add_finding
        self._cache = {}
        self.response = None
        self.html = ""
        self.soup = None
        self.notes = {}
        self.new_onions = set()

    def fetch(self, path=None, timeout=None, allow_redirects=True):
        url = self.url if path is None else urljoin(self.url, path)
        if url in self._cache:
            return self._cache[url]
        try:
            r = self.session.get(url, timeout=timeout or 12, allow_redirects=allow_redirects)
            self._cache[url] = r
            return r
        except Exception as exc:
            self._cache[url] = exc
            return exc

    @property
    def doc(self):
        if self.soup is None and self.html:
            self.soup = BeautifulSoup(self.html, "html.parser")
        return self.soup


# ---------------------------------------------------------------- checks ----


def check_reachability(ctx):
    ctx.emit("info", f"GET {ctx.url}")
    t0 = __import__("time").time()
    # hidden services over Tor can take a long time to build the circuit
    r = ctx.fetch(timeout=45 if ctx.route == "tor" else 20)
    if isinstance(r, Exception):
        ctx.emit("err", f"transport failure: {type(r).__name__}: {r}")
        return [
            ctx.add_finding("high", "Target unreachable", {"error": str(r), "route": ctx.route})
        ]
    ms = int((__import__("time").time() - t0) * 1000)
    ctx.notes["status_code"] = r.status_code
    ctx.notes["alive"] = r.status_code < 500
    chain = [f"{h.status_code} {h.url}" for h in r.history]
    ctx.emit("ok", f"HTTP {r.status_code} in {ms} ms, {len(r.content)} bytes, {len(r.history)} redirect(s)")
    for c in chain:
        ctx.emit("info", f"redirect → {c}")
    ctx.response = r
    ctx.html = r.text or ""
    findings = []
    if r.history:
        findings.append(
            ctx.add_finding("medium", "Redirect chain present", {"chain": chain, "final": r.url})
        )
    if r.status_code >= 500:
        findings.append(ctx.add_finding("medium", "Server error response", {"status": r.status_code}))
    return findings


def check_security_headers(ctx):
    if not ctx.response:
        return []
    headers = ctx.response.headers
    ctx.emit("info", f"inspecting {len(headers)} response headers")
    findings = []
    missing = []
    for header, label, sev in SEC_HEADERS:
        if header in headers:
            ctx.emit("ok", f"{header}: {headers[header][:90]}")
        else:
            missing.append(header)
            ctx.emit("warn", f"{header}: absent")
    if missing:
        findings.append(ctx.add_finding("low", "Missing security headers", {"missing": missing}))
    if "Server" in headers:
        ctx.notes["server_banner"] = headers["Server"]
        findings.append(
            ctx.add_finding("info", "Server banner disclosed", {"banner": headers["Server"]})
        )
    if "X-Powered-By" in headers:
        ctx.notes["server_banner"] = ctx.notes.get("server_banner", "") + f" | {headers['X-Powered-By']}"
        findings.append(
            ctx.add_finding("medium", "X-Powered-By disclosed", {"value": headers["X-Powered-By"]})
        )
    return findings


def check_tls_certificate(ctx):
    host = ctx.parsed.hostname
    if not host:
        return []
    if ctx.parsed.scheme == "http" and ctx.route == "direct":
        ctx.emit("info", "target is plain HTTP — no certificate to inspect")
        return []
    ctx.emit("info", f"opening TLS session to :443 for {host} via {ctx.route}")
    try:
        cert = torclient.tls_certificate(host, 443, route=ctx.route, timeout=10)
    except Exception as exc:
        ctx.emit("warn", f"TLS handshake failed: {type(exc).__name__}: {exc}")
        return [ctx.add_finding("info", "TLS handshake failed", {"error": str(exc)})]
    summary = torclient.cert_summary(cert)
    ctx.notes["cert_subject"] = summary["subject"]
    ctx.notes["cert_org"] = summary["org"]
    findings = []
    ctx.emit("ok", f"subject: {summary['subject'] or '(none)'}")
    ctx.emit("ok", f"issuer : {summary['issuer']}")
    ctx.emit("info", f"validity: {summary['not_before']} → {summary['not_after']}")
    clearnet_sans = [s for s in summary["sans"] if not s.endswith(".onion")]
    if clearnet_sans:
        ctx.emit("warn", "certificate SANs reference clearnet names — infrastructure pivot")
        findings.append(
            ctx.add_finding(
                "high",
                "Certificate tied to clearnet domain(s)",
                {"sans": summary["sans"], "clearnet": clearnet_sans, "subject": summary["subject"]},
            )
        )
    if summary["org"]:
        findings.append(
            ctx.add_finding("medium", "Certificate organisation recorded", {"org": summary["org"]})
        )
    return findings


def _probe(args):
    path, base, route, timeout = args
    import requests as _rq

    session = torclient.build_session(route)
    try:
        resp = session.get(base + path, timeout=timeout, allow_redirects=False,
                           headers={"User-Agent": torclient.UA})
        return path, resp.status_code, len(resp.content), resp.headers.get("Content-Type", ""), (resp.text or "")[:400]
    except Exception as exc:
        return path, 0, 0, "", str(exc)


def check_sensitive_paths(ctx):
    base = ctx.url.rstrip("/")
    ctx.emit("info", f"probing {len(SENSITIVE_PATHS)} sensitive paths (8 workers, route={ctx.route})")
    findings = []
    jobs = [(p, base, ctx.route, 8) for p in SENSITIVE_PATHS]
    results = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = [pool.submit(_probe, j) for j in jobs]
        for f in as_completed(futs):
            results.append(f.result())
    hits = []
    for path, status, length, ctype, body in sorted(results):
        if status in (200, 301, 302, 403) and not _looks_like_spa(status, length, body):
            hits.append({"path": path, "status": status, "bytes": length, "type": ctype})
            level = "warn" if status == 200 else "info"
            ctx.emit(level, f"{status} {path} ({length} bytes)")
    if hits:
        exposed = [h for h in hits if h["status"] == 200]
        sev = "critical" if any(h["path"] in ("/.env", "/.git/config", "/server-status", "/phpinfo.php") for h in exposed) else "high"
        findings.append(ctx.add_finding(sev, "Sensitive path exposed", {"hits": hits}))
    else:
        ctx.emit("ok", "no sensitive paths answered with content")
    return findings


def _looks_like_spa(status, length, body):
    if status in (301, 302):
        return True
    if length == 0:
        return True
    low = (body or "").lower()
    if length < 400 and ("<!doctype html" in low or "<div id=" in low or "webpack" in low):
        if low.count("not found") > 0 or "single-page" in low:
            return True
    return False


def check_directory_listing(ctx):
    ctx.emit("info", f"checking {len(DIR_PATHS)} directories for index listings")
    findings = []
    for path in DIR_PATHS:
        r = ctx.fetch(path, timeout=8)
        if isinstance(r, Exception):
            continue
        if r.status_code == 200 and "Index of /" in (r.text or ""):
            ctx.emit("warn", f"directory listing enabled at {path}")
            findings.append(
                ctx.add_finding("medium", "Directory listing enabled", {"path": path, "status": 200})
            )
    if not findings:
        ctx.emit("ok", "no open directory listings")
    return findings


def check_robots_sitemap(ctx):
    findings = []
    r = ctx.fetch("/robots.txt", timeout=8)
    if not isinstance(r, Exception) and r.status_code == 200 and "Disallow" in (r.text or ""):
        lines = [ln.strip() for ln in r.text.splitlines() if ln.strip().lower().startswith(("disallow", "allow"))]
        ctx.emit("ok", f"robots.txt parsed — {len(lines)} rules")
        findings.append(ctx.add_finding("info", "robots.txt reveals hidden paths", {"rules": lines[:25]}))
    else:
        ctx.emit("info", "robots.txt: none or no rules")
    r2 = ctx.fetch("/sitemap.xml", timeout=8)
    if not isinstance(r2, Exception) and r2.status_code == 200 and "<url" in (r2.text or ""):
        locs = re.findall(r"<loc>(.*?)</loc>", r2.text)[:40]
        ctx.emit("ok", f"sitemap.xml parsed — {len(locs)} URLs")
        findings.append(ctx.add_finding("info", "Sitemap enumerated", {"urls": locs[:25]}))
    return findings


def check_cookies(ctx):
    if not ctx.response:
        return []
    jar = ctx.response.cookies
    if not jar:
        ctx.emit("info", "no cookies set")
        return []
    rows, issues = [], []
    for c in jar:
        row = {"name": c.name, "secure": bool(c.secure), "httponly": "HttpOnly" in str(c)}
        rows.append(row)
        ctx.emit("info", f"cookie {c.name} secure={row['secure']} httponly={row['httponly']}")
        if not row["secure"] or not row["httponly"]:
            issues.append(c.name)
    if issues:
        return [ctx.add_finding("low", "Session cookie missing flags", {"cookies": rows, "weak": issues})]
    return []


def check_cors(ctx):
    origin = "https://trinetra-probe.invalid"
    try:
        r = ctx.session.get(ctx.url, timeout=10, headers={"Origin": origin})
    except Exception as exc:
        ctx.emit("warn", f"CORS probe failed: {exc}")
        return []
    acao = r.headers.get("Access-Control-Allow-Origin", "")
    if not acao:
        ctx.emit("ok", "no Access-Control-Allow-Origin header")
        return []
    ctx.emit("warn", f"Access-Control-Allow-Origin: {acao}")
    if acao in ("*", origin):
        return [ctx.add_finding("medium", "Permissive CORS", {"acao": acao, "origin_sent": origin})]
    return [ctx.add_finding("info", "CORS policy observed", {"acao": acao})]


def check_external_resources(ctx):
    if not ctx.doc:
        return []
    base = ctx.parsed.netloc
    external = {}
    for tag, attr in (("script", "src"), ("img", "src"), ("link", "href"), ("iframe", "src")):
        for el in ctx.doc.find_all(tag):
            val = el.get(attr)
            if not val or val.startswith(("data:", "#", "/")):
                continue
            if val.startswith("//"):
                val = "http:" + val
            p = urlparse(val)
            if p.netloc and p.netloc != base:
                external.setdefault(p.netloc, set()).add(tag)
    if not external:
        ctx.emit("ok", "no third-party resources referenced")
        return []
    rows = [{"host": h, "tags": sorted(t)} for h, t in sorted(external.items())]
    for row in rows:
        ctx.emit("warn", f"clearnet dependency → {row['host']} ({', '.join(row['tags'])})")
    return [
        ctx.add_finding(
            "high",
            "Page depends on clearnet infrastructure (pivot surface)",
            {"resources": rows},
        )
    ]


def check_meta_and_comments(ctx):
    if not ctx.doc:
        return []
    findings = []
    title = (ctx.doc.title.string or "").strip() if ctx.doc.title else ""
    if title:
        ctx.notes["title"] = title[:255]
        ctx.emit("info", f"title: {title[:80]}")
    gen = ctx.doc.find("meta", attrs={"name": re.compile("^generator$", re.I)})
    if gen and gen.get("content"):
        ctx.emit("warn", f"generator meta leaked: {gen['content']}")
        findings.append(ctx.add_finding("low", "Generator meta disclosed", {"value": gen["content"]}))
    comments = []
    for c in ctx.doc.find_all(string=lambda t: isinstance(t, Comment)):
        text = str(c).strip()
        if 8 < len(text) < 400:
            comments.append(text)
    if comments:
        ctx.emit("warn", f"{len(comments)} HTML comments found")
        findings.append(
            ctx.add_finding("medium", "HTML comments leak implementation detail", {"comments": comments[:15]})
        )
    if ctx.response is not None and "ETag" in ctx.response.headers:
        etag = ctx.response.headers["ETag"]
        ctx.emit("info", f"ETag: {etag}")
        findings.append(
            ctx.add_finding("info", "ETag disclosed (rebuild/dedup signature)", {"etag": etag})
        )
    return findings


def check_favicon_hash(ctx):
    r = ctx.fetch("/favicon.ico", timeout=8)
    if isinstance(r, Exception) or r.status_code != 200 or not r.content:
        ctx.emit("info", "favicon: not served")
        return []
    h = hashlib.sha256(r.content).hexdigest()
    ctx.notes["favicon_hash"] = h
    ctx.emit("ok", f"favicon sha256: {h[:32]}…")
    return [ctx.add_finding("info", "Favicon fingerprint captured", {"sha256": h, "bytes": len(r.content)})]


def check_identifier_extraction(ctx):
    from . import extract as extract_mod

    if not ctx.html:
        return []
    found = extract_mod.extract(ctx.html, ctx.url)
    total = sum(len(v) for v in found.values())
    ctx.notes["found"] = found
    if not total:
        ctx.emit("info", "no reusable identifiers located in page body")
        return []
    for kind, values in sorted(found.items()):
        shown = ", ".join(v[:48] for v in values[:4])
        more = f" (+{len(values)-4} more)" if len(values) > 4 else ""
        ctx.emit("ok", f"{kind}: {shown}{more}")
    ctx.notes["new_onions"] = set(found.get("onion", []))
    return [
        ctx.add_finding(
            "high" if any(k in found for k in ("pgp", "btc", "xmr", "email")) else "info",
            "Identifiers harvested from page",
            {"counts": {k: len(v) for k, v in found.items()}, "samples": {k: v[:5] for k, v in found.items()}},
        )
    ]


def check_linked_onions(ctx):
    onions = ctx.notes.get("new_onions") or set()
    if not onions and ctx.html:
        onions = set(re.findall(r"\b[a-z2-7]{56}\.onion\b", ctx.html)) - {ctx.parsed.netloc}
    if not onions:
        ctx.emit("info", "no additional hidden services referenced")
        return []
    for o in sorted(onions)[:20]:
        ctx.emit("ok", f"discovered service: {o}")
    return [
        ctx.add_finding("info", "Linked hidden services discovered", {"onions": sorted(onions)[:40]})
    ]


CHECKS = [
    {"id": "reachability", "title": "Service reachability", "desc": "Fetch the target, record status code, redirect chain and latency.", "fn": check_reachability},
    {"id": "headers", "title": "Response header audit", "desc": "Security headers, server banner and framework fingerprints.", "fn": check_security_headers},
    {"id": "tls", "title": "TLS certificate analysis", "desc": "Subject, issuer, organisation and SANs — clearnet pivots.", "fn": check_tls_certificate},
    {"id": "sensitive", "title": "Sensitive path probe", "desc": "Parallel probe of .env, .git, server-status, phpinfo and friends.", "fn": check_sensitive_paths},
    {"id": "dirlist", "title": "Directory listing", "desc": "Detect open index pages that expose file trees.", "fn": check_directory_listing},
    {"id": "robots", "title": "robots / sitemap intel", "desc": "Hidden paths and URL inventory published by the operator.", "fn": check_robots_sitemap},
    {"id": "cookies", "title": "Cookie flags", "desc": "Session cookie hygiene (Secure / HttpOnly).", "fn": check_cookies},
    {"id": "cors", "title": "CORS policy", "desc": "Origin reflection and wildcard access-control.", "fn": check_cors},
    {"id": "resources", "title": "Clearnet dependency map", "desc": "Third-party scripts/assets that tie the onion to clearnet infra.", "fn": check_external_resources},
    {"id": "meta", "title": "Metadata & comment leaks", "desc": "Title, generator meta, HTML comments and ETags.", "fn": check_meta_and_comments},
    {"id": "favicon", "title": "Favicon fingerprint", "desc": "Stable asset hash used to cluster mirrored sites.", "fn": check_favicon_hash},
    {"id": "identifiers", "title": "Identifier extraction", "desc": "PGP blocks, wallets, e-mails, handles harvested from the page.", "fn": check_identifier_extraction},
    {"id": "linked", "title": "Linked service discovery", "desc": "Find other hidden services referenced by this page.", "fn": check_linked_onions},
]
