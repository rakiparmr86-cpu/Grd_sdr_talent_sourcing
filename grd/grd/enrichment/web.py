from __future__ import annotations

import re

import httpx

from grd.enrichment.base import EnrichmentProvider
from grd.enrichment.capabilities import WEB_FETCH, CapabilityResult, Fact
from grd.schemas import ContactProfile, ResearchIssue

_UA = "GRD-AI-SDR/0.1 (+research bot; contact your admin)"
_CAREERS_PATHS = ["/careers", "/jobs", "/careers/", "/company/careers", "/about/careers"]
_JOB_LINK_RE = re.compile(r"(job|role|position|opening|vacanc)", re.I)


class WebEnrichmentProvider(EnrichmentProvider):
    """Fetches the company's OWN website + a careers page. Real HTTP, best effort.

    Only touches the target domain - never third-party sites (LinkedIn etc.),
    which must come from a licensed data provider added alongside this one.
    On failure it emits a `site_blocked` issue rather than raising.
    """

    name = "web"
    capabilities = {WEB_FETCH}

    def __init__(self, timeout: float = 10.0) -> None:
        self.timeout = timeout

    async def call(
        self, capability: str, *, domain: str, contact_hint: ContactProfile | None = None
    ) -> CapabilityResult:
        res = CapabilityResult()
        if capability != WEB_FETCH:
            return res

        base = f"https://{domain}"
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout, follow_redirects=True, headers={"User-Agent": _UA}
            ) as client:
                home = await self._get(client, base)
                if home is None:
                    res.issues.append(ResearchIssue(
                        kind="site_blocked",
                        detail=f"could not fetch {base} (no 200 HTML response)",
                        capability=WEB_FETCH, source=base,
                    ))
                    return res

                name, description = _title_and_description(home)
                if name:
                    res.facts.append(Fact("name", name, base, WEB_FETCH))
                if description:
                    res.facts.append(Fact("description", description, base, WEB_FETCH))

                open_roles, careers_url = await self._count_open_roles(client, base, home)
                if open_roles is not None:
                    res.facts.append(Fact("open_roles", open_roles, careers_url or base, WEB_FETCH))
        except Exception as exc:  # noqa: BLE001 - provider is best effort
            res.issues.append(ResearchIssue(
                kind="site_blocked",
                detail=f"{type(exc).__name__} fetching {base}",
                capability=WEB_FETCH, source=base,
            ))
        return res

    async def _get(self, client: httpx.AsyncClient, url: str) -> str | None:
        try:
            resp = await client.get(url)
            if resp.status_code == 200 and "text/html" in resp.headers.get("content-type", ""):
                return resp.text
        except httpx.HTTPError:
            return None
        return None

    async def _count_open_roles(
        self, client: httpx.AsyncClient, base: str, home_html: str
    ) -> tuple[int | None, str | None]:
        for path in _CAREERS_PATHS:
            html = await self._get(client, base + path)
            if not html:
                continue
            job_links = {ln for ln in re.findall(r'href="([^"]+)"', html) if _JOB_LINK_RE.search(ln)}
            if job_links:
                return len(job_links), base + path
        job_links = {ln for ln in re.findall(r'href="([^"]+)"', home_html) if _JOB_LINK_RE.search(ln)}
        return (len(job_links) or None), (base if job_links else None)


def _title_and_description(html: str) -> tuple[str | None, str | None]:
    try:
        from bs4 import BeautifulSoup
    except ImportError:  # pragma: no cover
        m = re.search(r"<title>(.*?)</title>", html, re.I | re.S)
        return (m.group(1).strip() if m else None), None

    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.string.strip() if soup.title and soup.title.string else None
    desc = None
    tag = soup.find("meta", attrs={"name": "description"}) or soup.find(
        "meta", attrs={"property": "og:description"}
    )
    if tag and tag.get("content"):
        desc = tag["content"].strip()
    return title, desc
