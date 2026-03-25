"""
BaseAgent — foundation for all sub-agents.

Pattern: Think (best free model) → Act (Python tools) → Log (Supabase) → Return
- Uses model_router to pick Groq/Gemini/Ollama based on task
- Each subclass overrides: name, system_prompt, and _act()
- _act() receives the plan and executes real-world actions
"""
import logging
from datetime import datetime, timezone

from tools.groq_client import chat as groq_chat
from tools.model_router import choose_model, GROQ_MODEL

logger = logging.getLogger(__name__)


class BaseAgent:
    name: str = "base"
    system_prompt: str = "You are a helpful AI agent. Complete the task concisely."
    groq_model: str = GROQ_MODEL
    max_tokens: int = 2048

    async def run(self, task: str) -> str:
        """
        Main entry point. Think → Act → Log → Return.

        Args:
            task: Natural language task description

        Returns:
            Result summary string
        """
        logger.info(f"[{self.name}] Starting: {task[:80]}")
        started = datetime.now(timezone.utc).isoformat()

        # ── Report task start to NEXUS Platform ──────────────────
        try:
            from tools.platform_reporter import report_task_started
            report_task_started(task, self.name)
        except Exception:
            pass
        # ─────────────────────────────────────────────────────────

        try:
            # Step 1: Think — pick best free model for this task
            model_choice = choose_model(task)
            logger.debug(f"[{self.name}] Using model: {model_choice}")

            if model_choice == "gemini":
                try:
                    from tools.gemini_client import chat as gemini_chat
                    plan = gemini_chat(
                        prompt=task,
                        system=self.system_prompt,
                        max_tokens=self.max_tokens,
                    )
                except Exception:
                    # Fallback to Groq
                    plan = groq_chat(
                        prompt=task,
                        system=self.system_prompt,
                        model=self.groq_model,
                        max_tokens=self.max_tokens,
                        temperature=0.4,
                    )
            elif model_choice == "ollama":
                try:
                    from tools.ollama_client import chat as ollama_chat
                    plan = ollama_chat(
                        prompt=task,
                        system=self.system_prompt,
                        max_tokens=self.max_tokens,
                    )
                except Exception:
                    plan = groq_chat(
                        prompt=task,
                        system=self.system_prompt,
                        model=self.groq_model,
                        max_tokens=self.max_tokens,
                        temperature=0.4,
                    )
            else:
                # Default: Groq
                plan = groq_chat(
                    prompt=task,
                    system=self.system_prompt,
                    model=self.groq_model,
                    max_tokens=self.max_tokens,
                    temperature=0.4,
                )

            # Step 2: Act — subclasses execute tools based on the plan
            result = await self._act(task, plan)

            # Step 3: Log to Supabase + local file
            await self._log(task, result, started)

            logger.info(f"[{self.name}] Done: {result[:100]}")
            # ── Report task completion to NEXUS Platform ──────────
            try:
                from tools.platform_reporter import report_task_done
                report_task_done(task, result[:120], self.name)
            except Exception:
                pass
            # ─────────────────────────────────────────────────────
            return result

        except Exception as exc:
            error_msg = f"[{self.name}] FAILED: {exc}"
            logger.error(error_msg, exc_info=True)
            await self._log(task, f"ERROR: {exc}", started, is_error=True)
            return error_msg

    async def _act(self, task: str, plan: str) -> str:
        """
        Override in subclasses to execute tools.
        Default: return the Groq plan as-is (pure reasoning agent).
        """
        return plan

    async def _log(self, task: str, result: str, started: str, is_error: bool = False) -> None:
        """Log event to Supabase + local fallback."""
        try:
            from tools.agent_logger import log_event
            await log_event(
                agent_name=self.name,
                event_type="error" if is_error else "task",
                title=task[:120],
                details=result[:500],
            )
        except Exception as e:
            logger.warning(f"[{self.name}] Could not log to Supabase: {e}")

    def status(self) -> dict:
        """Return agent metadata for Curios dashboard."""
        return {
            "name": self.name,
            "model": self.groq_model,
            "description": self.__doc__ or "",
        }
