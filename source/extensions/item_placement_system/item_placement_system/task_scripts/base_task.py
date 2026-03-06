"""
Base Task Class
タスクスクリプトの基底クラス

各オブジェクト用のタスクはこのクラスを継承して実装します。
"""

from abc import ABC, abstractmethod
from pxr import Usd
import carb

LOG_PREFIX = "[Task]"


class BaseTask(ABC):
    """
    タスクスクリプトの基底クラス

    各オブジェクト用のタスクはこのクラスを継承して実装します。
    """

    def __init__(self, slot_id: str, real_object_path: str):
        """
        Args:
            slot_id: スロットID
            real_object_path: 本物のオブジェクトパス
        """
        self.slot_id = slot_id
        self.real_object_path = real_object_path
        self._task_started = False
        self._task_completed = False

    @abstractmethod
    def check_completion(self, stage: Usd.Stage) -> bool:
        """
        タスク完了条件をチェック

        Args:
            stage: USD Stage

        Returns:
            bool: タスクが完了していればTrue
        """
        pass

    def on_task_start(self, stage: Usd.Stage):
        """タスク開始時の処理（オーバーライド可能）"""
        self._task_started = True
        carb.log_info(f"{LOG_PREFIX} Started: {self.slot_id}")

    def on_task_complete(self, stage: Usd.Stage):
        """タスク完了時の処理（オーバーライド可能）"""
        self._task_completed = True
        carb.log_info(f"{LOG_PREFIX} Completed: {self.slot_id}")

    def reset(self):
        """タスクをリセット"""
        self._task_started = False
        self._task_completed = False
        carb.log_info(f"{LOG_PREFIX} Reset: {self.slot_id}")


class NoTask(BaseTask):
    """タスクなしのダミー実装"""

    def check_completion(self, stage: Usd.Stage) -> bool:
        """常にTrue（タスクなし = 常に取り外し可能）"""
        return True

    def on_task_start(self, stage: Usd.Stage):
        """何もしない"""
        self._task_started = True
        carb.log_info(f"{LOG_PREFIX} NoTask - immediately detachable: {self.slot_id}")

    def on_task_complete(self, stage: Usd.Stage):
        """何もしない"""
        self._task_completed = True
