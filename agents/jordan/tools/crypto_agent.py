"""
CryptoAgent — On-chain analytics and DeFi opportunities.

Monitors Phantom wallet, DEX activity, token launches.
Uses Alchemy + Moralis + DexScreener + CoinGecko.
"""
import logging

from agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)

_SYSTEM = """\
You are CryptoAgent, a DeFi-native analyst who thinks in on-chain data.

Given crypto data and a task, output:
- MARKET SUMMARY: 2 sentences on current conditions
- TOP OPPORTUNITY: best risk/reward trade right now
- WALLET WATCH: anything notable in Nicholas's Phantom wallet
- DEFI YIELD: best current yield opportunities (>5% APY, low risk)
- ACTION: one specific thing to do with <$50 (Nicholas's budget)

Think like a DeFi degen who actually manages risk.
Solana ecosystem priority — that's where Nicholas's wallet is.
"""


class CryptoAgent(BaseAgent):
    """On-chain analytics, DeFi yields, Phantom wallet monitoring."""

    name = "crypto"
    system_prompt = _SYSTEM
    max_tokens = 1024

    async def _act(self, task: str, plan: str) -> str:
        context = []

        # Get crypto prices
        try:
            from tools.coingecko import get_price
            for coin in ["bitcoin", "ethereum", "solana"]:
                try:
                    price = get_price(coin)
                    if price:
                        context.append(f"{coin.upper()}: ${price:,.2f}")
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"CryptoAgent coingecko failed: {e}")

        # Check DEX for hot tokens
        try:
            from tools.dexscreener import get_trending_pairs
            pairs = get_trending_pairs(chain="solana", limit=3)
            for p in pairs:
                context.append(f"DEX hot: {p.get('baseToken', {}).get('symbol', '?')} "
                                f"({p.get('priceChange', {}).get('h24', 0):+.1f}% 24h)")
        except Exception as e:
            logger.warning(f"CryptoAgent dexscreener failed: {e}")

        if context:
            enriched = f"{task}\n\nLive data:\n" + "\n".join(context)
            try:
                from tools.groq_client import chat
                plan = chat(
                    prompt=enriched,
                    system=self.system_prompt,
                    max_tokens=self.max_tokens,
                    temperature=0.2,
                )
            except Exception:
                pass

        return plan
