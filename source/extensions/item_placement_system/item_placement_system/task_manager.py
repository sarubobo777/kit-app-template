"""
Task Manager
タスクスクリプトの管理

このモジュールは、各オブジェクト用のタスクスクリプトを管理します。
"""

import carb
from typing import Dict, Optional, Type
from .task_scripts.base_task import BaseTask, NoTask

LOG_PREFIX = "[TaskManager]"


class TaskManager:
    """タスクスクリプトの管理"""

    def __init__(self):
        self._tasks: Dict[str, BaseTask] = {}
        self._task_classes: Dict[str, Type[BaseTask]] = {}

        # タスククラスを登録
        self._register_task_classes()

    def _register_task_classes(self):
        """利用可能なタスククラスを登録"""
        try:
            # VoxelMeshTask
            from .task_scripts.voxel_mesh_task import VoxelMeshTask
            self._task_classes['voxel_mesh'] = VoxelMeshTask

            # PlugTask
            from .task_scripts.plug_task import PlugTask
            self._task_classes['plug'] = PlugTask

            # NoTask（タスクなし）
            self._task_classes['none'] = NoTask

            carb.log_info(f"{LOG_PREFIX} Registered {len(self._task_classes)} task classes")

        except Exception as e:
            carb.log_error(f"{LOG_PREFIX} Error registering task classes: {e}")
            import traceback
            traceback.print_exc()

    def create_task(self, slot_id: str, task_type: str, real_object_path: str) -> Optional[BaseTask]:
        """
        タスクインスタンスを生成

        Args:
            slot_id: スロットID
            task_type: タスクタイプ ('voxel_mesh', 'plug', 'none' など)
            real_object_path: 本物のオブジェクトパス

        Returns:
            BaseTask: タスクインスタンス（失敗時はNone）
        """
        if task_type not in self._task_classes:
            carb.log_warn(f"{LOG_PREFIX} Unknown task type: {task_type}, using NoTask")
            task_type = 'none'

        task_class = self._task_classes[task_type]
        task_instance = task_class(slot_id, real_object_path)

        self._tasks[slot_id] = task_instance
        carb.log_info(f"{LOG_PREFIX} Created task: {slot_id} -> {task_type}")

        return task_instance

    def get_task(self, slot_id: str) -> Optional[BaseTask]:
        """スロットIDからタスクを取得"""
        return self._tasks.get(slot_id)

    def check_task_completion(self, slot_id: str, stage) -> bool:
        """
        タスク完了状態をチェック

        Args:
            slot_id: スロットID
            stage: USD Stage

        Returns:
            bool: タスクが完了していればTrue
        """
        task = self.get_task(slot_id)
        if not task:
            return True  # タスクが登録されていない場合は完了とみなす

        return task.check_completion(stage)

    def reset_task(self, slot_id: str):
        """タスクをリセット"""
        task = self.get_task(slot_id)
        if task:
            task.reset()


# グローバルインスタンス
_task_manager_instance = None


def get_task_manager():
    """TaskManagerのグローバルインスタンスを取得"""
    global _task_manager_instance
    if _task_manager_instance is None:
        _task_manager_instance = TaskManager()
    return _task_manager_instance
