import os
import json
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo
from models import TaskType, DailyTask, TaskConfig, get_today_in_tz, validate_timezone
from task_manager import TaskManager


class TestTaskModels(unittest.TestCase):
    def test_task_type_enum(self):
        self.assertEqual(TaskType.LOGIN.value, "login")
        self.assertEqual(TaskType.KILL.value, "kill")
        self.assertEqual(TaskType.RECHARGE.value, "recharge")

    def test_daily_task_update_progress(self):
        task = DailyTask(user_id="u1", task_type=TaskType.KILL, target=10)
        self.assertEqual(task.progress, 0)
        self.assertFalse(task.completed)

        result = task.update_progress(5)
        self.assertTrue(result)
        self.assertEqual(task.progress, 5)
        self.assertFalse(task.completed)

        result = task.update_progress(5)
        self.assertTrue(result)
        self.assertEqual(task.progress, 10)
        self.assertTrue(task.completed)

        result = task.update_progress(1)
        self.assertFalse(result)
        self.assertEqual(task.progress, 10)

    def test_daily_task_progress_cap(self):
        task = DailyTask(user_id="u1", task_type=TaskType.KILL, target=10)
        task.update_progress(100)
        self.assertEqual(task.progress, 10)
        self.assertTrue(task.completed)

    def test_daily_task_claim_reward(self):
        task = DailyTask(user_id="u1", task_type=TaskType.LOGIN, target=1)
        self.assertFalse(task.claim_reward())

        task.update_progress(1)
        self.assertTrue(task.claim_reward())
        self.assertTrue(task.claimed)

        self.assertFalse(task.claim_reward())

    def test_daily_task_reset(self):
        task = DailyTask(user_id="u1", task_type=TaskType.KILL, target=10)
        task.update_progress(8)
        task.claim_reward()
        task.reset_date = date.today() - timedelta(days=1)

        task.reset()
        self.assertEqual(task.progress, 0)
        self.assertFalse(task.completed)
        self.assertFalse(task.claimed)
        self.assertEqual(task.reset_date, date.today())

    def test_daily_task_needs_reset(self):
        task = DailyTask(user_id="u1", task_type=TaskType.LOGIN)
        self.assertFalse(task.needs_reset())

        task.reset_date = date.today() - timedelta(days=1)
        self.assertTrue(task.needs_reset())

    def test_daily_task_serialization(self):
        task = DailyTask(
            user_id="u123",
            task_type=TaskType.RECHARGE,
            progress=1,
            target=1,
            completed=True,
            claimed=False,
            reset_date=date.today(),
            timezone="Asia/Shanghai",
        )
        data = task.to_dict()
        self.assertEqual(data["user_id"], "u123")
        self.assertEqual(data["task_type"], "recharge")
        self.assertEqual(data["timezone"], "Asia/Shanghai")

        restored = DailyTask.from_dict(data)
        self.assertEqual(restored.user_id, task.user_id)
        self.assertEqual(restored.task_type, task.task_type)
        self.assertEqual(restored.progress, task.progress)
        self.assertEqual(restored.completed, task.completed)
        self.assertEqual(restored.timezone, "Asia/Shanghai")

    def test_daily_task_default_timezone_is_utc(self):
        task = DailyTask(user_id="u1", task_type=TaskType.LOGIN)
        self.assertEqual(task.timezone, "UTC")

    def test_daily_task_deserialization_missing_timezone(self):
        data = {
            "user_id": "u1",
            "task_type": "login",
            "progress": 0,
            "target": 1,
        }
        task = DailyTask.from_dict(data)
        self.assertEqual(task.timezone, "UTC")


class TestTimezoneHelpers(unittest.TestCase):
    def test_get_today_in_tz_utc(self):
        today = get_today_in_tz("UTC")
        self.assertIsInstance(today, date)

    def test_get_today_in_tz_shanghai(self):
        today = get_today_in_tz("Asia/Shanghai")
        self.assertIsInstance(today, date)

    def test_get_today_in_tz_invalid_falls_back_to_utc(self):
        today = get_today_in_tz("Invalid/Timezone")
        utc_today = get_today_in_tz("UTC")
        self.assertEqual(today, utc_today)

    def test_validate_timezone_valid(self):
        self.assertTrue(validate_timezone("UTC"))
        self.assertTrue(validate_timezone("Asia/Shanghai"))
        self.assertTrue(validate_timezone("America/New_York"))
        self.assertTrue(validate_timezone("Europe/London"))

    def test_validate_timezone_invalid(self):
        self.assertFalse(validate_timezone("Invalid/Zone"))
        self.assertFalse(validate_timezone(""))
        self.assertFalse(validate_timezone("NotATimezone"))


class TestTimezoneAwareReset(unittest.TestCase):
    def test_needs_reset_uses_user_timezone(self):
        task = DailyTask(
            user_id="u1",
            task_type=TaskType.LOGIN,
            timezone="Asia/Shanghai",
        )
        shanghai_today = get_today_in_tz("Asia/Shanghai")
        self.assertFalse(task.needs_reset())

        task.reset_date = shanghai_today - timedelta(days=1)
        self.assertTrue(task.needs_reset())

    def test_reset_uses_user_timezone(self):
        task = DailyTask(
            user_id="u1",
            task_type=TaskType.KILL,
            target=50,
            timezone="Asia/Tokyo",
        )
        task.update_progress(30)
        task.completed = True
        task.claimed = True
        task.reset_date = date.today() - timedelta(days=1)

        task.reset()
        tokyo_today = get_today_in_tz("Asia/Tokyo")
        self.assertEqual(task.reset_date, tokyo_today)
        self.assertEqual(task.progress, 0)
        self.assertFalse(task.completed)
        self.assertFalse(task.claimed)

    def test_different_timezones_different_reset_dates(self):
        utc_now = datetime.now(ZoneInfo("UTC"))
        shanghai_now = datetime.now(ZoneInfo("Asia/Shanghai"))

        utc_today = utc_now.date()
        shanghai_today = shanghai_now.date()

        task_utc = DailyTask(user_id="u1", task_type=TaskType.LOGIN, timezone="UTC")
        task_shanghai = DailyTask(user_id="u2", task_type=TaskType.LOGIN, timezone="Asia/Shanghai")

        self.assertEqual(task_utc._today(), utc_today)
        self.assertEqual(task_shanghai._today(), shanghai_today)

    def test_cross_timezone_boundary_scenario(self):
        task_west = DailyTask(
            user_id="u_west",
            task_type=TaskType.LOGIN,
            timezone="America/Los_Angeles",
        )
        task_east = DailyTask(
            user_id="u_east",
            task_type=TaskType.LOGIN,
            timezone="Asia/Shanghai",
        )

        la_today = get_today_in_tz("America/Los_Angeles")
        sh_today = get_today_in_tz("Asia/Shanghai")

        task_west.reset_date = la_today
        task_east.reset_date = sh_today

        self.assertFalse(task_west.needs_reset())
        self.assertFalse(task_east.needs_reset())

        task_west.reset_date = la_today - timedelta(days=1)
        task_east.reset_date = sh_today - timedelta(days=1)

        self.assertTrue(task_west.needs_reset())
        self.assertTrue(task_east.needs_reset())

    def test_timezone_stored_in_serialization(self):
        task = DailyTask(
            user_id="u1",
            task_type=TaskType.KILL,
            timezone="Europe/Berlin",
            progress=10,
            target=50,
        )
        data = task.to_dict()
        self.assertEqual(data["timezone"], "Europe/Berlin")

        restored = DailyTask.from_dict(data)
        self.assertEqual(restored.timezone, "Europe/Berlin")
        self.assertEqual(restored._today(), get_today_in_tz("Europe/Berlin"))


class TestTaskManager(unittest.TestCase):
    def setUp(self):
        self.temp_fd, self.temp_path = tempfile.mkstemp(suffix=".json")
        os.close(self.temp_fd)
        self.manager = TaskManager(data_file=self.temp_path)

    def tearDown(self):
        if os.path.exists(self.temp_path):
            os.unlink(self.temp_path)

    def test_login_task(self):
        task = self.manager.login("user1")
        self.assertEqual(task.task_type, TaskType.LOGIN)
        self.assertEqual(task.progress, 1)
        self.assertTrue(task.completed)

    def test_kill_monsters(self):
        task = self.manager.kill_monsters("user1", 30)
        self.assertEqual(task.progress, 30)
        self.assertFalse(task.completed)

        task = self.manager.kill_monsters("user1", 30)
        self.assertEqual(task.progress, 50)
        self.assertTrue(task.completed)

    def test_recharge(self):
        task = self.manager.recharge("user1")
        self.assertEqual(task.progress, 1)
        self.assertTrue(task.completed)

    def test_get_user_tasks_creates_all(self):
        tasks = self.manager.get_user_tasks("new_user")
        self.assertEqual(len(tasks), 3)
        self.assertIn(TaskType.LOGIN, tasks)
        self.assertIn(TaskType.KILL, tasks)
        self.assertIn(TaskType.RECHARGE, tasks)

    def test_claim_reward(self):
        self.manager.login("user1")
        success = self.manager.claim_reward("user1", TaskType.LOGIN)
        self.assertTrue(success)

        success = self.manager.claim_reward("user1", TaskType.LOGIN)
        self.assertFalse(success)

    def test_claim_reward_not_completed(self):
        success = self.manager.claim_reward("user1", TaskType.KILL)
        self.assertFalse(success)

    def test_force_reset_all(self):
        self.manager.login("u1")
        self.manager.kill_monsters("u1", 50)
        self.manager.recharge("u1")
        self.manager.login("u2")

        tasks1 = self.manager.get_user_tasks("u1")
        tasks2 = self.manager.get_user_tasks("u2")
        completed_count_1 = sum(1 for t in tasks1.values() if t.completed)
        completed_count_2 = sum(1 for t in tasks2.values() if t.completed)
        self.assertEqual(completed_count_1, 3)
        self.assertEqual(completed_count_2, 1)

        count = self.manager.force_reset_all()
        self.assertEqual(count, 6)

        tasks1 = self.manager.get_user_tasks("u1")
        tasks2 = self.manager.get_user_tasks("u2")
        for t in tasks1.values():
            self.assertEqual(t.progress, 0)
            self.assertFalse(t.completed)
        for t in tasks2.values():
            self.assertEqual(t.progress, 0)
            self.assertFalse(t.completed)

    def test_reset_user_tasks(self):
        self.manager.login("u1")
        self.manager.kill_monsters("u1", 50)
        self.manager.login("u2")

        self.manager.reset_user_tasks("u1")

        tasks1 = self.manager.get_user_tasks("u1")
        for t in tasks1.values():
            self.assertEqual(t.progress, 0)
            self.assertFalse(t.completed)

        tasks2 = self.manager.get_user_tasks("u2")
        self.assertTrue(tasks2[TaskType.LOGIN].completed)

    def test_auto_reset_on_access(self):
        task = self.manager.login("u1")
        self.assertTrue(task.completed)

        task.reset_date = date.today() - timedelta(days=1)
        self.manager._save()

        manager2 = TaskManager(data_file=self.temp_path)
        task2 = manager2.get_task("u1", TaskType.LOGIN)
        self.assertEqual(task2.progress, 0)
        self.assertFalse(task2.completed)
        self.assertEqual(task2.reset_date, date.today())

    def test_persistence(self):
        self.manager.login("u1")
        self.manager.kill_monsters("u1", 25)

        with open(self.temp_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        self.assertIn("u1:login", raw)
        self.assertIn("u1:kill", raw)
        self.assertEqual(raw["u1:login"]["progress"], 1)
        self.assertEqual(raw["u1:kill"]["progress"], 25)

        manager2 = TaskManager(data_file=self.temp_path)
        tasks = manager2.get_user_tasks("u1")
        self.assertEqual(tasks[TaskType.LOGIN].progress, 1)
        self.assertEqual(tasks[TaskType.KILL].progress, 25)

    def test_custom_task_config(self):
        config = TaskConfig(task_type=TaskType.KILL, name="新版击杀", target=100, reward="1000经验")
        self.manager.set_task_config(config)
        tasks = self.manager.get_user_tasks("u1")
        self.assertEqual(tasks[TaskType.KILL].target, 100)


class TestTaskManagerTimezone(unittest.TestCase):
    def setUp(self):
        self.temp_fd, self.temp_path = tempfile.mkstemp(suffix=".json")
        os.close(self.temp_fd)
        self.manager = TaskManager(data_file=self.temp_path)

    def tearDown(self):
        if os.path.exists(self.temp_path):
            os.unlink(self.temp_path)

    def test_set_user_timezone(self):
        result = self.manager.set_user_timezone("u1", "Asia/Shanghai")
        self.assertTrue(result)
        self.assertEqual(self.manager.get_user_timezone("u1"), "Asia/Shanghai")

    def test_set_invalid_timezone(self):
        result = self.manager.set_user_timezone("u1", "Invalid/Zone")
        self.assertFalse(result)
        self.assertEqual(self.manager.get_user_timezone("u1"), "UTC")

    def test_default_timezone_is_utc(self):
        self.assertEqual(self.manager.get_user_timezone("nonexistent"), "UTC")

    def test_timezone_propagated_to_new_tasks(self):
        self.manager.set_user_timezone("u1", "Asia/Tokyo")
        task = self.manager.login("u1")
        self.assertEqual(task.timezone, "Asia/Tokyo")

    def test_timezone_synced_on_existing_tasks(self):
        self.manager.login("u1")
        task = self.manager.get_task("u1", TaskType.LOGIN)
        self.assertEqual(task.timezone, "UTC")

        self.manager.set_user_timezone("u1", "Europe/Berlin")
        task = self.manager.get_task("u1", TaskType.LOGIN)
        self.assertEqual(task.timezone, "Europe/Berlin")

    def test_timezone_persistence(self):
        self.manager.set_user_timezone("u1", "Asia/Shanghai")
        self.manager.login("u1")

        with open(self.temp_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        self.assertEqual(raw["u1:login"]["timezone"], "Asia/Shanghai")

        manager2 = TaskManager(data_file=self.temp_path)
        self.assertEqual(manager2.get_user_timezone("u1"), "Asia/Shanghai")
        task = manager2.get_task("u1", TaskType.LOGIN)
        self.assertEqual(task.timezone, "Asia/Shanghai")

    def test_get_users_in_timezone(self):
        self.manager.set_user_timezone("u1", "Asia/Shanghai")
        self.manager.set_user_timezone("u2", "Asia/Shanghai")
        self.manager.set_user_timezone("u3", "UTC")
        self.manager.login("u1")
        self.manager.login("u2")
        self.manager.login("u3")

        shanghai_users = self.manager.get_users_in_timezone("Asia/Shanghai")
        self.assertEqual(set(shanghai_users), {"u1", "u2"})

        utc_users = self.manager.get_users_in_timezone("UTC")
        self.assertIn("u3", utc_users)

    def test_get_all_timezone_groups(self):
        self.manager.set_user_timezone("u1", "Asia/Shanghai")
        self.manager.set_user_timezone("u2", "UTC")
        self.manager.set_user_timezone("u3", "Asia/Shanghai")
        self.manager.login("u1")
        self.manager.login("u2")
        self.manager.login("u3")

        groups = self.manager.get_all_timezone_groups()
        self.assertIn("Asia/Shanghai", groups)
        self.assertIn("UTC", groups)
        self.assertEqual(set(groups["Asia/Shanghai"]), {"u1", "u3"})
        self.assertEqual(groups["UTC"], ["u2"])

    def test_reset_tasks_for_timezone(self):
        self.manager.set_user_timezone("u_sh", "Asia/Shanghai")
        self.manager.set_user_timezone("u_ny", "America/New_York")
        self.manager.login("u_sh")
        self.manager.login("u_ny")

        tasks_sh = self.manager.get_user_tasks("u_sh")
        tasks_ny = self.manager.get_user_tasks("u_ny")
        self.assertTrue(tasks_sh[TaskType.LOGIN].completed)
        self.assertTrue(tasks_ny[TaskType.LOGIN].completed)

        sh_yesterday = get_today_in_tz("Asia/Shanghai") - timedelta(days=1)
        ny_today = get_today_in_tz("America/New_York")
        for task in tasks_sh.values():
            task.reset_date = sh_yesterday
        for task in tasks_ny.values():
            task.reset_date = ny_today
        self.manager._save()

        count = self.manager.reset_tasks_for_timezone("Asia/Shanghai")
        self.assertEqual(count, 3)

        tasks_sh = self.manager.get_user_tasks("u_sh")
        tasks_ny = self.manager.get_user_tasks("u_ny")
        self.assertFalse(tasks_sh[TaskType.LOGIN].completed)
        self.assertTrue(tasks_ny[TaskType.LOGIN].completed)

    def test_cross_timezone_auto_reset_on_access(self):
        self.manager.set_user_timezone("u_sh", "Asia/Shanghai")
        self.manager.set_user_timezone("u_utc", "UTC")
        self.manager.login("u_sh")
        self.manager.login("u_utc")

        task_sh = self.manager.get_task("u_sh", TaskType.LOGIN)
        task_utc = self.manager.get_task("u_utc", TaskType.LOGIN)
        self.assertTrue(task_sh.completed)
        self.assertTrue(task_utc.completed)

        sh_today = get_today_in_tz("Asia/Shanghai")
        utc_today = get_today_in_tz("UTC")

        task_sh.reset_date = sh_today - timedelta(days=1)
        task_utc.reset_date = utc_today
        self.manager._save()

        manager2 = TaskManager(data_file=self.temp_path)

        task_sh2 = manager2.get_task("u_sh", TaskType.LOGIN)
        task_utc2 = manager2.get_task("u_utc", TaskType.LOGIN)

        self.assertFalse(task_sh2.completed)
        self.assertTrue(task_utc2.completed)

    def test_needs_reset_uses_task_timezone_not_server(self):
        self.manager.set_user_timezone("u_sh", "Asia/Shanghai")
        task = self.manager.login("u_sh")
        self.assertEqual(task.timezone, "Asia/Shanghai")

        sh_today = get_today_in_tz("Asia/Shanghai")
        task.reset_date = sh_today - timedelta(days=1)
        self.assertTrue(task.needs_reset())

        utc_today = get_today_in_tz("UTC")
        task.reset_date = utc_today
        if sh_today != utc_today:
            self.assertTrue(task.needs_reset())
        else:
            self.assertFalse(task.needs_reset())


class TestTimezoneScheduler(unittest.TestCase):
    def test_is_tz_past_reset_time(self):
        from reset_scheduler import _is_tz_past_reset_time
        import reset_scheduler as rs_module

        fixed_now = datetime(2026, 6, 13, 0, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
        original_datetime = rs_module.datetime

        class MockDatetime:
            @staticmethod
            def now(tz=None):
                if tz is None:
                    return fixed_now
                return fixed_now.astimezone(tz)

            def __new__(cls, *args, **kwargs):
                return original_datetime(*args, **kwargs)

        with patch.object(rs_module, "datetime", MockDatetime):
            self.assertTrue(_is_tz_past_reset_time("Asia/Shanghai", 0, 0))
            self.assertTrue(_is_tz_past_reset_time("Asia/Shanghai", 0, 30))
            self.assertFalse(_is_tz_past_reset_time("Asia/Shanghai", 1, 0))

        fixed_now2 = datetime(2026, 6, 13, 0, 30, tzinfo=ZoneInfo("UTC"))

        class MockDatetime2:
            @staticmethod
            def now(tz=None):
                if tz is None:
                    return fixed_now2
                return fixed_now2.astimezone(tz)

            def __new__(cls, *args, **kwargs):
                return original_datetime(*args, **kwargs)

        with patch.object(rs_module, "datetime", MockDatetime2):
            self.assertFalse(_is_tz_past_reset_time("UTC", 1, 0))
            self.assertTrue(_is_tz_past_reset_time("UTC", 0, 30))
            self.assertTrue(_is_tz_past_reset_time("UTC", 0, 0))

        fixed_now3 = datetime(2026, 6, 14, 0, 0, tzinfo=ZoneInfo("UTC"))

        class MockDatetime3:
            @staticmethod
            def now(tz=None):
                if tz is None:
                    return fixed_now3
                return fixed_now3.astimezone(tz)

            def __new__(cls, *args, **kwargs):
                return original_datetime(*args, **kwargs)

        with patch.object(rs_module, "datetime", MockDatetime3):
            self.assertTrue(_is_tz_past_reset_time("UTC", 0, 0))

    def test_get_tz_today(self):
        from reset_scheduler import _get_tz_today
        import reset_scheduler as rs_module

        fixed_now = datetime(2026, 6, 13, 23, 0, tzinfo=ZoneInfo("UTC"))
        original_datetime = rs_module.datetime

        class MockDatetime:
            @staticmethod
            def now(tz=None):
                if tz is None:
                    return fixed_now
                return fixed_now.astimezone(tz)

            def __new__(cls, *args, **kwargs):
                return original_datetime(*args, **kwargs)

        with patch.object(rs_module, "datetime", MockDatetime):
            self.assertEqual(_get_tz_today("UTC"), date(2026, 6, 13))
            self.assertEqual(_get_tz_today("Asia/Shanghai"), date(2026, 6, 14))

    def _mock_datetime_for_scheduler(self, fixed_now):
        import reset_scheduler as rs_module
        from models import get_today_in_tz as models_get_today
        import models as models_module

        original_datetime = rs_module.datetime
        original_models_datetime = models_module.datetime

        class MockDatetime:
            @staticmethod
            def now(tz=None):
                if tz is None:
                    return fixed_now
                return fixed_now.astimezone(tz)

            def __new__(cls, *args, **kwargs):
                return original_datetime(*args, **kwargs)

        return (
            patch.object(rs_module, "datetime", MockDatetime),
            patch.object(models_module, "datetime", MockDatetime),
        )

    def test_scheduler_resets_only_past_midnight(self):
        from reset_scheduler import DailyResetScheduler
        temp_fd, temp_path = tempfile.mkstemp(suffix=".json")
        os.close(temp_fd)
        try:
            tm = TaskManager(data_file=temp_path)
            tm.set_user_timezone("u_sh", "Asia/Shanghai")
            tm.set_user_timezone("u_utc", "UTC")

            fixed_now = datetime(2026, 6, 13, 0, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
            mock1, mock2 = self._mock_datetime_for_scheduler(fixed_now)

            with mock1, mock2:
                tm.login("u_sh")
                tm.login("u_utc")

                for uid in ["u_sh", "u_utc"]:
                    tasks = tm.get_user_tasks(uid)
                    for task in tasks.values():
                        if uid == "u_sh":
                            task.reset_date = task._today() - timedelta(days=1)
                        else:
                            task.reset_date = task._today()
                tm._save()

                scheduler = DailyResetScheduler(tm, reset_hour=0, reset_minute=0)
                scheduler._check_and_reset()

                task_sh2 = tm._tasks["u_sh"][TaskType.LOGIN]
                task_utc2 = tm._tasks["u_utc"][TaskType.LOGIN]
                self.assertFalse(task_sh2.completed)
                self.assertTrue(task_utc2.completed)

                self.assertIn("Asia/Shanghai", scheduler._last_reset_dates)
                self.assertEqual(scheduler._last_reset_dates["Asia/Shanghai"], date(2026, 6, 13))
                self.assertIn("UTC", scheduler._last_reset_dates)
                self.assertEqual(scheduler._last_reset_dates["UTC"], date(2026, 6, 12))

            fixed_now2 = datetime(2026, 6, 13, 0, 30, tzinfo=ZoneInfo("UTC"))
            mock3, mock4 = self._mock_datetime_for_scheduler(fixed_now2)
            with mock3, mock4:
                for uid in ["u_sh", "u_utc"]:
                    for task in tm._tasks[uid].values():
                        if not task.completed:
                            task.reset_date = task._today() - timedelta(days=1)
                tm._save()

                scheduler._check_and_reset()

                task_utc3 = tm._tasks["u_utc"][TaskType.LOGIN]
                self.assertFalse(task_utc3.completed)
                self.assertEqual(scheduler._last_reset_dates["UTC"], date(2026, 6, 13))

        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_scheduler_does_not_reset_twice_same_day(self):
        from reset_scheduler import DailyResetScheduler
        temp_fd, temp_path = tempfile.mkstemp(suffix=".json")
        os.close(temp_fd)
        try:
            tm = TaskManager(data_file=temp_path)
            tm.set_user_timezone("u1", "UTC")

            fixed_now = datetime(2026, 6, 13, 1, 0, tzinfo=ZoneInfo("UTC"))
            mock1, mock2 = self._mock_datetime_for_scheduler(fixed_now)

            with mock1, mock2:
                tm.login("u1")
                for task in tm.get_user_tasks("u1").values():
                    task.reset_date = task._today() - timedelta(days=1)
                tm._save()

                scheduler = DailyResetScheduler(tm, reset_hour=0, reset_minute=0)
                scheduler._check_and_reset()
                self.assertEqual(scheduler._last_reset_dates["UTC"], date(2026, 6, 13))

                tm.login("u1")
                for task in tm._tasks["u1"].values():
                    if task.completed:
                        task.reset_date = task._today() - timedelta(days=1)
                tm._save()

                before_reset_dates = dict(scheduler._last_reset_dates)
                scheduler._check_and_reset()
                self.assertEqual(scheduler._last_reset_dates, before_reset_dates)

                task2 = tm._tasks["u1"][TaskType.LOGIN]
                self.assertTrue(task2.completed)

        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_trigger_timezone_reset(self):
        from reset_scheduler import DailyResetScheduler
        temp_fd, temp_path = tempfile.mkstemp(suffix=".json")
        os.close(temp_fd)
        try:
            tm = TaskManager(data_file=temp_path)
            tm.set_user_timezone("u1", "Asia/Shanghai")
            tm.set_user_timezone("u2", "UTC")
            tm.login("u1")
            tm.login("u2")

            scheduler = DailyResetScheduler(tm)
            count = scheduler.trigger_timezone_reset("Asia/Shanghai")
            self.assertGreaterEqual(count, 0)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
