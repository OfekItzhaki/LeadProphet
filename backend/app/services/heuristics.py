from urllib.parse import urlparse

import httpx


async def inspect_website(url: str | None) -> dict:
    if not url:
        return {"available": False, "notes": "No website URL provided.", "tech_stack": {}}

    normalized_url = url if url.startswith(("http://", "https://")) else f"https://{url}"
    parsed = urlparse(normalized_url)
    heuristics = {
        "available": False,
        "normalized_url": normalized_url,
        "uses_https": parsed.scheme == "https",
        "status_code": None,
        "title": None,
        "html_excerpt": "",
        "tech_stack": {},
        "notes": "",
    }

    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            response = await client.get(normalized_url, headers={"User-Agent": "LeadProphetBot/0.1"})
        text = response.text[:5000]
        lower = text.lower()
        heuristics.update(
            {
                "available": response.status_code < 500,
                "status_code": response.status_code,
                "html_excerpt": text[:1800],
                "tech_stack": {
                    "wordpress": "wp-content" in lower,
                    "wix": "wixstatic" in lower,
                    "shopify": "cdn.shopify.com" in lower or "myshopify" in lower,
                    "react": "react" in lower or "__next" in lower,
                },
            }
        )
    except Exception as exc:
        heuristics["notes"] = f"Website fetch failed: {exc}"

    return heuristics

