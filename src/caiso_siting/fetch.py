"""One guarded HTTP GET for every download in this project.

Three things every fetch needs and none of the ad-hoc call sites had all of:

1. **The final URL must still be HTTPS, on a host we meant to talk to.** requests follows up to 30
   redirects by default and does not stop an https -> http downgrade, so an upstream host having a
   bad day (or a hijacked DNS answer) could hand us attacker-served bytes over plaintext.
2. **A ceiling on the body.** Every call site used `r.content`, which buffers the whole response.
   A 50 MB xlsx whose sheet inflates 20x is an out-of-memory kill of an unattended job holding a
   write token — no code execution, but the publish pipeline stops.
3. **Never overwrite a good file with a bad one.** Write `.part`, verify, then replace.
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

MAX_BYTES = 80 * 1024 * 1024
CHUNK = 1 << 20
USER_AGENT = "caiso-siting (+https://github.com/mrk-svg/caiso-siting)"

# Hosts this project is allowed to end up at. A redirect off this list is refused rather than
# followed: the point of pinning the URL is lost if the last hop can be anywhere.
ALLOWED_HOSTS = {
    "caiso.com", "oasis.caiso.com", "pge.com", "eia.gov", "energy.ca.gov", "ca.gov",
    "openstreetmap.org", "overpass-api.de", "arcgis.com", "sce.com", "sdge.com",
}


class UnsafeFetch(RuntimeError):
    """The response came from somewhere, or was larger than, we are willing to accept."""


def _host_ok(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in ALLOWED_HOSTS)


def get_bytes(url: str, *, timeout: int = 120, max_bytes: int = MAX_BYTES,
              allowed_hosts: set[str] | None = None) -> bytes:
    """GET `url` and return the body, refusing an unsafe redirect or an oversized response."""
    import requests

    if not url.lower().startswith("https://"):
        raise UnsafeFetch(f"refusing a non-HTTPS URL: {url}")
    hosts = allowed_hosts if allowed_hosts is not None else ALLOWED_HOSTS
    with requests.get(url, timeout=timeout, stream=True,
                      headers={"User-Agent": USER_AGENT}) as r:
        for hop in list(r.history) + [r]:
            u = hop.url
            if not u.lower().startswith("https://"):
                raise UnsafeFetch(f"redirect downgraded to plaintext: {u}")
            host = (urlparse(u).hostname or "").lower()
            if not any(host == h or host.endswith("." + h) for h in hosts):
                raise UnsafeFetch(f"redirect left the allowed hosts: {host}")
        r.raise_for_status()
        declared = r.headers.get("Content-Length")
        if declared and declared.isdigit() and int(declared) > max_bytes:
            raise UnsafeFetch(f"response declares {int(declared):,} bytes, over the {max_bytes:,} cap")
        buf = bytearray()
        for chunk in r.iter_content(CHUNK):
            buf += chunk
            if len(buf) > max_bytes:
                raise UnsafeFetch(f"response exceeded the {max_bytes:,} byte cap")
        return bytes(buf)


def download_to(url: str, dest: Path, *, verify=None, timeout: int = 120,
                max_bytes: int = MAX_BYTES) -> int:
    """Fetch `url` into `dest` via a `.part` file, running `verify(part)` before the replace.

    A good file is never destroyed by a bad download: if anything raises, `dest` is untouched.
    """
    body = get_bytes(url, timeout=timeout, max_bytes=max_bytes)
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    part.write_bytes(body)
    try:
        if verify is not None:
            verify(part)
        part.replace(dest)
    except Exception:
        part.unlink(missing_ok=True)
        raise
    return len(body)


def verify_xlsx(path: Path, min_bytes: int = 4096) -> None:
    """An HTML error page served with status 200 is the common failure; it is not a zip."""
    size = path.stat().st_size
    if size < min_bytes:
        raise UnsafeFetch(f"{path.name} is only {size:,} bytes — almost certainly not a workbook")
    with open(path, "rb") as fh:
        if fh.read(2) != b"PK":
            raise UnsafeFetch(f"{path.name} has no zip signature — not an xlsx")
