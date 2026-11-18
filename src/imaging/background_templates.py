# Match each supplied background to its own ordered podium positions.
# Coordinates use a 1024 x 1024 reference and scale to the image dimensions.
# Slots are ordered left to right, from the rear row to the front row.

from collections.abc import Iterable
from pathlib import Path

from src.core.paths import BACKGROUND_DIR

GROUPS_PER_PAGE = 8
IMAGE_SLOTS_BY_COUNT = {
    1: ((315, 230, 705, 648),),
    2: ((150, 255, 495, 667), (530, 255, 865, 667)),
    3: (
        (112, 260, 362, 703), (390, 260, 635, 703), (665, 260, 910, 703),
    ),
    4: (
        (185, 210, 480, 464), (545, 210, 835, 464),
        (180, 510, 485, 705), (540, 510, 840, 705),
    ),
    5: (
        (118, 205, 356, 448), (397, 205, 633, 448), (673, 205, 911, 448),
        (220, 493, 480, 670), (546, 493, 804, 670),
    ),
    6: (
        (125, 205, 364, 483), (398, 205, 633, 483), (667, 205, 907, 483),
        (130, 528, 364, 734), (402, 528, 630, 734), (670, 528, 902, 734),
    ),
    7: (
        (132, 205, 368, 389), (397, 205, 628, 389), (660, 205, 892, 389),
        (216, 434, 482, 564), (542, 434, 806, 564),
        (177, 609, 477, 739), (548, 609, 844, 739),
    ),
    8: (
        (100, 205, 370, 448), (395, 205, 665, 440), (685, 205, 955, 445),
        (105, 490, 475, 640), (520, 490, 820, 640),
        (100, 700, 370, 835), (395, 700, 665, 835), (685, 700, 955, 835),
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
