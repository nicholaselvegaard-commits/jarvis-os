"""
Phantom wallet monitor — track Solana wallet via Alchemy + Solana RPC.

Usage:
    from tools.phantom_wallet import get_balance, get_recent_transactions, get_token_holdings

Config:
    PHANTOM_WALLET_ADDRESS in .env (set by Nicholas)
    ALCHEMY_API_KEY in .env
    SOLANA_RPC_URL in .env (default: https://api.mainnet-beta.solana.com)
"""
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

SOLANA_RPC_URL = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
ALCHEMY_API_KEY = os.getenv("ALCHEMY_API_KEY", "")
PHANTOM_ADDRESS = os.getenv("PHANTOM_WALLET_ADDRESS", "")

# Alchemy Solana RPC endpoint (higher rate limits than public)
ALCHEMY_RPC = f"https://solana-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}" if ALCHEMY_API_KEY else SOLANA_RPC_URL


def _rpc(method: str, params: list) -> dict:
    """Make a Solana JSON-RPC call."""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params,
    }
    with httpx.Client(timeout=15) as client:
        resp = client.post(ALCHEMY_RPC, json=payload)
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            raise ValueError(f"RPC error: {data['error']}")
        return data.get("result", {})


def get_balance(address: str | None = None) -> dict:
    """
    Get SOL balance for the Phantom wallet.

    Returns:
        {"address": str, "sol": float, "lamports": int}
    """
    addr = address or PHANTOM_ADDRESS
    if not addr:
        return {"error": "No wallet address configured. Set PHANTOM_WALLET_ADDRESS in .env or pass address."}

    try:
        result = _rpc("getBalance", [addr])
        lamports = result.get("value", 0)
        sol = lamports / 1_000_000_000
        return {"address": addr, "sol": round(sol, 6), "lamports": lamports}
    except Exception as exc:
        logger.error(f"phantom_wallet.get_balance failed: {exc}")
        return {"error": str(exc)}


def get_token_holdings(address: str | None = None) -> list[dict]:
    """
    Get all SPL token holdings (not SOL) for the wallet.

    Returns list of:
        {"mint": str, "amount": float, "decimals": int, "symbol": str | None}
    """
    addr = address or PHANTOM_ADDRESS
    if not addr:
        return [{"error": "No wallet address configured."}]

    try:
        result = _rpc("getTokenAccountsByOwner", [
            addr,
            {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},
            {"encoding": "jsonParsed"},
        ])
        accounts = result.get("value", [])
        holdings = []
        for account in accounts:
            info = account.get("account", {}).get("data", {}).get("parsed", {}).get("info", {})
            token_amount = info.get("tokenAmount", {})
            amount = float(token_amount.get("uiAmount", 0) or 0)
            if amount > 0:
                holdings.append({
                    "mint": info.get("mint", ""),
                    "amount": amount,
                    "decimals": token_amount.get("decimals", 0),
                })
        return holdings
    except Exception as exc:
        logger.error(f"phantom_wallet.get_token_holdings failed: {exc}")
        return [{"error": str(exc)}]


def get_recent_transactions(address: str | None = None, limit: int = 10) -> list[dict]:
    """
    Get recent transaction signatures for the wallet.

    Returns list of:
        {"signature": str, "slot": int, "block_time": int | None, "err": Any}
    """
    addr = address or PHANTOM_ADDRESS
    if not addr:
        return [{"error": "No wallet address configured."}]

    try:
        result = _rpc("getSignaturesForAddress", [addr, {"limit": limit}])
        if not isinstance(result, list):
            return []
        return [
            {
                "signature": tx.get("signature"),
                "slot": tx.get("slot"),
                "block_time": tx.get("blockTime"),
                "err": tx.get("err"),
            }
            for tx in result
        ]
    except Exception as exc:
        logger.error(f"phantom_wallet.get_recent_transactions failed: {exc}")
        return [{"error": str(exc)}]


def get_wallet_summary(address: str | None = None) -> dict:
    """
    Full wallet summary: SOL balance + token count + recent activity.

    Returns:
        {"sol": float, "tokens": int, "recent_txs": int, "last_activity": int | None, "address": str}
    """
    addr = address or PHANTOM_ADDRESS
    balance = get_balance(addr)
    tokens = get_token_holdings(addr)
    txs = get_recent_transactions(addr, limit=5)

    last_activity = None
    if txs and not txs[0].get("error"):
        last_activity = txs[0].get("block_time")

    return {
        "address": addr,
        "sol": balance.get("sol", 0),
        "tokens": len([t for t in tokens if not t.get("error")]),
        "recent_txs": len([t for t in txs if not t.get("error")]),
        "last_activity_unix": last_activity,
        "error": balance.get("error"),
    }
