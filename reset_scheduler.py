import threading
import logging
from datetime import datetime, date
from typing import Callable, Dict, Optional
from zoneinfo import ZoneInfo

from task_manager import TaskManager


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("DailyResetScheduler")


def _get_tz_today(tz_name: str) -> date:
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("UTC")
    return datetime.now(tz).date()


def _is_tz_past_reset_time(tz_name: str, reset_hour: int, reset_minute: int) -> bool:
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("UTC")
    now_in_tz = datetime.now(tz)
    reset_today = now_in_tz.replace(
        hour=reset_hour, minute=reset_minute, second=0, microsecond=0
    )
    return now_in_tz >= reset_today


class DailyResetScheduler:
    def __init__(
        self,
        task_manager: TaskManager,
        reset_hour: int = 0,
        reset_minute: int = 0,
        on_reset_callback: Optional[Callable[[int], None]] = None,
        check_interval: int = 60,
    ):
        self.task_manager = task_manager
        self.reset_hour = reset_hour
        self.reset_minute = reset_minute
        self.on_reset_callback = on_reset_callback
        self.check_interval = check_interval
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._last_reset_dates: Dict[str, date] = {}

    def _run(self) -> None:
        logger.info(
            "每日重置调度服务已启动（时区感知模式），重置时间: %02d:%02d 各时区本地时间，检查间隔: %ds",
            self.reset_hour,
            self.reset_minute,
            self.check_interval,
        )

        while not self._stop_event.is_set():
            try:
                self._check_and_reset()
            except Exception as e:
                logger.error("时区感知重置检查失败: %s", e, exc_info=True)

            self._stop_event.wait(timeout=self.check_interval)

        logger.info("每日重置调度服务已停止")

    def _check_and_reset(self) -> None:
        tz_groups = self.task_manager.get_all_timezone_groups()
        if not tz_groups:
            return

        total_reset = 0
        for tz_name in tz_groups:
            current_date = _get_tz_today(tz_name)
            last_reset = self._last_reset_dates.get(tz_name)

            already_reset_today = (last_reset is not None and last_reset >= current_date)
            if already_reset_today:
                continue

            past_reset_time = _is_tz_past_reset_time(tz_name, self.reset_hour, self.reset_minute)
            if not past_reset_time:
                continue

            logger.info(
                "时区 %s 已到达重置时间（本地 %02d:%02d，当前日期 %s），开始重置任务",
                tz_name,
                self.reset_hour,
                self.reset_minute,
                current_date.isoformat(),
            )
            count = self.task_manager.reset_tasks_for_timezone(tz_name)
            self._last_reset_dates[tz_name] = current_date
            total_reset += count
            logger.info("时区 %s 重置完成，共重置 %d 个任务", tz_name, count)

        if total_reset > 0 and self.on_reset_callback:
            try:
                self.on_reset_callback(total_reset)
            except Exception as cb_e:
                logger.error("重置回调执行失败: %s", cb_e)

        active_tzs = set(tz_groups.keys())
        self._last_reset_dates = {
            tz: dt for tz, dt in self._last_reset_dates.items()
            if tz in active_tzs
        }

    def start(self) -> None:
        if self._running:
            logger.warning("调度服务已在运行中")
            return
        self._stop_event.clear()
        self._last_reset_dates.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="DailyResetThread")
        self._thread.start()
        self._running = True

    def stop(self) -> None:
        if not self._running:
            return
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=10)
        self._running = False
        logger.info("调度服务已停止")

    @property
    def is_running(self) -> bool:
        return self._running

    def trigger_manual_reset(self) -> int:
        logger.info("手动触发任务重置")
        count = self.task_manager.reset_all_tasks()
        logger.info("手动重置完成，共重置 %d 个任务", count)
        if self.on_reset_callback:
            try:
                self.on_reset_callback(count)
            except Exception as cb_e:
                logger.error("重置回调执行失败: %s", cb_e)
        return count

    def trigger_timezone_reset(self, tz_name: str) -> int:
        logger.info("手动触发时区 %s 任务重置", tz_name)
        count = self.task_manager.reset_tasks_for_timezone(tz_name)
        logger.info("时区 %s 手动重置完成，共重置 %d 个任务", tz_name, count)
        if count > 0 and self.on_reset_callback:
            try:
                self.on_reset_callback(count)
            except Exception as cb_e:
                logger.error("重置回调执行失败: %s", cb_e)
        return count
