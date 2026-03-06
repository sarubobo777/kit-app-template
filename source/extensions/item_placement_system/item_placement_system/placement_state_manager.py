"""
Placement State Manager
配置状態の統括管理（表示/非表示切り替え版）

このモジュールは、オブジェクトの配置状態を管理し、
プロキシと本物のオブジェクトの表示/非表示を制御します。
"""

from enum import Enum
from typing import Dict, Optional, Tuple
import carb
from pxr import UsdGeom, Gf, UsdPhysics, Sdf

LOG_PREFIX = "[PlacementState]"


class PlacementState(Enum):
    """オブジェクトの配置状態"""
    IDLE = "idle"                    # 待機中（プロキシが表示中）
    PLACED = "placed"                # 設置済み（実オブジェクト表示中）
    DETACHABLE = "detachable"        # 取り外し可能（タスク完了後）
    DETACHED = "detached"            # 取り外し済み（プロキシに戻る）


class ObjectPlacementState:
    """個別オブジェクトの状態"""

    def __init__(self, slot_id: str, proxy_path: str, real_path: str):
        self.slot_id = slot_id
        self.proxy_path = proxy_path
        self.real_path = real_path
        self.state = PlacementState.IDLE
        self.task_completed = False


class PlacementStateManager:
    """配置状態の統括管理（表示/非表示切り替え版）"""

    def __init__(self):
        self._states: Dict[str, ObjectPlacementState] = {}
        self._task_manager = None  # TaskManagerへの参照

    def set_task_manager(self, task_manager):
        """TaskManagerを設定"""
        self._task_manager = task_manager
        carb.log_info(f"{LOG_PREFIX} TaskManager set")

    def register_object(self, slot_id: str, proxy_path: str, real_path: str):
        """オブジェクトを登録"""
        self._states[slot_id] = ObjectPlacementState(slot_id, proxy_path, real_path)
        carb.log_info(f"{LOG_PREFIX} Registered: {slot_id}")

    def on_placement(self, slot_id: str, stage, proxy_path: str = None, real_path: str = None, proxy_reset_position: Tuple[float, float, float] = None):
        """
        配置時の処理

        Args:
            slot_id: スロットID
            stage: USD Stage
            proxy_path: プロキシオブジェクトパス
            real_path: 本物のオブジェクトパス
            proxy_reset_position: プロキシのリセット位置（例: (0, 100, 0)）
        """
        try:
            if slot_id not in self._states:
                carb.log_warn(f"{LOG_PREFIX} Slot not registered: {slot_id}")
                carb.log_warn(f"{LOG_PREFIX} Available slots: {list(self._states.keys())}")
                return False

            state = self._states[slot_id]
            carb.log_info(f"{LOG_PREFIX} Starting placement for slot: {slot_id}")

            # ★ステップ1: プロキシを所定位置に移動（遠くに隠す）
            if proxy_path and proxy_reset_position:
                carb.log_info(f"{LOG_PREFIX} Moving proxy {proxy_path} to {proxy_reset_position}")
                self._move_object(stage, proxy_path, proxy_reset_position)
                carb.log_info(f"{LOG_PREFIX} Proxy moved to: {proxy_reset_position}")

            # ★ステップ2: 本物のオブジェクトを表示し、コリジョンを有効化
            if real_path:
                carb.log_info(f"{LOG_PREFIX} Making real object visible: {real_path}")
                self._set_visibility(stage, real_path, visible=True)
                self._set_collision_enabled(stage, real_path, enabled=True)
                carb.log_info(f"{LOG_PREFIX} Real object visible and collision enabled: {real_path}")

            # ステップ3: 状態更新
            state.state = PlacementState.PLACED
            carb.log_info(f"{LOG_PREFIX} State updated to PLACED")

            # ステップ4: タスク開始
            if self._task_manager:
                task = self._task_manager.get_task(slot_id)
                if task:
                    task.on_task_start(stage)
                    carb.log_info(f"{LOG_PREFIX} Task started for slot: {slot_id}")

            carb.log_info(f"{LOG_PREFIX} ✅ Object placed: {slot_id}")
            return True

        except Exception as e:
            carb.log_error(f"{LOG_PREFIX} Error in on_placement: {e}")
            import traceback
            traceback.print_exc()
            return False

    def on_detachment(self, slot_id: str, stage, real_path: str = None, proxy_path: str = None, proxy_original_position: Tuple[float, float, float] = None):
        """
        取り外し時の処理

        Args:
            slot_id: スロットID
            stage: USD Stage
            real_path: 本物のオブジェクトパス
            proxy_path: プロキシオブジェクトパス
            proxy_original_position: プロキシの元の位置（例: (0, 0, 0)）
        """
        if slot_id not in self._states:
            carb.log_warn(f"{LOG_PREFIX} Slot not registered: {slot_id}")
            return False

        state = self._states[slot_id]

        # ★ステップ1: 本物のオブジェクトを非表示にし、コリジョンを無効化
        if real_path:
            self._set_visibility(stage, real_path, visible=False)
            self._set_collision_enabled(stage, real_path, enabled=False)
            carb.log_info(f"{LOG_PREFIX} Real object hidden and collision disabled: {real_path}")

        # ★ステップ2: プロキシを元の位置に戻す
        if proxy_path and proxy_original_position:
            self._move_object(stage, proxy_path, proxy_original_position)
            carb.log_info(f"{LOG_PREFIX} Proxy reset to: {proxy_original_position}")

        # ★ステップ3: プロキシを再表示
        if proxy_path:
            self._set_visibility(stage, proxy_path, visible=True)

        # ステップ4: 状態リセット
        state.state = PlacementState.IDLE
        state.task_completed = False

        # ステップ5: タスクリセット
        if self._task_manager:
            self._task_manager.reset_task(slot_id)

        carb.log_info(f"{LOG_PREFIX} ✅ Object detached: {slot_id}")
        return True

    def check_detachment_allowed(self, slot_id: str, stage) -> bool:
        """
        取り外し可能かチェック（タスク完了判定含む）

        Args:
            slot_id: スロットID
            stage: USD Stage

        Returns:
            bool: 取り外し可能ならTrue
        """
        if slot_id not in self._states:
            return False

        state = self._states[slot_id]

        # 配置済み状態でなければ取り外し不可
        if state.state != PlacementState.PLACED and state.state != PlacementState.DETACHABLE:
            return False

        # タスク完了チェック
        if self._task_manager:
            is_task_complete = self._task_manager.check_task_completion(slot_id, stage)

            if is_task_complete and not state.task_completed:
                # タスクが完了した！
                state.task_completed = True
                state.state = PlacementState.DETACHABLE

                task = self._task_manager.get_task(slot_id)
                if task:
                    task.on_task_complete(stage)

                carb.log_info(f"{LOG_PREFIX} 🎉 Task completed! Now detachable: {slot_id}")

        return state.state == PlacementState.DETACHABLE

    def _set_visibility(self, stage, prim_path: str, visible: bool):
        """オブジェクトの表示/非表示切り替え（inherited/invisible）"""
        try:
            prim = stage.GetPrimAtPath(prim_path)
            if not prim or not prim.IsValid():
                carb.log_error(f"{LOG_PREFIX} Invalid prim for visibility: {prim_path}")
                return

            imageable = UsdGeom.Imageable(prim)
            visibility_attr = imageable.GetVisibilityAttr()
            if not visibility_attr:
                # 属性が存在しない場合、PhysXシミュレーション中は作成できない
                carb.log_error(f"{LOG_PREFIX} No visibility attribute on {prim_path}")
                carb.log_error(f"{LOG_PREFIX} Cannot create attribute during PhysX simulation (causes mutex error)")
                carb.log_error(f"{LOG_PREFIX} Please ensure object has visibility attribute before simulation")
                return

            if visible:
                # inherited に設定（通常の表示状態）
                visibility_attr.Set(UsdGeom.Tokens.inherited)
                carb.log_info(f"{LOG_PREFIX} Set visibility=inherited for {prim_path}")
            else:
                # invisible に設定
                visibility_attr.Set(UsdGeom.Tokens.invisible)
                carb.log_info(f"{LOG_PREFIX} Set visibility=invisible for {prim_path}")

        except Exception as e:
            carb.log_error(f"{LOG_PREFIX} Error setting visibility for {prim_path}: {e}")
            import traceback
            traceback.print_exc()

    def _set_collision_enabled(self, stage, prim_path: str, enabled: bool):
        """コリジョンの有効/無効を切り替え"""
        try:
            prim = stage.GetPrimAtPath(prim_path)
            if not prim or not prim.IsValid():
                carb.log_error(f"{LOG_PREFIX} Invalid prim for collision: {prim_path}")
                return

            collision_api = UsdPhysics.CollisionAPI.Get(stage, prim_path)
            if not collision_api:
                # CollisionAPIが存在しない場合、PhysXシミュレーション中は作成できない
                carb.log_error(f"{LOG_PREFIX} No CollisionAPI found on {prim_path}")
                carb.log_error(f"{LOG_PREFIX} Cannot apply CollisionAPI during PhysX simulation (causes mutex error)")
                carb.log_error(f"{LOG_PREFIX} Please ensure object has CollisionAPI before simulation")
                return

            # collisionEnabledを設定
            collision_enabled_attr = collision_api.GetCollisionEnabledAttr()
            if not collision_enabled_attr:
                # 属性が存在しない場合、PhysXシミュレーション中は作成できない
                carb.log_error(f"{LOG_PREFIX} No collisionEnabled attribute on {prim_path}")
                carb.log_error(f"{LOG_PREFIX} Cannot create attribute during PhysX simulation")
                return

            collision_enabled_attr.Set(enabled)
            carb.log_info(f"{LOG_PREFIX} Set collisionEnabled={enabled} for {prim_path}")

        except Exception as e:
            carb.log_error(f"{LOG_PREFIX} Error setting collision for {prim_path}: {e}")
            import traceback
            traceback.print_exc()

    def _move_object(self, stage, prim_path: str, position: Tuple[float, float, float]):
        """オブジェクトを指定位置に移動"""
        try:
            prim = stage.GetPrimAtPath(prim_path)
            if not prim or not prim.IsValid():
                carb.log_error(f"{LOG_PREFIX} Invalid prim for move: {prim_path}")
                return

            xformable = UsdGeom.Xformable(prim)
            translate_op = None
            for op in xformable.GetOrderedXformOps():
                if op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
                    translate_op = op
                    break

            if not translate_op:
                # TranslateOpが存在しない場合、PhysXシミュレーション中は作成できない
                carb.log_error(f"{LOG_PREFIX} No TranslateOp found on {prim_path}")
                carb.log_error(f"{LOG_PREFIX} Cannot create TranslateOp during PhysX simulation (causes mutex error)")
                carb.log_error(f"{LOG_PREFIX} Please ensure proxy object has TranslateOp before simulation")
                return

            translate_op.Set(Gf.Vec3f(position[0], position[1], position[2]))
            carb.log_info(f"{LOG_PREFIX} Moved {prim_path} to {position}")

        except Exception as e:
            carb.log_error(f"{LOG_PREFIX} Error moving object {prim_path}: {e}")
            import traceback
            traceback.print_exc()

    def cleanup_all_on_simulation_stop(self, stage) -> int:
        """
        シミュレーション停止時のクリーンアップ
        プロキシシステムで配置されたオブジェクトを処理

        Args:
            stage: USD Stage

        Returns:
            int: クリーンアップしたオブジェクト数
        """
        try:
            cleanup_count = 0

            for slot_id, state in self._states.items():
                if state.state == PlacementState.PLACED or state.state == PlacementState.DETACHABLE:
                    carb.log_info(f"{LOG_PREFIX} Cleaning up slot: {slot_id}")

                    # Real objectを非表示にし、collision無効化
                    if state.real_path:
                        self._set_visibility(stage, state.real_path, visible=False)
                        self._set_collision_enabled(stage, state.real_path, enabled=False)
                        carb.log_info(f"{LOG_PREFIX} Hidden and disabled collision for: {state.real_path}")

                    # 状態をIDLEにリセット
                    state.state = PlacementState.IDLE
                    state.task_completed = False

                    cleanup_count += 1

            carb.log_info(f"{LOG_PREFIX} Proxy system cleanup: {cleanup_count} objects processed")
            return cleanup_count

        except Exception as e:
            carb.log_error(f"{LOG_PREFIX} Error in cleanup_all_on_simulation_stop: {e}")
            import traceback
            traceback.print_exc()
            return 0


# グローバルインスタンス
_state_manager_instance = None


def get_placement_state_manager():
    """PlacementStateManagerのグローバルインスタンスを取得"""
    global _state_manager_instance
    if _state_manager_instance is None:
        _state_manager_instance = PlacementStateManager()
    return _state_manager_instance
