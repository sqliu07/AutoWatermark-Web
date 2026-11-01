"""Small display derivatives; full resolution media stays untouched."""

import os
import tempfile
from io import BytesIO

from PIL import Image, ImageOps

from imaging.safety import validate_raster_size

PREVIEW_EDGE = 1280
THUMBNAIL_EDGE = 160
_SUFFIXES = {"preview": ".preview.jpg", "thumbnail": ".thumb.jpg"}
_MAX_PREVIEW_BYTES = 2 * 1024 * 1024


def preview_paths(source_path: str) -> dict[str, str]:
    return {kind: source_path + suffix for kind, suffix in _SUFFIXES.items()}


def preview_source(path: str) -> str | None:
    for suffix in _SUFFIXES.values():
        if path.endswith(suffix):
            return path[:-len(suffix)]
    return None


def create_previews(source_path: str, *, storage_quota_bytes: int | None = None) -> dict[str, str]:
    """Decode once, downsample early, then atomically publish both JPEGs.

    Callers sharing a directory must hold their upload/storage lock. If either
    derivative fails, remove both so a retry cannot display stale content.
    """
    targets = preview_paths(source_path)
    temporary_paths = []
    try:
        with Image.open(source_path, formats=("JPEG", "PNG")) as source:
            validate_raster_size(source.size)
            profile = source.info.get("icc_profile")
            # JPEG thumbnail() uses decoder draft scaling before loading pixels.
            source.thumbnail((PREVIEW_EDGE, PREVIEW_EDGE), Image.Resampling.LANCZOS)
            with ImageOps.exif_transpose(source) as oriented:
                with Image.new("RGB", oriented.size, "white") as preview:
                    if "A" in oriented.getbands():
                        with oriented.getchannel("A") as alpha:
                            preview.paste(oriented, mask=alpha)
                    else:
                        preview.paste(oriented)
                    encoded = {}
                    for kind, edge in (("preview", PREVIEW_EDGE), ("thumbnail", THUMBNAIL_EDGE)):
                        if kind == "thumbnail":
                            preview.thumbnail((edge, edge), Image.Resampling.LANCZOS)
                        buffer = BytesIO()
                        preview.save(buffer, format="JPEG", quality=82, optimize=True,
                                     **({"icc_profile": profile} if profile else {}))
                        if buffer.tell() > _MAX_PREVIEW_BYTES:
                            raise OSError("Preview exceeds the display size budget")
                        encoded[kind] = buffer.getvalue()

        folder = os.path.dirname(source_path) or "."
        if storage_quota_bytes is not None:
            used = 0
            with os.scandir(folder) as entries:
                for entry in entries:
                    try:
                        if entry.is_file(follow_symlinks=False):
                            used += entry.stat(follow_symlinks=False).st_size
                    except FileNotFoundError:
                        pass  # Concurrent retention cleanup.
            if used + sum(map(len, encoded.values())) > storage_quota_bytes:
                raise OSError("No space available for display previews")

        for kind, path in targets.items():
            fd, temporary = tempfile.mkstemp(prefix=".preview_", suffix=".jpg", dir=folder)
            temporary_paths.append(temporary)
            with os.fdopen(fd, "wb") as stream:
                stream.write(encoded[kind])
            os.replace(temporary, path)
        return targets
    except Exception:
        for path in [*temporary_paths, *targets.values()]:
            try:
                os.remove(path)
            except FileNotFoundError:
                pass
        raise
