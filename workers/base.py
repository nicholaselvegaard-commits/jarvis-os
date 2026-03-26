"""
BaseWorker — Grunnklasse for alle Jarvis-arbeidere.

Hver arbeider er en Claude-instans med:
  - Spesialisert systemprompt
  - Begrenset verktøysett for sin domene
  - Delt Brain (KG + vector + Obsidian)
  - Resultat rapporteres tilbake til Jarvis (NEXUS)

Bruk:
    from workers.base import BaseWorker
    worker = ResearchWorker()
    result = await worker.run("Finn markedsdata for Bodø kommune")
"""
import asyncio
import json
import logging
import os
import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv
load_dotenv("/opt/nexus/.env")
import anthropic

logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
DEFAULT_MODEL = "claude-haiku-4-5-20251001"  # Fast + cheap for workers
ORCHESTRATOR_MODEL = "claude-sonnet-4-6"  # Strong for orchestrator


class BaseWorker(ABC):
    """
    Base class for all Jarvis workers.
    Each worker has a specialty and runs autonomously.
    """

    name: str = "base_worker"
    specialty: str = "general"
    model: str = DEFAULT_MODEL
    max_tokens: int = 2048
    max_iterations: int = 8

    def __init__(self):
        self.client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        self._brain = None
        self.logs = []

    @property
    def brain(self):
        if self._brain is None:
            try:
                import sys
                sys.path.insert(0, "/opt/nexus")
                from memory.brain import Brain
                self._brain = Brain()
            except Exception as e:
                logger.warning(f"Brain unavailable in worker {self.name}: {e}")
        return self._brain

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """System prompt for this worker's specialty."""
        pass

    @property
    @abstractmethod
    def tools(self) -> list:
        """Tool schemas available to this worker."""
        pass

    def handle_tool(self, name: str, inputs: dict) -> str:
        """
        Execute a tool call. Override in subclass for custom tools.
        Returns string result.
        """
        return f"Tool {name} not implemented in {self.name}"

    def run(self, task: str, context: str = "") -> dict:
        """
        Run this worker on a task synchronously.
        Returns: {success, result, worker, duration_ms, tokens_used}
        """
        start = time.time()
        messages = []
        total_tokens = 0

        # Build initial message
        user_content = task
        if context:
            user_content = f"Kontekst:\n{context}\n\n---\nOppgave: {task}"

        messages.append({"role": "user", "content": user_content})
        self._log(f"START: {task[:80]}")

        for iteration in range(self.max_iterations):
            try:
                kwargs = {
                    "model": self.model,
                    "max_tokens": self.max_tokens,
                    "system": self.system_prompt,
                    "messages": messages,
                }
                if self.tools:
                    kwargs["tools"] = self.tools

                response = self.client.messages.create(**kwargs)
                total_tokens += response.usage.input_tokens + response.usage.output_tokens

                # Collect tool uses and text
                tool_uses = []
                text_parts = []

                for block in response.content:
                    if block.type == "text":
                        text_parts.append(block.text)
                    elif block.type == "tool_use":
                        tool_uses.append(block)

                # Add assistant message
                messages.append({"role": "assistant", "content": response.content})

                if response.stop_reason == "end_turn" or not tool_uses:
                    # Done
                    final_text = "\n".join(text_parts).strip()
                    duration = int((time.time() - start) * 1000)
                    self._log(f"DONE in {iteration+1} iterations, {total_tokens} tokens")
                    return {
                        "success": True,
                        "result": final_text,
                        "worker": self.name,
                        "specialty": self.specialty,
                        "duration_ms": duration,
                        "tokens_used": total_tokens,
                        "iterations": iteration + 1,
                    }

                # Execute tools
                tool_results = []
                for tool_use in tool_uses:
                    self._log(f"TOOL: {tool_use.name}({json.dumps(tool_use.input)[:60]})")
                    try:
                        result = self.handle_tool(tool_use.name, tool_use.input)
                    except Exception as e:
                        result = f"Error: {e}"
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": str(result)[:4000],
                    })

                messages.append({"role": "user", "content": tool_results})

            except anthropic.APIError as e:
                duration = int((time.time() - start) * 1000)
                self._log(f"API ERROR: {e}")
                return {
                    "success": False,
                    "result": f"API error: {e}",
                    "worker": self.name,
                    "duration_ms": duration,
                    "tokens_used": total_tokens,
                }

        duration = int((time.time() - start) * 1000)
        return {
            "success": False,
            "result": "Max iterations reached",
            "worker": self.name,
            "duration_ms": duration,
            "tokens_used": total_tokens,
        }

    def _log(self, msg: str):
        ts = datetime.utcnow().strftime("%H:%M:%S")
        entry = f"[{self.name}@{ts}] {msg}"
        self.logs.append(entry)
        logger.info(entry)
