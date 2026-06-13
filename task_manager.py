import json
import os
import threading
from datetime import date
from typing import Dict, List, Optional
from models import DailyTask, TaskType, TaskConfig


DEFAULT_TASK_CONFIGS: List[TaskConfig] = [
    TaskConfig(task_type=TaskType.LOGIN, name="每日登录", target=1, reward="100金币"),
    TaskConfig(task_type=TaskType.KILL, name="击杀怪物", target=50, reward="500经验"),
    TaskConfig(task_type=TaskType.RECHARGE, name="每日充值", target=1, reward="VIP经验x10"),
]


class TaskManager:
    def __init__(self, data_file: str = "tasks_data.json"):
        self.data_file = data_file
        self._lock = threading.RLock()
        self._tasks: Dict[str, Dict[TaskType, DailyTask]] = {}
        self._task_configs: Dict[TaskType, TaskConfig] = {
            tc.task_type: tc for tc in DEFAULT_TASK_CONFIGS
        }
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
            self._tasks[user_id][task_type] = DailyTask(
                user_id=user_id,
                task_type=task_type,
                target=config.target,
            )
        return self._tasks[user_id][task_type]

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

    def claim_reward(self, user_id: str, task_type: TaskType) -> bool:
        with self._lock:
            task = self.get_task(user_id, task_type)
            if task and task.claim_reward():
                self._save()
                return True
            return False

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
