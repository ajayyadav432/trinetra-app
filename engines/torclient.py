"""HTTP/TLS helpers. All investigative traffic can be pinned to a local Tor SOCKS5."""

import socket
import ssl
import time

import requests

from config import Config

UA = "TRINETRA/1.0 (threat-intel collection; +local)"


def build_session(route: str = "tor") -> requests.Session:
    s = requests.Session()
    s.trust_env = False
    s.headers.update({"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,*/*;q=0.8"})
    if route == "tor":
        s.proxies = {"http": Config.TOR_SOCKS, "https": Config.TOR_SOCKS}
    return s


def get(url: str, route: str = "tor", timeout: int = None, session: requests.Session = None, **kw):
    s = session or build_session(route)
    return s.get(url, timeout=timeout or Config.REQUEST_TIMEOUT, allow_redirects=True, **kw)


def head(url: str, route: str = "tor", timeout: int = None, session: requests.Session = None, **kw):
    s = session or build_session(route)
    return s.head(url, timeout=timeout or Config.REQUEST_TIMEOUT, allow_redirects=True, **kw)


def tls_certificate(host: str, port: int = 443, route: str = "direct", timeout: int = 10):
    """Return the parsed peer certificate dict for a host, optionally through Tor."""
    if route == "tor":
        import socks

        sock = socks.create_connection(
            (host, port),
            proxy_type=socks.SOCKS5,
            proxy_addr="127.0.0.1",
            proxy_port=9050,
            proxy_rdns=True,
            timeout=timeout,
        )
    else:
        sock = socket.create_connection((host, port), timeout=timeout)

    ctx = ssl.create_default_context()
    try:
        with ctx.wrap_socket(sock, server_hostname=host) as ssock:
            return ssock.getpeercert()
    finally:
        try:
            sock.close()
        except Exception:
            pass


def cert_summary(cert: dict) -> dict:
    """Flatten an ssl.getpeercert() dict into investigation-friendly fields."""
    out = {"subject": "", "issuer": "", "org": "", "sans": [], "not_before": "", "not_after": ""}
    if not cert:
        return out

    def _flat(pairs):
        return {k: v for tup in pairs for k, v in tup}

    subj = _flat(cert.get("subject", ()))
    iss = _flat(cert.get("issuer", ()))
    out["subject"] = ", ".join(f"{k}={v}" for k, v in subj.items())
    out["issuer"] = ", ".join(f"{k}={v}" for k, v in iss.items())
    out["org"] = subj.get("organizationName", subj.get("commonName", ""))
    out["sans"] = [v.split(":", 1)[1] for typ, v in cert.get("subjectAltName", ()) if typ == "DNS"]
    out["not_before"] = cert.get("notBefore", "")
    out["not_after"] = cert.get("notAfter", "")
    return out


def elapsed_ms(t0: float) -> int:
    return int((time.time() - t0) * 1000)
