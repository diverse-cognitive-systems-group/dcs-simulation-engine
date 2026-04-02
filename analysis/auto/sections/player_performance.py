"""Section 6 — Player Performance."""



from analysis.auto.constants import section_intro
from analysis.common.loader import AnalysisData


def render(data: AnalysisData) -> str:
    return (
        section_intro("player_performance")
        + '<div class="alert alert-secondary mb-0">'
        'TODO - add performance data'
        '</div>'
    )
