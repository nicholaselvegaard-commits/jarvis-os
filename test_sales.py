import sys
sys.path.insert(0, '/opt/nexus')

from workers.specialists import SalesWorker

worker = SalesWorker()
result = worker.run(
    "Finn 3 IT-bedrifter i Bodø. Bruk brreg_search med municipality=Bodo og industry=62. "
    "List navn, org.nr og adresse for de 3 første du finner."
)
print('SUCCESS:', result['success'])
print('TOKENS:', result['tokens_used'])
print('DURATION:', result['duration_ms'], 'ms')
print()
print(result['result'][:1000])
