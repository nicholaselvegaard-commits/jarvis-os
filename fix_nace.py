import re
with open('/opt/nexus/workers/specialists.py', 'r') as f:
    content = f.read()

old_nace = '''                NACE_MAP = {
                    "IT": "62", "IKT": "62", "SOFTWARE": "62", "DATA": "62",
                    "PROGRAMVARE": "62", "TEKNOLOGI": "62", "TECH": "62",
                    "WEB": "63", "INTERNETT": "63",
                    "BYGG": "41", "INDUSTRI": "28", "HANDEL": "47",
                    "KONSULENT": "70", "REVISJON": "69", "REKLAME": "73",
                }
                ind = inputs.get("industry", "")
                if ind and not ind[:2].isdigit():
                    ind = NACE_MAP.get(ind.upper().strip(), ind)'''

new_nace = '''                NACE_MAP = {
                    "IT": "62", "IKT": "62", "SOFTWARE": "62", "DATA": "62",
                    "PROGRAMVARE": "62", "TEKNOLOGI": "62", "TECH": "62",
                    "TJENESTER": "62", "WEB": "63", "INTERNETT": "63",
                    "BYGG": "41", "INDUSTRI": "28", "HANDEL": "47",
                    "KONSULENT": "70", "REVISJON": "69", "REKLAME": "73",
                }
                ind = inputs.get("industry", "")
                if ind:
                    num_match = re.match(r"(\\d+)", ind.strip())
                    if num_match:
                        ind = num_match.group(1)
                    elif not ind[:2].isdigit():
                        ind_upper = ind.upper()
                        ind = next((code for kw, code in NACE_MAP.items() if kw in ind_upper), "62")'''

content = content.replace(old_nace, new_nace)

# Make sure re is imported at top
if 'import re' not in content[:200]:
    content = 'import re\n' + content

with open('/opt/nexus/workers/specialists.py', 'w') as f:
    f.write(content)

import py_compile
py_compile.compile('/opt/nexus/workers/specialists.py', doraise=True)
print('specialists.py: smart NACE mapping added, syntax OK')
