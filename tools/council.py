"""
Council pattern — query 5 AI models in parallel and synthesize the best answer.
Use for high-stakes decisions: contracts, big code refactors, strategy.
Costs more but significantly reduces error rate.
"""
import asyncio
import logging
import os

import anthropic
import httpx

logger = logging.getLogger(__name__)

COUNCIL_MODELS = [
    {"provider": "anthropic", "model": "claude-sonnet-4-6"},
    {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"},
    {"provider": "openrouter", "model": "google/gemini-2.0-flash-exp:free"},
    {"provider": "groq",      "model": "llama-3.3-70b-versatile"},
    {"provider": "openrouter", "model": "deepseek/deepseek-chat"},
]


async def _ask_anthropic(model: str, prompt: str, system: str) -> str:
    client = anthropic.AsyncAnthropic()
    msg = await client.messages.create(
        model=model,
        max_tokens=2048,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text if msg.content else ""


async def _ask_openrouter(model: str, prompt: str, system: str) -> str:
    key = os.getenv("OPENROUTER_API_KEY", "")
    if not key:
        return ""
    messages = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": model, "messages": messages},
        )
        if resp.status_code != 200:
            return ""
        return resp.json()["choices"][0]["message"]["content"]


async def _ask_groq(model: str, prompt: str, system: str) -> str:
    key = os.getenv("GROQ_API_KEY", "")
    if not key:
        return ""
    messages = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": model, "messages": messages, "max_tokens": 2048},
        )
        if resp.status_code != 200:
            return ""
        return resp.json()["choices"][0]["message"]["content"]


async def _ask_one(spec: dict, prompt: str, system: str) -> str:
    try:
        if spec["provider"] == "anthropic":
            return await _ask_anthropic(spec["model"], prompt, system)
        elif spec["provider"] == "openrouter":
            return await _ask_openrouter(spec["model"], prompt, system)
        elif spec["provider"] == "groq":
            return await _ask_groq(spec["model"], prompt, system)
    except Exception as exc:
        logger.warning(f"Council member {spec['model']} failed: {exc}")
    return ""


async def deliberate(
    question: str,
    system: str = "Du er en ekspert rådgiver. Gi et presist og godt begrunnet svar.",
    models: list[dict] | None = None,
) -> str:
    """
    Ask multiple AI models the same question in parallel, then synthesize.

    Args:
        question: The question or task to deliberate on
        system: System prompt for all models
        models: Custom model list (default: COUNCIL_MODELS)

    Returns:
        Synthesized best answer
    """
    council = models or COUNCIL_MODELS
    tasks = [_ask_one(spec, question, system) for spec in council]
    responses = await asyncio.gather(*tasks)

    valid = [r.strip() for r in responses if r.strip()]
    if not valid:
        raise RuntimeError("All council members failed to respond.")

    logger.info(f"Council got {len(valid)}/{len(council)} responses")

    # If only one responded, return it directly
    if len(valid) == 1:
        return valid[0]

    # Synthesize with Claude Sonnet
    synthesis_prompt = (
        f"Original question: {question}\n\n"
        + "\n\n".join(f"--- Model {i+1} ---\n{r}" for i, r in enumerate(valid))
        + "\n\n---\nSynthesize the best, most accurate answer from the responses above. "
        "Keep the best insights from each. Be concise."
    )
    try:
        return await _ask_anthropic("claude-sonnet-4-6", synthesis_prompt, "You synthesize expert opinions.")
    except Exception:
        return valid[0]  # Return first valid response as fallback
