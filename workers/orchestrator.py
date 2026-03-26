"""
Orchestrator — Jarvis sin arbeidsfordeler.

Tar en overordnet oppgave, deler den opp i deltasks, og kjører
de riktige arbeiderne — parallelt der det er mulig.

Bruk:
    from workers.orchestrator import Orchestrator
    orch = Orchestrator()

    # Kjør en enkelt arbeider
    result = orch.run_worker("research", "Finn markedsdata for Bodø")

    # Kjør mange arbeidere parallelt
    results = orch.run_parallel([
        ("research", "Finn 5 norske IT-bedrifter i Bodø"),
        ("sales",    "Finn kontakt hos Lystpaa AS"),
        ("analytics","Hva er total inntekt denne måneden?"),
    ])

    # La orchestrator selv bestemme arbeiderfordeling
    results = orch.delegate("Finn 3 leads i Bodø og skriv en pitch til hver")
"""
import concurrent.futures
import json
import logging
import os
import sys
import time
from datetime import datetime
from typing import Optional

sys.path.insert(0, "/opt/nexus")

import anthropic

from workers.base import ORCHESTRATOR_MODEL
from workers.specialists import WORKER_REGISTRY, get_worker

logger = logging.getLogger(__name__)


class Orchestrator:
    """
    Fordeler oppgaver til riktige arbeidere, kjører parallelt.
    Har tilgang til alle arbeidere og kan spawne flere instanser.
    """

    def __init__(self):
        self.client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
        self._results_cache = []

    def run_worker(self, specialty: str, task: str, context: str = "") -> dict:
        """Kjør en enkelt arbeider og returner resultatet."""
        worker = get_worker(specialty)
        logger.info(f"Orchestrator → {specialty}: {task[:60]}")
        return worker.run(task, context=context)

    def run_parallel(self, tasks: list[tuple], max_workers: int = 4) -> list[dict]:
        """
        Kjør flere arbeidere parallelt.

        Args:
            tasks: [(specialty, task_text), ...] eller [(specialty, task, context), ...]
            max_workers: Maks parallelle tråder

        Returns:
            Liste med resultater i samme rekkefølge som tasks
        """
        results = [None] * len(tasks)

        def run_one(idx_specialty_task):
            idx, item = idx_specialty_task
            if len(item) == 2:
                specialty, task = item
                context = ""
            else:
                specialty, task, context = item
            try:
                result = self.run_worker(specialty, task, context)
                result["task_index"] = idx
                return idx, result
            except Exception as e:
                return idx, {
                    "success": False,
                    "result": f"Worker error: {e}",
                    "worker": item[0],
                    "task_index": idx,
                }

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(run_one, (i, task)) for i, task in enumerate(tasks)]
            for future in concurrent.futures.as_completed(futures):
                idx, result = future.result()
                results[idx] = result

        self._results_cache.extend(results)
        return results

    def delegate(self, master_task: str, max_subtasks: int = 5) -> dict:
        """
        La Orchestrator planlegge og delegere en sammensatt oppgave.

        1. Bruker Claude (Sonnet) til å dele opp i subtasks med riktige arbeidere
        2. Kjører arbeidere parallelt
        3. Syntetiserer resultater til en sluttrapport

        Returns:
            {plan, results, summary, total_tokens, duration_ms}
        """
        start = time.time()
        total_tokens = 0

        # Step 1: Plan decomposition
        plan_prompt = f"""Du er orchestrator for Jarvis, et AI-agent system.

Tilgjengelige arbeidere:
- research: websøk, markedsanalyse, nyhetssøk
- sales: leadgenerering, Brreg, Apollo kontakter
- content: skrive innhold, Obsidian-notater
- analytics: SSB-data, Stripe-inntekt, KPI-rapporter
- memory: knowledge graph, lagre/hente minner
- code: kjøre Python, lage verktøy

Oppgave: {master_task}

Svar KUN med JSON-array (maks {max_subtasks} oppgaver):
[
  {{"worker": "research", "task": "..."}},
  {{"worker": "sales", "task": "..."}},
  ...
]

Vær konkret. Ikke dupliser arbeid. Velg riktig arbeider for hvert deltrinn."""

        response = self.client.messages.create(
            model=ORCHESTRATOR_MODEL,
            max_tokens=800,
            messages=[{"role": "user", "content": plan_prompt}],
        )
        total_tokens += response.usage.input_tokens + response.usage.output_tokens

        plan_text = response.content[0].text.strip()
        # Extract JSON
        try:
            if "```" in plan_text:
                plan_text = plan_text.split("```")[1]
                if plan_text.startswith("json"):
                    plan_text = plan_text[4:]
            subtasks = json.loads(plan_text.strip())
        except Exception as e:
            logger.warning(f"Plan parsing failed: {e}\nRaw: {plan_text}")
            # Fallback: single research task
            subtasks = [{"worker": "research", "task": master_task}]

        logger.info(f"Orchestrator plan: {len(subtasks)} subtasks for: {master_task[:60]}")

        # Step 2: Run workers in parallel
        task_tuples = [(t["worker"], t["task"]) for t in subtasks if t.get("worker") in WORKER_REGISTRY]
        results = self.run_parallel(task_tuples)

        # Step 3: Synthesize
        results_text = ""
        for i, (subtask, result) in enumerate(zip(subtasks, results)):
            if result:
                status = "✓" if result.get("success") else "✗"
                results_text += f"\n### {status} {subtask['worker'].upper()}: {subtask['task']}\n"
                results_text += result.get("result", "Ingen svar")[:1500] + "\n"

        synth_prompt = f"""Originaloppgave: {master_task}

Arbeidernes resultater:
{results_text}

Skriv en kortfattet, handlingsrettet oppsummering på norsk. Punkt-form. Max 300 ord."""

        synth_response = self.client.messages.create(
            model=ORCHESTRATOR_MODEL,
            max_tokens=600,
            messages=[{"role": "user", "content": synth_prompt}],
        )
        total_tokens += synth_response.usage.input_tokens + synth_response.usage.output_tokens
        summary = synth_response.content[0].text.strip()

        duration = int((time.time() - start) * 1000)

        return {
            "plan": subtasks,
            "results": results,
            "summary": summary,
            "total_tokens": total_tokens,
            "duration_ms": duration,
            "workers_used": len(results),
        }

    def worker_swarm(self, task_template: str, inputs: list[str], specialty: str = "research") -> list[dict]:
        """
        Spawn mange arbeidere av samme type på forskjellige inputs.
        Nyttig for: 'analyser disse 10 bedriftene' → 10 parallelle sales-workers.

        Args:
            task_template: Template med {input} placeholder
            inputs: Liste med verdier å sette inn
            specialty: Hvilken arbeider-type

        Returns:
            Liste med resultater
        """
        tasks = [(specialty, task_template.format(input=inp)) for inp in inputs]
        return self.run_parallel(tasks, max_workers=min(len(tasks), 6))

    def status(self) -> dict:
        """Status for orchestrator og arbeidere."""
        return {
            "available_workers": list(WORKER_REGISTRY.keys()),
            "results_cached": len(self._results_cache),
            "model": ORCHESTRATOR_MODEL,
        }
