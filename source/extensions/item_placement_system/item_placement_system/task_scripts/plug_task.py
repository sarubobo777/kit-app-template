"""
Plug Task
プラグ用タスクスクリプト

条件: 指定位置から10cm以内に移動させる
"""

from .base_task import BaseTask
from pxr import Usd, UsdGeom, Gf
import carb

LOG_PREFIX = "[PlugTask]"


class PlugTask(BaseTask):
    """
    プラグ用タスク

    条件: 指定位置から10cm以内に移動しなければならない
    """

    def __init__(self, slot_id: str, real_object_path: str):
        super().__init__(slot_id, real_object_path)
        # 目標位置（例：プラグを差し込む位置）
        self.target_position = Gf.Vec3d(115.0, 5.0, 78.5)
        self.distance_threshold = 10.0  # 10cm

    def check_completion(self, stage: Usd.Stage) -> bool:
        """オブジェクトが目標位置に到達したかチェック"""
        try:
            prim = stage.GetPrimAtPath(self.real_object_path)
            if not prim or not prim.IsValid():
                return False

            xformable = UsdGeom.Xformable(prim)
            world_transform = xformable.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
            current_position = world_transform.ExtractTranslation()

            # 目標位置との距離を計算
            distance = (current_position - self.target_position).GetLength()

            is_completed = distance < self.distance_threshold

            if is_completed and not self._task_completed:
                carb.log_info(f"{LOG_PREFIX} ✅ タスク完了！ 距離: {distance:.1f}cm")
                # USD属性 custom:task を True に設定
                self._update_task_attribute(stage, True)

            return is_completed

        except Exception as e:
            carb.log_error(f"{LOG_PREFIX} Error: {e}")
            return False

    def _update_task_attribute(self, stage: Usd.Stage, value: bool):
        """custom:task属性をUSDに保存"""
        try:
            prim = stage.GetPrimAtPath(self.real_object_path)
            if not prim or not prim.IsValid():
                return

            from pxr import Sdf
            task_attr = prim.GetAttribute("custom:task")
            if not task_attr:
                task_attr = prim.CreateAttribute("custom:task", Sdf.ValueTypeNames.Bool, False)
            task_attr.Set(value)
            carb.log_info(f"{LOG_PREFIX} Updated custom:task={value} on {self.real_object_path}")

        except Exception as e:
            carb.log_error(f"{LOG_PREFIX} Error updating task attribute: {e}")

    def on_task_start(self, stage: Usd.Stage):
        """タスク開始時の処理"""
        super().on_task_start(stage)
        carb.log_info(f"{LOG_PREFIX} 🎯 タスク開始: プラグを目標位置{self.distance_threshold}cm以内に移動させてください")

    def on_task_complete(self, stage: Usd.Stage):
        """タスク完了時の処理"""
        super().on_task_complete(stage)
        carb.log_info(f"{LOG_PREFIX} 🎉 タスク完了！ プラグを取り外せます")
