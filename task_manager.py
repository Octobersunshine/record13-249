import json
import os
import threading
from datetime import date, datetime, timezone
from typing import Dict, List, Optional, Set, Tuple
from zoneinfo import ZoneInfo
from models import DailyTask, TaskType, TaskConfig, validate_timezone, get_today_in_tz, DEFAULT_REWARD_TIERS


DEFAULT_TASK_CONFIGS: List[TaskConfig] = [
    TaskConfig(
        task_type=TaskType.LOGIN,
        name="每日登录",
        target=1,
        reward="100金币",
        reward_tiers=DEFAULT_REWARD_TIERS[TaskType.LOGIN],
    ),
    TaskConfig(
        task_type=TaskType.KILL,
        name="击杀怪物",
        target=50,
        reward="500经验",
        reward_tiers=DEFAULT_REWARD_TIERS[TaskType.KILL],
    ),
    TaskConfig(
        task_type=TaskType.RECHARGE,
        name="每日充值",
        target=1,
        reward="VIP经验x10",
        reward_tiers=DEFAULT_REWARD_TIERS[TaskType.RECHARGE],
    ),
]


class TaskManager:
    def __init__(self, data_file: str = "tasks_data.json"):
        self.data_file = data_file
        self._lock = threading.RLock()
        self._tasks: Dict[str, Dict[TaskType, DailyTask]] = {}
        self._task_configs: Dict[TaskType, TaskConfig] = {
            tc.task_type: tc for tc in DEFAULT_TASK_CONFIGS
        }
        self._user_timezones: Dict[str, str] = {}
        self._load()

    def _get_storage_key(self, user_id: str, task_type: TaskType) -> str:
        return f"{user_id}:{task_type.value}"

    def _load(self) -> None:
        if not os.path.exists(self.data_file):
            return
        try:
            with open(self.data_file, "r", encoding="utf-8") as f:
                raw = json.load(f)
            for key, data in raw.items():
                task = DailyTask.from_dict(data)
                user_id, task_type_str = key.rsplit(":", 1)
                task_type = TaskType(task_type_str)
                if user_id not in self._tasks:
                    self._tasks[user_id] = {}
                self._tasks[user_id][task_type] = task
                tz = data.get("timezone", "UTC")
                self._user_timezones[user_id] = tz
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            print(f"加载任务数据失败: {e}")

    def _save(self) -> None:
        raw = {}
        for user_id, user_tasks in self._tasks.items():
            for task_type, task in user_tasks.items():
                key = self._get_storage_key(user_id, task_type)
                raw[key] = task.to_dict()
        with open(self.data_file, "w", encoding="utf-8") as f:
            json.dump(raw, f, ensure_ascii=False, indent=2)

    def _ensure_task(self, user_id: str, task_type: TaskType) -> DailyTask:
        if user_id not in self._tasks:
            self._tasks[user_id] = {}
        if task_type not in self._tasks[user_id]:
            config = self._task_configs[task_type]
            tz = self._user_timezones.get(user_id, "UTC")
            self._tasks[user_id][task_type] = DailyTask(
                user_id=user_id,
                task_type=task_type,
                target=config.target,
                timezone=tz,
            )
        return self._tasks[user_id][task_type]

    def _sync_timezone_to_tasks(self, user_id: str) -> None:
        tz = self._user_timezones.get(user_id, "UTC")
        if user_id in self._tasks:
            for task in self._tasks[user_id].values():
                if task.timezone != tz:
                    task.timezone = tz

    def set_user_timezone(self, user_id: str, tz_name: str) -> bool:
        if not validate_timezone(tz_name):
            return False
        with self._lock:
            self._user_timezones[user_id] = tz_name
            self._sync_timezone_to_tasks(user_id)
            self._save()
            return True

    def get_user_timezone(self, user_id: str) -> str:
        return self._user_timezones.get(user_id, "UTC")

    def get_users_in_timezone(self, tz_name: str) -> List[str]:
        with self._lock:
            return [
                uid for uid, tz in self._user_timezones.items()
                if tz == tz_name
            ]

    def get_all_user_timezones(self) -> Dict[str, str]:
        with self._lock:
            return dict(self._user_timezones)

    def get_all_timezone_groups(self) -> Dict[str, List[str]]:
        with self._lock:
            groups: Dict[str, List[str]] = {}
            for uid, tz in self._user_timezones.items():
                groups.setdefault(tz, []).append(uid)
            return groups

    def update_task_progress(self, user_id: str, task_type: TaskType, amount: int = 1) -> Optional[DailyTask]:
        with self._lock:
            task = self._ensure_task(user_id, task_type)
            if task.needs_reset():
                task.reset()
            task.update_progress(amount)
            self._save()
            return task

    def login(self, user_id: str) -> DailyTask:
        return self.update_task_progress(user_id, TaskType.LOGIN, 1)

    def kill_monsters(self, user_id: str, count: int = 1) -> DailyTask:
        return self.update_task_progress(user_id, TaskType.KILL, count)

    def recharge(self, user_id: str) -> DailyTask:
        return self.update_task_progress(user_id, TaskType.RECHARGE, 1)

    def get_user_tasks(self, user_id: str) -> Dict[TaskType, DailyTask]:
        with self._lock:
            if user_id not in self._tasks:
                self._tasks[user_id] = {}
            for task_type in self._task_configs:
                self._ensure_task(user_id, task_type)
            result = {}
            for task_type, task in self._tasks[user_id].items():
                if task.needs_reset():
                    task.reset()
                result[task_type] = task
            self._save()
            return result

    def get_task(self, user_id: str, task_type: TaskType) -> Optional[DailyTask]:
        with self._lock:
            self._ensure_task(user_id, task_type)
            task = self._tasks[user_id][task_type]
            if task.needs_reset():
                task.reset()
                self._save()
            return task

    def claim_reward(self, user_id: str, task_type: TaskType) -> Tuple[bool, str]:
        with self._lock:
            task = self.get_task(user_id, task_type)
            if task and task.claim_reward():
                config = self._task_configs[task_type]
                reward = task.get_current_reward(config)
                self._save()
                return True, reward
            return False, ""

    def get_streak_days(self, user_id: str, task_type: TaskType) -> int:
        with self._lock:
            task = self.get_task(user_id, task_type)
            return task.streak_days if task else 0

    def get_current_reward(self, user_id: str, task_type: TaskType) -> str:
        with self._lock:
            task = self.get_task(user_id, task_type)
            if not task:
                return ""
            config = self._task_configs[task_type]
            return task.get_current_reward(config)

    def reset_streak(self, user_id: str, task_type: TaskType) -> None:
        with self._lock:
            task = self.get_task(user_id, task_type)
            if task:
                task.streak_days = 0
                task.last_completed_date = None
                self._save()

    def reset_user_tasks(self, user_id: str) -> None:
        with self._lock:
            if user_id in self._tasks:
                for task in self._tasks[user_id].values():
                    task.reset()
                self._save()

    def reset_all_tasks(self) -> int:
        with self._lock:
            count = 0
            for user_id in list(self._tasks.keys()):
                for task in self._tasks[user_id].values():
                    if task.needs_reset():
                        task.reset()
                        count += 1
            self._save()
            return count

    def reset_tasks_for_timezone(self, tz_name: str) -> int:
        with self._lock:
            count = 0
            for user_id in self.get_users_in_timezone(tz_name):
                if user_id in self._tasks:
                    for task in self._tasks[user_id].values():
                        if task.needs_reset():
                            task.reset()
                            count += 1
            if count > 0:
                self._save()
            return count

    def force_reset_all(self) -> int:
        with self._lock:
            count = 0
            for user_id in list(self._tasks.keys()):
                for task in self._tasks[user_id].values():
                    task.reset()
                    count += 1
            self._save()
            return count

    def set_task_config(self, config: TaskConfig) -> None:
        with self._lock:
            self._task_configs[config.task_type] = config

    def get_task_configs(self) -> Dict[TaskType, TaskConfig]:
        return dict(self._task_configs)
