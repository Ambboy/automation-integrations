"""Hermes-native entry point; no imports from Hermes internals or transport adapters."""
from .bridge import Bridge


def register(ctx):
    if not ctx.get_config("enabled", False):
        return
    bridge = Bridge(
        endpoint=ctx.get_config("endpoint", "http://127.0.0.1:8787"),
        token_file=ctx.get_config("token_file"),
        state_dir=ctx.get_config("state_dir"),
        profile=ctx.profile_name,
        origin_contract=ctx.get_config("origin_contract", "unavailable"),
        topic_icons=ctx.get_config("topic_icons", False),
        voice_reply=ctx.get_config("voice_reply", True),
    )
    # Own cleanup before starting background work. No process-global environment changes.
    ctx.on_unload(bridge.close)
    ctx.register_hook("pre_llm_call", bridge.before)
    ctx.register_hook("post_llm_call", bridge.after)
    bridge.start()
