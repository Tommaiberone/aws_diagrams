"""
Dynamic discovery of all available node classes across every provider.
Results are cached after the first call.
"""
import importlib
import inspect
from pathlib import Path

from diagrams import Node

_catalog_cache = None


def get_node_catalog() -> dict:
    """Return {provider: {module: [{name, type, icon}]}} for every provider."""
    global _catalog_cache
    if _catalog_cache is not None:
        return _catalog_cache

    diagrams_dir = Path(__file__).parent.parent
    catalog: dict = {}

    for provider_dir in sorted(diagrams_dir.iterdir()):
        if not provider_dir.is_dir():
            continue
        provider = provider_dir.name
        if provider.startswith("_") or provider == "editor":
            continue
        if not (provider_dir / "__init__.py").exists():
            continue

        provider_modules: dict = {}

        for module_file in sorted(provider_dir.glob("*.py")):
            if module_file.name.startswith("_"):
                continue

            module_name = f"diagrams.{provider}.{module_file.stem}"
            try:
                mod = importlib.import_module(module_name)
            except Exception:
                continue

            nodes = []
            for cls_name, cls in inspect.getmembers(mod, inspect.isclass):
                if (
                    issubclass(cls, Node)
                    and cls.__module__ == module_name
                    and not cls_name.startswith("_")
                    and getattr(cls, "_icon", None)
                ):
                    icon_dir = getattr(cls, "_icon_dir", "")
                    # _icon_dir contains "resources/..." but the /api/icons
                    # endpoint already serves from the resources/ root, so strip it.
                    icon_path = f"{icon_dir}/{cls._icon}".lstrip("/")
                    if icon_path.startswith("resources/"):
                        icon_path = icon_path[len("resources/"):]
                    nodes.append(
                        {
                            "name": cls_name,
                            "type": f"{provider}.{module_file.stem}.{cls_name}",
                            "icon": icon_path,
                        }
                    )

            if nodes:
                provider_modules[module_file.stem] = nodes

        if provider_modules:
            catalog[provider] = provider_modules

    _catalog_cache = catalog
    return catalog
