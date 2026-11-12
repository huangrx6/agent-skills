"""email-composer 的实现包：内容规格 → HTML / 纯文本 / Markdown / .eml。

`scripts/render.py`、`scripts/validate.py`、`scripts/template.py` 是三个薄 CLI，
实际逻辑都在这里，便于回归测试按模块导入。
"""

from __future__ import annotations

from pathlib import Path

# .../skills/email-composer/scripts/email_composer/__init__.py
SKILL_ROOT = Path(__file__).resolve().parents[2]
ASSETS = SKILL_ROOT / "assets"
STYLES = ASSETS / "styles"
