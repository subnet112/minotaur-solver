"""Shared token metadata and unit conversion helpers."""
from __future__ import annotations
TOKEN_DECIMALS = {'0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2': 18, '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48': 6, '0x2260fac5e5542a773aa44fbcfedf7c193bc2c599': 8, '0x6b175474e89094c44da98b954eedeac495271d0f': 18, '0xdac17f958d2ee523a2206206994597c13d831ec7': 6}

def get_decimals(token_address):
    """Return token decimals, defaulting to 18 for unknown assets."""
    return TOKEN_DECIMALS.get(token_address.lower(), 18)

def to_human(raw_amount, decimals):
    """Convert an integer token amount to its decimal form."""
    if decimals == 0:
        return float(raw_amount)
    return raw_amount / 10 ** decimals

def to_raw(human_amount, decimals):
    """Convert a decimal token amount to its raw integer form."""
    return int(human_amount * 10 ** decimals)