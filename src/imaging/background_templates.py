# Match each supplied background to its own ordered podium positions.
# Coordinates use a 1024 x 1024 reference and scale to the image dimensions.
# Slots are ordered left to right, from the rear row to the front row.

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from src.core.paths import BACKGROUND_DIR

GROUPS_PER_PAGE = 8
IMAGE_SLOTS_BY_COUNT = {
    1: ((280, 380, 740, 725),),
    2: (
        (180, 350, 480, 670),
        (544, 350, 844, 670),
    ),
    3: (
        (515, 275, 825, 500),
        (220, 390, 520, 610),
        (510, 550, 830, 720),
    ),
    4: (
        (320, 260, 640, 485),
        (155, 430, 385, 600),
        (600, 420, 895, 605),
        (320, 540, 625, 715),
    ),
    5: (
        (115, 235, 335, 405),
        (390, 225, 610, 395),
        (665, 235, 885, 405),
        (215, 455, 435, 635),
        (530, 455, 750, 635),
    ),
    6: (
        (105, 235, 325, 405),
        (390, 225, 610, 395),
        (665, 235, 885, 405),
        (115, 455, 335, 635),
        (400, 455, 620, 635),
        (680, 455, 900, 635),
    ),
    7: (
        (410, 235, 635, 405),
        (70, 255, 290, 425),
        (695, 275, 915, 445),
        (405, 430, 625, 570),
        (70, 440, 290, 610),
        (725, 490, 945, 660),
        (380, 580, 600, 720),
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

# Header and Mascot positions and sizes per group count (reference canvas
# 1024x1024).
HEADER_SLOTS_BY_COUNT: dict[int, dict[str, Any]] = {
    1: {"pos": (15, 0), "width": 365},
    2: {"pos": (15, 0), "width": 365},
    3: {"pos": (15, 0), "width": 365},
    4: {"pos": (15, 0), "width": 365},
    5: {"pos": (15, 0), "width": 310},
    6: {"pos": (15, 0), "width": 310},
    7: {"pos": (15, 0), "width": 310},
    8: {"pos": (15, 0), "width": 365},
}

MASCOT_SLOTS_BY_COUNT: dict[int, dict[str, Any]] = {
    1: {"pos": (560, 20), "width": 180},
    2: {"pos": (560, 20), "width": 180},
    3: {"pos": (560, 20), "width": 180},
    4: {"pos": (560, 20), "width": 180},
    5: {"pos": (560, 20), "width": 180},
    6: {"pos": (560, 20), "width": 180},
    7: {"pos": (560, 20), "width": 180},
    8: {"pos": (560, 20), "width": 180},
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
