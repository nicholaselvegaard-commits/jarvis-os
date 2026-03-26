with open('/opt/nexus/workers/specialists.py', 'r') as f:
    content = f.read()

# Fix 1: research worker web search - use Brave API directly, no old import
old_research_search = '''        if name == "web_search":
            try:
                from tools import brave_search
                results = brave_search.search(inputs["query"])
                if isinstance(results, list):
                    return "\\n".join([f"- {r.get('title','')}: {r.get('description','')[:200]}" for r in results[:5]])
                return str(results)[:2000]
            except Exception as e:
                return f"Sokefeil: {e}"'''

new_research_search = '''        if name == "web_search":
            try:
                import os, requests as _req
                api_key = os.getenv("BRAVE_API_KEY", "")
                if not api_key:
                    return "Brave API key mangler."
                headers = {
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip",
                    "X-Subscription-Token": api_key,
                }
                resp = _req.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    headers=headers,
                    params={"q": inputs["query"], "count": 6},
                    timeout=15,
                )
                resp.raise_for_status()
                hits = resp.json().get("web", {}).get("results", [])
                lines = [h.get("title","") + ": " + h.get("description","")[:200] for h in hits[:5]]
                return "\\n".join(lines) if lines else "Ingen resultater."
            except Exception as e:
                return "Websok feil: " + str(e)'''

content = content.replace(old_research_search, new_research_search)

# Fix 2: brreg - correct function name
content = content.replace(
    'results = brreg.search(\n                    inputs["query"],\n                    municipality=inputs.get("municipality"),\n                    industry=inputs.get("industry"),\n                )',
    'results = brreg.search_companies(municipality=inputs.get("municipality",""), industry_code=inputs.get("industry",""))'
)

# Fix 3: apollo - correct function name
old_apollo = '''results = apollo.find_contacts(inputs["company_name"], title=inputs.get("title", "CEO"))'''
new_apollo = '''results = apollo.search_people(name=inputs.get("title","CEO"), organization_name=inputs["company_name"])'''
content = content.replace(old_apollo, new_apollo)

with open('/opt/nexus/workers/specialists.py', 'w') as f:
    f.write(content)
print("specialists.py fixed")
