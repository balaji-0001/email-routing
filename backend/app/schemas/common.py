from datetime import datetime, timezone
from typing import Annotated, Generic, TypeVar
from zoneinfo import ZoneInfo

from pydantic import AfterValidator, BaseModel, ConfigDict, PlainSerializer, StringConstraints

T = TypeVar("T")


def _as_utc(value: datetime) -> str:
    """The database keeps naive UTC; the API always says so explicitly."""
    return value.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def _known_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except (KeyError, ValueError, OSError):
        raise ValueError("Choose a time zone from the list.") from None
    return value


UtcDateTime = Annotated[datetime, PlainSerializer(_as_utc, return_type=str)]
Timezone = Annotated[str, StringConstraints(max_length=64), AfterValidator(_known_timezone)]


class Schema(BaseModel):
    """Base for responses built straight from database rows."""

    model_config = ConfigDict(from_attributes=True)


class Envelope(BaseModel, Generic[T]):
    """Every successful response puts its payload under `data`."""

    data: T
