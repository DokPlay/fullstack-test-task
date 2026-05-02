from __future__ import annotations

from typing import Annotated

from fastapi import Query

from src.core.pagination import DEFAULT_PAGE_LIMIT, MAX_PAGE_LIMIT

PageOffset = Annotated[
    int,
    Query(
        ge=0,
        description="Number of items to skip before returning the current page.",
    ),
]
PageLimit = Annotated[
    int,
    Query(
        ge=1,
        le=MAX_PAGE_LIMIT,
        description="Maximum number of items returned in one response.",
    ),
]
