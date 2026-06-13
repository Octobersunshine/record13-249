import time
import signal
import sys

from models import TaskType
from task_manager import TaskManager
from reset_scheduler import DailyResetScheduler


def on_reset_complete(reset_count: int) -> None:
    print(f"[回调] 每日重置完成，共处理 {reset_count} 个任务")


def print_user_tasks(task_manager: TaskManager, user_id: str) -> None:
    print(f"\n===== 用户 {user_id} 的每日任务 =====")
    configs = task_manager.get_task_configs()
    tasks = task_manager.get_user_tasks(user_id)
    for task_type, task in tasks.items():
        config = configs.get(task_type)
        name = config.name if config else task_type.value
        reward = config.reward if config else "-"
        status = "✅已完成" if task.completed else "⏳进行中"
        claimed = "🎁已领取" if task.claimed else "📦未领取"
        print(
            f"[{name}] 进度: {task.progress}/{task.target} "
            f"| {status} | {claimed} | 奖励: {reward}"
        )
    print("=====================================\n")


def main() -> None:
    data_file = "tasks_data.json"
    task_manager = TaskManager(data_file=data_file)

    scheduler = DailyResetScheduler(
        task_manager=task_manager,
        reset_hour=0,
        reset_minute=0,
        on_reset_callback=on_reset_complete,
    )

    def handle_shutdown(signum, frame):
        print("\n正在关闭服务...")
        scheduler.stop()
        print("服务已关闭，再见！")
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    scheduler.start()

    print("=" * 50)
    print("每日任务系统已启动")
    print("支持任务类型: 登录(LOGIN)、击杀(KILL)、充值(RECHARGE)")
    print("调度服务: 每日凌晨 00:00 自动重置")
    print("=" * 50)

    demo_user = "user_1001"

    print(f"\n--- 模拟用户 {demo_user} 登录 ---")
    task_manager.login(demo_user)
    print_user_tasks(task_manager, demo_user)

    print(f"--- 模拟用户 {demo_user} 击杀 30 只怪物 ---")
    task_manager.kill_monsters(demo_user, 30)
    print_user_tasks(task_manager, demo_user)

    print(f"--- 模拟用户 {demo_user} 再击杀 25 只怪物 ---")
    task_manager.kill_monsters(demo_user, 25)
    print_user_tasks(task_manager, demo_user)

    print(f"--- 模拟用户 {demo_user} 领取击杀任务奖励 ---")
    success = task_manager.claim_reward(demo_user, TaskType.KILL)
    print(f"领取结果: {'成功' if success else '失败'}")
    print_user_tasks(task_manager, demo_user)

    print(f"--- 模拟用户 {demo_user} 充值 ---")
    task_manager.recharge(demo_user)
    print_user_tasks(task_manager, demo_user)

    print("\n--- 测试: 手动触发重置 ---")
    input("按 Enter 键手动触发一次任务重置...")
    reset_count = scheduler.trigger_manual_reset()
    print(f"重置了 {reset_count} 个任务")
    print_user_tasks(task_manager, demo_user)

    print("\n调度服务将继续运行，等待每日凌晨自动重置...")
    print("按 Ctrl+C 退出服务")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        handle_shutdown(None, None)


if __name__ == "__main__":
    main()
