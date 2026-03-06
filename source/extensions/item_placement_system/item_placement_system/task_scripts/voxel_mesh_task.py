"""
Voxel Mesh Task
Voxel Mesh用タスクスクリプト

条件: handle_drillを-100度以上回転させる
"""

from .base_task import BaseTask
from pxr import Usd, UsdPhysics
import carb

LOG_PREFIX = "[VoxelMeshTask]"


class VoxelMeshTask(BaseTask):
    """
    Voxel Mesh用タスク

    条件: handle_drillを-100度以上回転させる
    """

    def __init__(self, slot_id: str, real_object_path: str):
        super().__init__(slot_id, real_object_path)
        self.target_rotation = -100.0  # 目標回転角度（度）
        self.handle_path = "/World/New_MillingMachine/Main/Handle_Dril"
        self.joint_path = f"{self.handle_path}/RevoluteJoint"

    def check_completion(self, stage: Usd.Stage) -> bool:
        """handle_drillの回転角度をチェック"""
        try:
            # RevoluteJointのDriveAPIから現在角度を取得
            joint_prim = stage.GetPrimAtPath(self.joint_path)
            if not joint_prim or not joint_prim.IsValid():
                return False

            drive_api = UsdPhysics.DriveAPI.Get(joint_prim, "angular")
            if not drive_api:
                return False

            # targetPositionが目標値以下になったか確認
            current_position = drive_api.GetTargetPositionAttr().Get()
            if current_position is None:
                return False

            # -100度以下（下限に近い）であれば完了
            is_completed = current_position <= self.target_rotation

            if is_completed and not self._task_completed:
                carb.log_info(f"{LOG_PREFIX} ✅ タスク完了！ 現在角度: {current_position:.1f}°")
                # USD属性 custom:task を True に設定
                self._update_task_attribute(stage, True)

            return is_completed

        except Exception as e:
            carb.log_error(f"{LOG_PREFIX} Error: {e}")
            return False

    def _update_task_attribute(self, stage: Usd.Stage, value: bool):
        """custom:task属性をUSDに保存"""
        try:
            real_prim = stage.GetPrimAtPath(self.real_object_path)
            if not real_prim or not real_prim.IsValid():
                return

            from pxr import Sdf
            task_attr = real_prim.GetAttribute("custom:task")
            if not task_attr:
                task_attr = real_prim.CreateAttribute("custom:task", Sdf.ValueTypeNames.Bool, False)
            task_attr.Set(value)
            carb.log_info(f"{LOG_PREFIX} Updated custom:task={value} on {self.real_object_path}")

        except Exception as e:
            carb.log_error(f"{LOG_PREFIX} Error updating task attribute: {e}")

    def on_task_start(self, stage: Usd.Stage):
        """タスク開始時の処理"""
        super().on_task_start(stage)
        carb.log_info(f"{LOG_PREFIX} 🎯 タスク開始: handle_drillを{self.target_rotation}度以下まで回転させてください")

    def on_task_complete(self, stage: Usd.Stage):
        """タスク完了時の処理"""
        super().on_task_complete(stage)
        carb.log_info(f"{LOG_PREFIX} 🎉 タスク完了！ Voxel Meshを取り外せます")
