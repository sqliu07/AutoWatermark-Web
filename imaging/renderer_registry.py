from __future__ import annotations

from typing import Dict, Type

from imaging.renderer_base import LayoutRenderer


_REGISTRY: Dict[str, Type[LayoutRenderer]] = {}


def register_renderer(layout_name: str, renderer_class: Type[LayoutRenderer]) -> None:
    _REGISTRY[layout_name] = renderer_class


def get_renderer(layout_name: str) -> LayoutRenderer:
    cls = _REGISTRY.get(layout_name)
    if cls is None:
        raise ValueError(f"Unknown layout: {layout_name}")
    return cls()


def _auto_register():
    from imaging.renderer_split_lr import SplitLRRenderer
    from imaging.renderer_center_stack import CenterStackRenderer
    from imaging.renderer_film_frame import FilmFrameRenderer

    register_renderer("split_lr", SplitLRRenderer)
    register_renderer("center_stack", CenterStackRenderer)
    register_renderer("film_frame", FilmFrameRenderer)


_auto_register()
