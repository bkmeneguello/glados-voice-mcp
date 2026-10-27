__all__ = ["VoiceEngine", "split_text"]


def __getattr__(name):
    # Lazy so that light importers (the MCP proxy) don't load onnxruntime and the models.
    if name in __all__:
        from . import engine

        return getattr(engine, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
