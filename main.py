import os
import time
import signal
import sys
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

from models import TaskType
from task_manager import TaskManager
from reset_scheduler import DailyResetScheduler


USERS = [
    {"id": "user_cn", "name": "中国玩家", "tz": "Asia/Shanghai"},
    {"id": "user_us", "name": "美国玩家", "tz": "America/New_York"},
    {"id": "user_uk", "name": "英国玩家", "tz": "Europe/London"},
    {"id": "user_jp", "name": "日本玩家", "tz": "Asia/Tokyo"},
]


def on_reset_complete(reset_count: int) -> None:
    print(f"[回调] 每日重置完成，共处理 {reset_count} 个任务")


def print_current_times() -> None:
    print("\n----- 当前各时区时间 -----")
    for user in USERS:
        now = datetime.now(ZoneInfo(user["tz"]))
        print(f"  {user['tz']:20s} | {user['name']:8s} | {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print("--------------------------\n")


def print_user_tasks(task_manager: TaskManager, user_id: str, user_name: str = None) -> None:
    name = user_name or user_id
    tz = task_manager.get_user_timezone(user_id)
    print(f"\n===== 用户 {name} ({user_id}) [时区: {tz}] 的每日任务 =====")
    configs = task_manager.get_task_configs()
    tasks = task_manager.get_user_tasks(user_id)
    for task_type, task in tasks.items():
        config = configs.get(task_type)
        tname = config.name if config else task_type.value
        streak = task.streak_days
        reward = task.get_current_reward(config) if config else "-"
        status = "✅已完成" if task.completed else "⏳进行中"
        claimed = "🎁已领取" if task.claimed else "📦未领取"
        streak_str = f"🔥连续{streak}天" if streak > 0 else "  未连续"
        print(
            f"[{tname}] 进度: {task.progress}/{task.target} "
            f"| {status} | {claimed} | {streak_str} | 奖励: {reward}"
        )
    print("=" * 70 + "\n")


def main() -> None:
    data_file = "tasks_data.json"
    if os.path.exists(data_file):
        os.remove(data_file)

    task_manager = TaskManager(data_file=data_file)

    scheduler = DailyResetScheduler(
        task_manager=task_manager,
        reset_hour=0,
        reset_minute=0,
        on_reset_callback=on_reset_complete,
        check_interval=60,
    )

    def handle_shutdown(signum, frame):
        print("\n正在关闭服务...")
        scheduler.stop()
        print("服务已关闭，再见！")
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    scheduler.start()

    print("=" * 70)
    print("每日任务系统已启动（时区感知模式）")
    print("支持任务类型: 登录(LOGIN)、击杀(KILL)、充值(RECHARGE)")
    print("调度服务: 各时区本地时间 00:00 自动重置")
    print("=" * 70)

    print_current_times()

    print("--- 为各用户设置时区 ---")
    for user in USERS:
        ok = task_manager.set_user_timezone(user["id"], user["tz"])
        print(f"  用户 {user['name']}({user['id']}) 设置时区 {user['tz']}: {'成功' if ok else '失败'}")

    print("\n--- 模拟各用户完成任务 ---")
    for user in USERS:
        print(f"\n[玩家 {user['name']}] 登录并击杀怪物...")
        task_manager.login(user["id"])
        task_manager.kill_monsters(user["id"], 50)
        task_manager.recharge(user["id"])
        print_user_tasks(task_manager, user["id"], user["name"])

    print("\n--- 演示连续任务奖励递增 ---")
    cn_id = "user_cn"
    task = task_manager.get_task(cn_id, TaskType.LOGIN)
    task.streak_days = 3
    task.last_completed_date = date.today() - timedelta(days=1)
    task_manager._save()
    configs = task_manager.get_task_configs()
    config = configs[TaskType.LOGIN]
    print(f"  连续登录 3 天，当前奖励: {task.get_current_reward(config)}")

    task.streak_days = 7
    print(f"  连续登录 7 天，当前奖励: {task.get_current_reward(config)}")

    task.streak_days = 15
    print(f"  连续登录 15 天（已达上限），当前奖励: {task.get_current_reward(config)}")

    task.streak_days = 1
    print(f"  连续登录 1 天（基础奖励），当前奖励: {task.get_current_reward(config)}")

    print("\n--- 领取连续任务奖励 ---")
    success, reward = task_manager.claim_reward(cn_id, TaskType.LOGIN)
    print(f"  领取登录奖励: {'成功' if success else '失败'} - {reward}")

    print_user_tasks(task_manager, cn_id, "中国玩家")

    print("\n--- 当前时区分组 ---")
    groups = task_manager.get_all_timezone_groups()
    for tz, users in groups.items():
        user_list = ", ".join(users)
        print(f"  {tz}: {user_list}")

    print("\n--- 测试: 按时区手动重置 ---")
    for user in USERS:
        print(f"\n按 Enter 键手动重置时区 {user['tz']} 的任务...")
        input()
        count = scheduler.trigger_timezone_reset(user["tz"])
        print(f"时区 {user['tz']} 重置了 {count} 个任务")
        print_user_tasks(task_manager, user["id"], user["name"])

    print("\n--- 模拟各用户再次完成任务，等待自动重置 ---")
    for user in USERS:
        task_manager.login(user["id"])
        task_manager.kill_monsters(user["id"], 30)

    print_current_times()
    print("调度服务将继续运行，等待各时区本地 00:00 自动重置...")
    print("按 Ctrl+C 退出服务")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        handle_shutdown(None, None)


if __name__ == "__main__":
    main()
