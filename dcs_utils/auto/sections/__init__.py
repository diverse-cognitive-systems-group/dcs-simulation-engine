"""Auto-analysis section modules.

Each module exposes a single function:

    def render(data: AnalysisData) -> str

that returns a complete HTML fragment (without the wrapping <section> tag —
that is added by auto/__init__.py).
"""
