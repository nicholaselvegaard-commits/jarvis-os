import sys
sys.path.insert(0, '/opt/nexus')

from workers.orchestrator import Orchestrator
from memory.brain import Brain

brain = Brain()
orch = Orchestrator()

print('=== BRAIN STATUS ===')
print(brain.status())

print()
print('=== PARALLEL WORKERS TEST ===')
results = orch.run_parallel([
    ('analytics', 'Gi en 3-linjers statusrapport om Jarvis per i dag'),
    ('memory', 'Legg til node: firma=TestAS, type=company, importance=2. Lag relasjon: TestAS er_potensiell_kunde_av jarvis'),
])
for res in results:
    w = res.get('worker', '?')
    ok = 'OK' if res.get('success') else 'FEIL'
    ms = res.get('duration_ms', 0)
    print(f'{w}: {ok} ({ms}ms)')
    print(res.get('result','')[:200])
    print()

print('=== BRAIN SUMMARY AFTER WORKERS ===')
print(brain.status())
