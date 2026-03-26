with open('/opt/nexus/workers/specialists.py', 'r') as f:
    lines = f.readlines()

# Find and replace the brreg result formatting lines
new_lines = []
skip_next = 0
for i, line in enumerate(lines):
    if skip_next > 0:
        skip_next -= 1
        continue
    if "r.get('navn','?')" in line or "r.get('organisasjonsnummer','?')" in line:
        # Replace with correct field names
        indent = '                '
        new_lines.append(f"{indent}name = r.get('name', r.get('navn', '?'))\n")
        new_lines.append(f"{indent}org = r.get('org_number', r.get('organisasjonsnummer', '?'))\n")
        new_lines.append(f"{indent}addr = r.get('address', '?')\n")
        new_lines.append(f"{indent}emp = r.get('employees', 0)\n")
        new_lines.append(f'{indent}lines.append("- " + name + " | Org: " + str(org) + " | " + addr + " | " + str(emp) + " ansatte")\n')
    else:
        new_lines.append(line)

with open('/opt/nexus/workers/specialists.py', 'w') as f:
    f.writelines(new_lines)

import py_compile
py_compile.compile('/opt/nexus/workers/specialists.py', doraise=True)
print('specialists.py: brreg field names fixed, syntax OK')
