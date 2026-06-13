from enum import Enum
from dataclasses import dataclass, field
from datetime import date, datetime, timezone, timedelta
from typing import Optional, Dict, List
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
    reward_tiers: Optional[Dict[int, str]] = None
    max_streak_days: int = 7

    def get_reward_for_streak(self, streak_days: int) -> str:
        if self.reward_tiers and streak_days > 0:
            effective_day = min(streak_days, self.max_streak_days)
            for day in sorted(self.reward_tiers.keys(), reverse=True):
                if effective_day >= day:
                    return self.reward_tiers[day]
        return self.reward


DEFAULT_REWARD_TIERS: Dict[TaskType, Dict[int, str]] = {
    TaskType.LOGIN: {
        1: "100金币",
        3: "300金币",
        7: "800金币 + 稀有道具",
    },
    TaskType.KILL: {
        1: "500经验",
        3: "1500经验",
        7: "4000经验 + 双倍经验卡",
    },
    TaskType.RECHARGE: {
        1: "VIP经验x10",
        3: "VIP经验x30",
        7: "VIP经验x80 + 专属称号",
    },
}


def get_today_in_tz(tz_name: str) -> date:
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = timezone.utc
    return datetime.now(tz).date()


def get_yesterday_in_tz(tz_name: str) -> date:
    return get_today_in_tz(tz_name) - timedelta(days=1)


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
    streak_days: int = 0
    last_completed_date: Optional[date] = None

    def update_progress(self, amount: int = 1) -> bool:
        if self.completed:
            return False
        self.progress = min(self.progress + amount, self.target)
        if self.progress >= self.target:
            self.completed = True
            self._update_streak_on_complete()
        return True

    def _update_streak_on_complete(self) -> None:
        today = self._today()
        yesterday = get_yesterday_in_tz(self.timezone)

        if self.last_completed_date == today:
            return

        if self.last_completed_date == yesterday:
            self.streak_days += 1
        elif self.last_completed_date is None or self.last_completed_date < yesterday:
            self.streak_days = 1

        self.last_completed_date = today

    def _reset_streak_if_broken(self) -> None:
        if self.last_completed_date is None:
            return

        today = self._today()
        yesterday = get_yesterday_in_tz(self.timezone)

        if self.last_completed_date < yesterday and self.reset_date < today:
            self.streak_days = 0

    def claim_reward(self) -> bool:
        if self.completed and not self.claimed:
            self.claimed = True
            return True
        return False

    def get_current_reward(self, config: TaskConfig) -> str:
        return config.get_reward_for_streak(self.streak_days)

    def _today(self) -> date:
        return get_today_in_tz(self.timezone)

    def reset(self) -> None:
        self._reset_streak_if_broken()
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
            "streak_days": self.streak_days,
            "last_completed_date": self.last_completed_date.isoformat() if self.last_completed_date else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DailyTask":
        last_completed = data.get("last_completed_date")
        return cls(
            user_id=data["user_id"],
            task_type=TaskType(data["task_type"]),
            progress=data.get("progress", 0),
            target=data.get("target", 1),
            completed=data.get("completed", False),
            claimed=data.get("claimed", False),
            reset_date=date.fromisoformat(data.get("reset_date", date.today().isoformat())),
            timezone=data.get("timezone", "UTC"),
            streak_days=data.get("streak_days", 0),
            last_completed_date=date.fromisoformat(last_completed) if last_completed else None,
        )
