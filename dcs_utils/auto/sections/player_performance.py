"""Section 6 — Player Performance."""



from dcs_utils.auto.constants import section_intro
from dcs_utils.common.loader import AnalysisData


def render(data: AnalysisData) -> str:
    return (
        section_intro("player_performance")
        + '<div class="alert alert-secondary mb-0">'
        'TODO - add performance data'
        '</div>'
    )
