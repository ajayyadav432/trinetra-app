"""Identifier extraction: turn raw HTML into typed, deduplicated entities."""

import re
from urllib.parse import urlparse

RE_PGP_BLOCK = re.compile(
    r"(-----BEGIN PGP (?:PUBLIC|PRIVATE) KEY BLOCK-----.*?-----END PGP (?:PUBLIC|PRIVATE) KEY BLOCK-----)",
    re.DOTALL | re.IGNORECASE,
)
RE_PGP_FINGERPRINT = re.compile(r"\b(?:[0-9A-F]{4}\s+){9}[0-9A-F]{4}\b")
RE_BTC = re.compile(r"\b(?:bc1[0-9a-z]{25,59}|[13][a-km-zA-HJ-NP-Z1-9]{25,34})\b")
RE_ETH = re.compile(r"\b0x[a-fA-F0-9]{40}\b")
RE_XMR = re.compile(r"\b[48][0-9A-Za-z]{93,105}\b")
RE_EMAIL = re.compile(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b")
RE_TELEGRAM = re.compile(r"(?:t\.me/|telegram\.me/)([A-Za-z0-9_]{4,32})")
RE_DISCORD = re.compile(r"(?:discord(?:app)?\.com/invite/|discord.gg/)([A-Za-z0-9-]{2,32})")
RE_SESSION = re.compile(r"\b05[0-9a-f]{64}\b")
RE_ONION = re.compile(r"\b[a-z2-7]{56}\.onion\b")
RE_DOMAIN = re.compile(r"\b(?:[a-z0-9-]+\.)+(?:com|net|org|io|ru|su|onion|xyz|info|biz|co|uk|de)\b", re.I)

STOP_DOMAINS = {
    "w3.org", "schema.org", "googleapis.com", "google.com", "gstatic.com", "jsdelivr.net",
    "cloudflare.com", "github.com", "youtube.com", "twitter.com", "facebook.com", "example.com",
    "localhost",
}


def extract(html: str, base_url: str = "") -> dict:
    """Return {kind: [values]} found in a document."""
    text = html or ""
    out: dict[str, list[str]] = {}

    def add(kind, values, clean=None):
        vals = []
        for v in values:
            v = clean(v) if clean else v
            v = v.strip()
            if v and v not in vals:
                vals.append(v)
        if vals:
            out.setdefault(kind, []).extend(v for v in vals if v not in out[kind])

    add("pgp", RE_PGP_BLOCK.findall(text))
    add("pgp_fingerprint", RE_PGP_FINGERPRINT.findall(text))
    add("btc", RE_BTC.findall(text))
    add("eth", RE_ETH.findall(text))
    add("xmr", RE_XMR.findall(text))
    add("email", RE_EMAIL.findall(text))
    add("telegram", RE_TELEGRAM.findall(text))
    add("discord", RE_DISCORD.findall(text))
    add("session_id", RE_SESSION.findall(text))

    onions = {o.lower() for o in RE_ONION.findall(text)}
    base_host = urlparse(base_url).netloc
    add("onion", [o for o in onions if o != base_host])

    domains = []
    for d in RE_DOMAIN.findall(text):
        d = d.lower().strip(".")
        if d in STOP_DOMAINS or d.endswith(".onion"):
            continue
        if any(d.endswith("." + s) for s in STOP_DOMAINS):
            continue
        domains.append(d)
    add("domain", domains)

    return out


def upsert(db, identifier_cls, mention_cls, asset, scan, found: dict) -> int:
    """Persist extracted identifiers and their asset mentions. Returns count written."""
    written = 0
    from datetime import datetime

    for kind, values in found.items():
        for value in values:
            norm = value.lower() if kind not in ("pgp",) else re.sub(r"\s+", "", value).lower()
            ident = identifier_cls.query.filter_by(kind=kind, norm=norm).first()
            if not ident:
                ident = identifier_cls(kind=kind, value=value, norm=norm)
                db.session.add(ident)
                db.session.flush()
            ident.last_seen = datetime.utcnow()
            if not mention_cls.query.filter_by(identifier_id=ident.id, asset_id=asset.id).first():
                db.session.add(
                    mention_cls(identifier_id=ident.id, asset_id=asset.id, scan_id=getattr(scan, "id", None))
                )
                written += 1
    db.session.commit()
    return written
