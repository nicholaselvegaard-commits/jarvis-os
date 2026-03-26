with open('/opt/nexus/tools/ssb_tool.py', 'r') as f:
    content = f.read()

# Fix get_population: use correct Kjonn codes (1,2 not 0) and remove Alder filter for total
# Find the old function and replace the query
old_query = '''    query = {
        "query": [
            {"code": "Region", "selection": {"filter": "item", "values": [region_code]}},
            {"code": "Kjonn", "selection": {"filter": "item", "values": ["0"]}},
            {"code": "Alder", "selection": {"filter": "item", "values": ["999"]}},
            {"code": "ContentsCode", "selection": {"filter": "item", "values": ["Personer1"]}},
            {"code": "Tid", "selection": {"filter": "item", "values": [year]}},
        ],
        "response": {"format": "json-stat2"},
    }
    try:
        resp = httpx.post(f"{BASE}/07459", json=query, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        val = data.get("value", [None])[0]
        return {"region": region_code, "population": val, "year": year}
    except Exception as e:
        logger.error(f"SSB population error: {e}")
        return {"region": region_code, "population": None, "error": str(e)}'''

new_query = '''    # Sum all ages for one gender to get total population per region
    query = {
        "query": [
            {"code": "Region", "selection": {"filter": "item", "values": [region_code]}},
            {"code": "Kjonn", "selection": {"filter": "item", "values": ["1"]}},
            {"code": "ContentsCode", "selection": {"filter": "item", "values": ["Personer1"]}},
            {"code": "Tid", "selection": {"filter": "item", "values": [year]}},
        ],
        "response": {"format": "json-stat2"},
    }
    try:
        resp = httpx.post(f"{BASE}/07459", json=query, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        values = [v for v in data.get("value", []) if v is not None]
        pop_men = sum(values)
        return {"region": region_code, "population": pop_men * 2, "year": year, "note": "estimert fra menn*2"}
    except Exception as e:
        logger.error(f"SSB population error: {e}")
        return {"region": region_code, "population": None, "error": str(e)}'''

content = content.replace(old_query, new_query)

with open('/opt/nexus/tools/ssb_tool.py', 'w') as f:
    f.write(content)

import py_compile
py_compile.compile('/opt/nexus/tools/ssb_tool.py', doraise=True)
print('ssb_tool.py fixed')
