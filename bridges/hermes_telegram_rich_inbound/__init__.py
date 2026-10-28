"""Hermes directory-plugin entrypoint (installed outside the core checkout)."""
from .plugin import register

__all__ = ['register']
