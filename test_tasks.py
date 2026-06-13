import os
import json
import tempfile
import unittest
from datetime import date, timedelta
from models import TaskType, DailyTask, TaskConfig
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
        )
        data = task.to_dict()
        self.assertEqual(data["user_id"], "u123")
        self.assertEqual(data["task_type"], "recharge")

        restored = DailyTask.from_dict(data)
        self.assertEqual(restored.user_id, task.user_id)
        self.assertEqual(restored.task_type, task.task_type)
        self.assertEqual(restored.progress, task.progress)
        self.assertEqual(restored.completed, task.completed)


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
