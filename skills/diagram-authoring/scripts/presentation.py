"""Immutable per-generation typography. Viewing targets live in authoring.py.

No palette/font globals are changed. Presets never remove content or promise
that an arbitrary graph fits a slide; assess the finished artifact separately.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class PresentationContext:
    preset: str = "fit"
    node: float = 16.0
    detail: float = 12.0
    title: float = 24.0
    region: float = 20.0
    padding_x: float = 22.0
    padding_y: float = 24.0
    node_gap: float = 120.0
    rank_gap: float = 120.0
    title_gap: float = 36.0
    card_gap: float = 64.0
    # Labels remain in semantic size classes; no target-dependent truncation.

    def layout_params(self, overrides=None):
        return {"nodeSeparation": self.node_gap, "rankSeparation": self.rank_gap,
                **(overrides or {})}


NAMES = ("fit", "doc-inline", "doc-wide", "slide-16x9", "print-a4-landscape")


def resolve(preset=None):
    if preset is not None and not isinstance(preset, str):
        # Modules are loaded by explicit paths in this skill. Avoid isinstance
        # against duplicate dataclass identities; callers pass the context on.
        if all(hasattr(preset, key) for key in PresentationContext.__dataclass_fields__):
            return preset
        raise ValueError("需要场景名称或 PresentationContext")
    name = preset or "fit"
    if name not in NAMES:
        raise ValueError(f"未知排版场景：{name}")
    if name == "slide-16x9":
        return PresentationContext(name, node=24, detail=20, title=32, region=24,
                                   padding_x=18, padding_y=16, node_gap=90,
                                   rank_gap=90, title_gap=24, card_gap=32)
    if name == "print-a4-landscape":
        return PresentationContext(name, node=18, detail=14, title=26, region=22)
    return PresentationContext(name)


def add_findings(assessment, outcome, issue_class):
    """Target failure is advisory and never feeds the geometry retry loop."""
    for page in assessment["pages"]:
        if page["status"] == "warning":
            outcome.issues.append(issue_class(
                "presentation", False, page["page"],
                f"{assessment['preset']} 下预计最小字号 {page['min_viewing_px']}px，"
                f"低于 {assessment['target']['min_text']}px；已保留全部内容。",
                advice="调整方向、拆成相互对应的视图或改用更大观看场景；不缩字、不删除关系。",
                evidence={"preset": assessment["preset"], **page,
                          "basis": assessment["basis"], "renderVerified": False}))
