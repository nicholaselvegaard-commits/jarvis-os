import sys
sys.path.insert(0, '/opt/nexus')

from workers.orchestrator import Orchestrator

orch = Orchestrator()
print('=== DELEGATE TEST ===')
print('Task: Finn 3 norske IT-bedrifter i Bodo og lag en kort pitch til hver')
print()

result = orch.delegate(
    "Finn 3 norske IT-bedrifter i Bodo og analyser markedet",
    max_subtasks=4
)

print('PLAN:')
for step in result.get('plan', []):
    print(f"  - [{step['worker']}] {step['task']}")

print()
print(f"WORKERS USED: {result['workers_used']}")
print(f"DURATION: {result['duration_ms']}ms")
print(f"TOKENS: {result['total_tokens']}")
print()
print('SUMMARY:')
print(result['summary'])
