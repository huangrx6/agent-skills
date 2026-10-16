"""Keep editable output beside a diagram's .source directory.

Only the opt-in .source convention changes naming. Existing flat inputs retain
their original CLI output paths; explicit -o is handled by each caller.
"""
from __future__ import annotations

import os
from pathlib import Path


def default_output(spec_path: str, extension: str) -> str:
    path = Path(spec_path)
    if path.parent.name == ".source":
        name = (path.name[:-len(".diagram.json")]
                if path.name.endswith(".diagram.json") else path.stem)
        return str(path.parent.parent / (name + extension))
    return os.path.splitext(spec_path)[0] + extension
