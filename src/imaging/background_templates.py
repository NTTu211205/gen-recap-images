# Match each supplied background to its own ordered podium positions.
# Coordinates use a 1024 x 1024 reference and scale to the image dimensions.
# Slots are ordered left to right, from the rear row to the front row.

from collections.abc import Iterable
from pathlib import Path

from src.core.paths import BACKGROUND_DIR

GROUPS_PER_PAGE = 8
IMAGE_SLOTS_BY_COUNT = {
    1: ((250, 280, 850, 750),),
    2: ((530, 220, 960, 580), (50, 380, 480, 715)),
    3: (
        (540, 300, 840, 525),
        (230, 420, 560, 620),
        (535, 580, 860, 735),
    ),
    4: (
        (320, 260, 640, 485),
        (160, 430, 390, 595),
        (595, 410, 900, 600),
        (320, 530, 630, 725),
    ),
    5: (
        (660, 165, 995, 410), (310, 255, 605, 480),
        (20, 360, 300, 590), (615, 490, 950, 730), (320, 680, 600, 910),
    ),
    6: (
        (665, 165, 995, 405), (295, 255, 595, 475), (20, 350, 285, 580),
        (600, 460, 920, 675), (20, 625, 285, 755), (430, 720, 780, 930),
    ),
    7: (
        (660, 40, 980, 220),
        (20, 220, 325, 370),
        (330, 180, 600, 380),
        (630, 280, 970, 475),
        (40, 420, 350, 595),
        (380, 500, 625, 660),
        (710, 515, 950, 660),
    ),
    8: (
        (310, 180, 530, 350),
        (655, 175, 875, 345),
        (70, 300, 305, 470),
        (420, 390, 650, 500),
        (715, 385, 915, 520),
        (130, 510, 370, 630),
        (380, 560, 620, 720),
        (655, 560, 905, 660),
    ),
}


def background_for_groups(count: int) -> Path:
    """Choose by display-group count, not by number of product codes."""
    if count not in IMAGE_SLOTS_BY_COUNT:
        raise ValueError(
            f"A recap page must contain 1-{GROUPS_PER_PAGE} groups"
        )
    return BACKGROUND_DIR / f"mwg-background-recap-{count}.png"


def require_backgrounds(counts: Iterable[int]) -> None:
    """Fail before generating assets when a required template is missing."""
    for count in dict.fromkeys(counts):
        path = background_for_groups(count)
        if not path.is_file():
            raise FileNotFoundError(f"Recap background not found: {path}")
