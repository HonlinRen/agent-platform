__all__ = ["build_tools", "get_tools_by_name"]


def __getattr__(name: str):
    if name == "build_tools":
        from rag.tools.registry import build_tools

        return build_tools
    if name == "get_tools_by_name":
        from rag.tools.registry import get_tools_by_name

        return get_tools_by_name
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
