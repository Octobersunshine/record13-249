from enum import Enum
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo


class TaskType(Enum):
    LOGIN = "login"
    KILL = "kill"
    RECHARGE = "recharge"


@dataclass
class TaskConfig:
    task_type: TaskType
    name: str
    target: int
    reward: str


def get_today_in_tz(tz_name: str) -> date:
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = timezone.utc
    return datetime.now(tz).date()


def validate_timezone(tz_name: str) -> bool:
    try:
        ZoneInfo(tz_name)
        return True
    except Exception:
        return False


@dataclass
class DailyTask:
    user_id: str
    task_type: TaskType
    progress: int = 0
    target: int = 1
    completed: bool = False
    claimed: bool = False
    reset_date: date = field(default_factory=date.today)
    timezone: str = "UTC"

    def update_progress(self, amount: int = 1) -> bool:
        if self.completed:
            return False
        self.progress = min(self.progress + amount, self.target)
        if self.progress >= self.target:
            self.completed = True
        return True

    def claim_reward(self) -> bool:
        if self.completed and not self.claimed:
            self.claimed = True
            return True
        return False

    def _today(self) -> date:
        return get_today_in_tz(self.timezone)

    def reset(self) -> None:
        self.progress = 0
        self.completed = False
        self.claimed = False
        self.reset_date = self._today()

    def needs_reset(self) -> bool:
        return self.reset_date != self._today()

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "task_type": self.task_type.value,
            "progress": self.progress,
            "target": self.target,
            "completed": self.completed,
            "claimed": self.claimed,
            "reset_date": self.reset_date.isoformat(),
            "timezone": self.timezone,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DailyTask":
        return cls(
            user_id=data["user_id"],
            task_type=TaskType(data["task_type"]),
            progress=data.get("progress", 0),
            target=data.get("target", 1),
            completed=data.get("completed", False),
            claimed=data.get("claimed", False),
            reset_date=date.fromisoformat(data.get("reset_date", date.today().isoformat())),
            timezone=data.get("timezone", "UTC"),
        )
