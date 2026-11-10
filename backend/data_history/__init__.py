"""Versioned history of the app's fetched and generated data, with approval of suspicious refreshes. See store.py for the storage and the scope names;
service.py (imported where needed, it depends on the app's models) has baseline / restore / approve."""

from . import diff, guard, store
from .store import HeldForApproval, acting_as, current_actor

# Snapshot keys that are datasets worth a history. The Comtrade / World Bank / FRED keys are refetchable caches and stay out.
VERSIONED_PREFIXES = ('custom_', 'usa_')
VERSIONED_KEYS = ('la_mayorista', 'corabastos')


def is_versioned_snapshot(source: str) -> bool:
    return source in VERSIONED_KEYS or source.startswith(VERSIONED_PREFIXES)


def snapshot_scope(source: str) -> str:
    return f'snapshot:{source}'


def market_size_scope(kind: str) -> str:
    return f'market_size:{kind}'


def held_message(error: HeldForApproval) -> str:
    return str(error)


__all__ = ['HeldForApproval', 'acting_as', 'current_actor', 'diff', 'guard', 'store', 'is_versioned_snapshot', 'snapshot_scope', 'market_size_scope', 'held_message']
