"""Optional Apify-backed web price lookup for preliminary repair planning."""

import json
import time

import httpx

from app import config
from app.model import systemAi

_search_cache = {}  # query -> (monotonic time, normalized public search items)


def _search_items(value):
    """Flatten Google Search Scraper output and keep a few public organic results."""
    candidates = []

    def collect(node):
        if isinstance(node, list):
            for child in node:
                collect(child)
        elif isinstance(node, dict):
            nested = node.get("organicResults") or node.get("organic_results") or node.get("results")
            if isinstance(nested, (list, dict)):
                collect(nested)
            elif node.get("url") or node.get("link"):
                candidates.append(node)

    collect(value)
    out = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or item.get("link") or "").strip()
        title = str(item.get("title") or "").strip()
        snippet = str(item.get("description") or item.get("snippet") or item.get("text") or "").strip()
        if url.startswith("http") and (title or snippet):
            out.append({"title": title[:180], "url": url[:500], "snippet": snippet[:700]})
        if len(out) >= 6:
            break
    return out


def lookup_and_ground(analysis, location=""):
    """Search current PH price pages and let the configured model re-estimate from cited data.

    Returns source metadata only when the lookup yields usable results. Failure is deliberately
    non-fatal so photo reports from web and mobile continue through the existing flow.
    """
    if (not config.APIFY_API_TOKEN or analysis.get("image_kind") != "campus_issue"
            or analysis.get("shows_issue") not in ("yes", "possible")):
        return
    issue = analysis.get("issue_title") or "campus facility repair"
    repair = analysis.get("repair_approach") or "repair materials and labor"
    query = f'{issue} {repair} construction material price {location} Philippines PHP'.strip()
    cached = _search_cache.get(query)
    if cached and time.monotonic() - cached[0] < 6 * 60 * 60:
        items = cached[1]
    else:
        try:
            response = httpx.post(
                f"https://api.apify.com/v2/acts/{config.APIFY_PRICE_ACTOR.replace('/', '~')}/run-sync-get-dataset-items",
                headers={"Authorization": f"Bearer {config.APIFY_API_TOKEN}"},
                params={"timeout": 12, "memory": 512},
                # `resultsPerPage` is not an input supported by Apify's official Actor;
                # it controls how many pages are fetched via maxPagesPerQuery instead.
                json={"queries": query, "maxPagesPerQuery": 1, "countryCode": "ph", "languageCode": "en"},
                timeout=18,
            )
            response.raise_for_status()
            items = _search_items(response.json())
            if items:
                _search_cache[query] = (time.monotonic(), items)
        except Exception as error:
            detail = getattr(getattr(error, "response", None), "text", "")
            print("APIFY PRICE LOOKUP:", repr(error)[:180], str(detail)[:400])
            return
    if not items:
        return

    sources = [{"title": item["title"], "url": item["url"]} for item in items]
    prompt = """You estimate preliminary repair costs for a Philippine university. Use ONLY the supplied web search snippets as current price evidence for materials. Do not invent prices, units, or measurements. If the snippets do not contain relevant numeric prices, return null for both budget values. Add likely labor only as a clearly labeled rough allowance, not as a web-sourced price. Keep the provided severity, workers, and duration unless the evidence clearly requires changing them. Return JSON only with exactly: estimated_budget_php_min (integer or null), estimated_budget_php_max (integer or null), estimate_assumptions (short string), pricing_basis (short string), pricing_sources (array of objects with title and url copied from supplied sources). Budget min/max must be a broad total repair planning range, not a unit price."""
    question = json.dumps({"issue": issue, "possible_repair": repair,
                           "current_estimate_php": [analysis.get("estimated_budget_php_min"),
                                                     analysis.get("estimated_budget_php_max")],
                           "staff": analysis.get("estimated_staff"),
                           "working_days": [analysis.get("estimated_days_min"), analysis.get("estimated_days_max")],
                           "search_results": items}, ensure_ascii=False)
    answer = systemAi.ask_model(prompt, question)
    if not answer:
        return
    try:
        start, end = answer.find("{"), answer.rfind("}")
        try:
            result = json.loads(answer[start:end + 1]) if start >= 0 and end > start else {}
        except ValueError:
            # Some model backends occasionally append malformed source arrays. Salvage only
            # the two numeric budget fields; the sources still come from Apify's actual items.
            import re
            result = {}
            for key in ("estimated_budget_php_min", "estimated_budget_php_max"):
                match = re.search(r'"' + key + r'"\s*:\s*(null|-?\d+)', answer)
                if match:
                    result[key] = None if match.group(1) == "null" else int(match.group(1))
            match = re.search(r'"estimate_assumptions"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"', answer)
            if match:
                try:
                    result["estimate_assumptions"] = json.loads('"' + match.group(1) + '"')
                except ValueError:
                    pass
        low, high = result.get("estimated_budget_php_min"), result.get("estimated_budget_php_max")
        if (isinstance(low, int) and not isinstance(low, bool) and
                isinstance(high, int) and not isinstance(high, bool) and 0 <= low <= high <= 100_000_000):
            analysis["estimated_budget_php_min"] = low
            analysis["estimated_budget_php_max"] = high
            analysis["estimate_assumptions"] = str(result.get("estimate_assumptions") or analysis.get("estimate_assumptions") or "")[:400]
            analysis["pricing_basis"] = str(result.get("pricing_basis") or "Apify web search; preliminary and unverified")[:400]
            returned_sources = result.get("pricing_sources")
            valid_urls = {item["url"] for item in sources}
            if isinstance(returned_sources, list):
                analysis["pricing_sources"] = [
                    {"title": str(item.get("title") or "Price source")[:180], "url": str(item.get("url") or "")[:500]}
                    for item in returned_sources if isinstance(item, dict) and item.get("url") in valid_urls
                ][:6]
            if not analysis.get("pricing_sources"):
                analysis["pricing_sources"] = sources
    except (ValueError, TypeError, AttributeError) as error:
        print("APIFY PRICE ESTIMATE:", repr(error)[:200])
