import threading
import time
import logging
from datetime import datetime, timedelta
from typing import Callable, Optional

from task_manager import TaskManager


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("DailyResetScheduler")


class DailyResetScheduler:
    def __init__(
        self,
        task_manager: TaskManager,
        reset_hour: int = 0,
        reset_minute: int = 0,
        on_reset_callback: Optional[Callable[[int], None]] = None,
    ):
        self.task_manager = task_manager
        self.reset_hour = reset_hour
        self.reset_minute = reset_minute
        self.on_reset_callback = on_reset_callback
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._running = False

    def _get_next_reset_time(self) -> datetime:
        now = datetime.now()
        next_reset = now.replace(
            hour=self.reset_hour,
            minute=self.reset_minute,
            second=0,
            microsecond=0,
        )
        if next_reset <= now:
            next_reset += timedelta(days=1)
        return next_reset

    def _sleep_until(self, target_time: datetime) -> bool:
        while not self._stop_event.is_set():
            now = datetime.now()
            remaining = (target_time - now).total_seconds()
            if remaining <= 0:
                return True
            sleep_time = min(remaining, 60)
            self._stop_event.wait(timeout=sleep_time)
        return False

    def _run(self) -> None:
        logger.info(
            "每日重置调度服务已启动，重置时间: %02d:%02d",
            self.reset_hour,
            self.reset_minute,
        )
        while not self._stop_event.is_set():
            next_reset = self._get_next_reset_time()
            logger.info("下一次重置时间: %s", next_reset.strftime("%Y-%m-%d %H:%M:%S"))

            if not self._sleep_until(next_reset):
                break

            try:
                reset_count = self.task_manager.reset_all_tasks()
                logger.info("每日任务重置完成，共重置 %d 个任务", reset_count)
                if self.on_reset_callback:
                    try:
                        self.on_reset_callback(reset_count)
                    except Exception as cb_e:
                        logger.error("重置回调执行失败: %s", cb_e)
            except Exception as e:
                logger.error("每日任务重置失败: %s", e, exc_info=True)

            time.sleep(1)

        logger.info("每日重置调度服务已停止")

    def start(self) -> None:
        if self._running:
            logger.warning("调度服务已在运行中")
            return
        self._stop_event.clear()
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
