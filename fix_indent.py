with open('/opt/nexus/workers/specialists.py', 'r') as f:
    lines = f.readlines()

# Find the for loop and fix indentation of the block after it
new_lines = []
in_brreg_for = False
for i, line in enumerate(lines):
    if 'for r in results[:8]:' in line and 'brreg' in ''.join(lines[max(0,i-5):i]):
        in_brreg_for = True
        new_lines.append(line)
        continue
    if in_brreg_for:
        stripped = line.lstrip()
        if stripped and not stripped.startswith('#'):
            # These lines need to be indented inside the for loop
            if any(stripped.startswith(k) for k in ['name =', 'org =', 'addr =', 'emp =', 'lines.append(', 'return']):
                if stripped.startswith('return'):
                    in_brreg_for = False
                    new_lines.append(line)
                else:
                    # Ensure 20 spaces indent (inside for loop which is at 16 spaces)
                    new_lines.append(' ' * 20 + stripped)
                continue
            else:
                in_brreg_for = False
    new_lines.append(line)

with open('/opt/nexus/workers/specialists.py', 'w') as f:
    f.writelines(new_lines)

import py_compile
py_compile.compile('/opt/nexus/workers/specialists.py', doraise=True)
print('specialists.py: indentation fixed, syntax OK')
