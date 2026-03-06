"""
Trigger Manager
トリガーベースのアイテム配置システムを管理

このモジュールは、PhysX Triggerの設定と状態管理を行います。
"""

import os
import carb
import omni.usd
from pxr import Usd, UsdPhysics, PhysxSchema, Sdf, Gf, UsdGeom
from typing import List, Dict, Optional, Tuple

LOG_PREFIX = "[ItemPlacement][TriggerManager]"


class ProxyMapping:
    """
    プロキシ（判定用）と実オブジェクト（表示用）のマッピング
    """
    def __init__(
        self,
        proxy_path: str,
        real_path: str,
        initial_hidden: bool = True
    ):
        """
        Args:
            proxy_path: RigidBody有りのダミーオブジェクトパス
            real_path: 実際に表示するオブジェクトパス
            initial_hidden: 初期状態で非表示にするか
        """
        self.proxy_path = proxy_path
        self.real_path = real_path
        self.initial_hidden = initial_hidden


class TriggerSlot:
    """
    個別のトリガースロット設定
    """
    def __init__(
        self,
        slot_id: str,
        trigger_path: str,
        correct_numbers: List[int],
        placement_translate: Tuple[float, float, float] = (0, 0, 0),
        placement_rotate: Tuple[float, float, float] = (0, 0, 0),
        placement_path: Optional[str] = None,
        proxy_mapping: Optional[ProxyMapping] = None,
        proxy_reset_position: Optional[Tuple[float, float, float]] = None,
        proxy_original_position: Optional[Tuple[float, float, float]] = None,
        task_type: str = 'none',
        scenario_id: int = 0,
        display_name: str = ""
    ):
        """
        Args:
            slot_id: スロットの一意識別子
            trigger_path: トリガーPrimのUSDパス
            correct_numbers: 正解とするNumber属性値のリスト
            placement_translate: 配置先のローカル座標（プロキシのリセット位置）
            placement_rotate: 配置時の回転角度（度数法、XYZ、デフォルト(0,0,0)）
            placement_path: 配置先の親パス（Noneの場合は現在の親を維持）
            proxy_mapping: プロキシと実オブジェクトのマッピング（Noneの場合は通常配置）
            proxy_reset_position: プロキシを隠す位置（デフォルト: (0, 100, 0)）
            proxy_original_position: プロキシの元の位置（取り外し時に戻る位置、デフォルト: (0, 0, 0)）
            task_type: タスクタイプ ('voxel_mesh', 'plug', 'none' など)
            scenario_id: シナリオID（将来の拡張用）
            display_name: UI表示用の名前
        """
        self.slot_id = slot_id
        self.trigger_path = trigger_path
        self.correct_numbers = correct_numbers
        self.placement_translate = placement_translate
        self.placement_rotate = placement_rotate
        self.placement_path = placement_path
        self.proxy_mapping = proxy_mapping
        self.proxy_reset_position = proxy_reset_position
        self.proxy_original_position = proxy_original_position
        self.task_type = task_type
        self.scenario_id = scenario_id
        self.display_name = display_name or slot_id


class TriggerManager:
    """
    トリガーベースのアイテム配置システムマネージャー
    """

    # デフォルトのトリガースロット設定
    #
    # 使用例:
    # - プロキシあり（Voxel Meshなど）:
    #   TriggerSlot(
    #       slot_id="voxel_mesh_slot",
    #       trigger_path="/World/.../Trigger_Table",
    #       correct_numbers=[1],
    #       placement_translate=(0, 100, 0),  # プロキシを遠くに隠す位置
    #       proxy_mapping=ProxyMapping(
    #           proxy_path="/World/Items/VoxelMesh_Proxy",  # RigidBody有り
    #           real_path="/World/.../VoxelMesh",           # 実際のVoxel Mesh
    #           initial_hidden=True
    #       ),
    #       task_type='voxel_mesh',  # タスクタイプ指定
    #       display_name="ワーク設置 (Number=1)"
    #   )
    #
    # - プロキシなし（通常配置）:
    #   TriggerSlot(
    #       slot_id="simple_slot",
    #       trigger_path="/World/.../Trigger",
    #       correct_numbers=[2],
    #       placement_translate=(20.0, 5.0, 0.0),  # 配置先座標
    #       task_type='none',  # タスクなし
    #       display_name="シンプル配置 (Number=2)"
    #   )
    DEFAULT_SLOTS = [
        TriggerSlot(
            slot_id="trigger_slot_1",
            trigger_path="/World/New_MillingMachine/Table/Set_Base/Trigger_Table",
            correct_numbers=[1],
            placement_translate=(10.0, 5.0, 0.0),
            proxy_mapping=None,
            task_type='none',    # タスクなし
            display_name="スロット1 (Number=1)"
        ),
        TriggerSlot(
            slot_id="trigger_slot_2",
            trigger_path="/World/New_MillingMachine/Main/Doril/Trigger_Drill",
            correct_numbers=[2],
            placement_translate=(20.0, 5.0, 0.0),
            display_name="スロット2 (Number=2)"
        ),
        TriggerSlot(
            slot_id="trigger_slot_3",
            trigger_path="/World/Industrial/Industrial/Trigger_Plug",
            correct_numbers=[3],
            placement_translate=(115.01953125, 84.44377958871065, -153.392956646741),
            #placement_rotate=(0, 45.0, 0.0),
            task_type='none',  # タスクなし
            display_name="スロット3 (Number=3)"
        ),
        TriggerSlot(
            slot_id="trigger_slot_4",
            trigger_path="/World/Triggers/TriggerSlot4",
            correct_numbers=[4],
            placement_translate=(40.0, 5.0, 0.0),
            display_name="スロット4 (Number=4)"
        ),
    ]

    def __init__(self):
        """初期化"""
        self._usd_context = omni.usd.get_context()
        self._slots: List[TriggerSlot] = []
        self._trigger_state_apis: Dict[str, PhysxSchema.PhysxTriggerStateAPI] = {}
        self._script_path = ""
        self._enabled = True
        self._scenario_controller = None  # 将来のシナリオコントローラー連携用

    def initialize(self):
        """
        トリガーマネージャーの初期化
        """
        try:
            carb.log_info(f"{LOG_PREFIX} Initializing TriggerManager...")

            # スクリプトパスを設定
            self._setup_script_path()

            # デフォルトスロットを読み込み
            self._slots = self.DEFAULT_SLOTS.copy()

            # トリガーをセットアップ
            self._setup_all_triggers()

            carb.log_info(f"{LOG_PREFIX} TriggerManager initialized with {len(self._slots)} slots")

        except Exception as e:
            carb.log_error(f"{LOG_PREFIX} Initialization error: {e}")
            import traceback
            traceback.print_exc()

    def _setup_script_path(self):
        """トリガースクリプトのパスを設定"""
        try:
            # 拡張機能ディレクトリからの相対パスでスクリプトを探す
            extension_path = os.path.dirname(os.path.abspath(__file__))
            script_name = "trigger_placement_script.py"
            self._script_path = os.path.join(extension_path, script_name)

            if not os.path.exists(self._script_path):
                carb.log_error(f"{LOG_PREFIX} Trigger script not found: {self._script_path}")
                return

            carb.log_info(f"{LOG_PREFIX} Using trigger script: {self._script_path}")

        except Exception as e:
            carb.log_error(f"{LOG_PREFIX} Error setting script path: {e}")

    def _setup_all_triggers(self):
        """すべてのトリガーをセットアップ"""
        stage = self._usd_context.get_stage()
        if not stage:
            carb.log_warn(f"{LOG_PREFIX} Stage not available")
            return

        # ⚠️ スクリプトパスチェックは廃止（TriggerStateAPI監視方式に移行）
        # if not self._script_path or not os.path.exists(self._script_path):
        #     carb.log_error(f"{LOG_PREFIX} Script path not valid: {self._script_path}")
        #     return

        setup_count = 0
        for slot in self._slots:
            success = self._setup_trigger(stage, slot)
            if success:
                setup_count += 1

        carb.log_info(f"{LOG_PREFIX} Setup complete: {setup_count}/{len(self._slots)} triggers configured")

    def _setup_trigger(self, stage: Usd.Stage, slot: TriggerSlot) -> bool:
        """
        個別のトリガーをセットアップ

        Args:
            stage: USD Stage
            slot: トリガースロット設定

        Returns:
            bool: セットアップ成功フラグ
        """
        try:
            trigger_prim = stage.GetPrimAtPath(slot.trigger_path)
            if not trigger_prim.IsValid():
                carb.log_warn(f"{LOG_PREFIX} Trigger prim not found: {slot.trigger_path}")
                return False

            carb.log_info(f"{LOG_PREFIX} Setting up trigger: {slot.trigger_path}")

            # CollisionAPIを適用（まだない場合）
            if not trigger_prim.HasAPI(UsdPhysics.CollisionAPI):
                UsdPhysics.CollisionAPI.Apply(trigger_prim)
                carb.log_info(f"{LOG_PREFIX}   - Applied CollisionAPI")

            # PhysxTriggerAPIを適用
            trigger_api = PhysxSchema.PhysxTriggerAPI.Apply(trigger_prim)

            # ⚠️ 重要：物理コールバックスクリプトは無効化
            # 理由：物理演算ステップ中にUSD変更を行うとメモリアクセス競合でクラッシュする
            # 新方式：TriggerStateAPIをUpdateループで監視して安全にUSD変更を行う
            #
            # # Enterイベントスクリプト設定（廃止）
            # trigger_api.CreateEnterScriptTypeAttr().Set(PhysxSchema.Tokens.scriptFile)
            # trigger_api.CreateOnEnterScriptAttr().Set(self._script_path)
            #
            # # Leaveイベントスクリプト設定（廃止）
            # trigger_api.CreateLeaveScriptTypeAttr().Set(PhysxSchema.Tokens.scriptFile)
            # trigger_api.CreateOnLeaveScriptAttr().Set(self._script_path)

            # TriggerStateAPIを適用（UpdateループでGetTriggeredCollisionsRel()を監視）
            trigger_state_api = PhysxSchema.PhysxTriggerStateAPI.Apply(trigger_prim)
            self._trigger_state_apis[slot.slot_id] = trigger_state_api

            # カスタム属性を設定（スクリプト側で参照）
            self._set_trigger_attributes(trigger_prim, slot)

            carb.log_info(f"{LOG_PREFIX}   - Trigger setup complete: {slot.display_name}")
            return True

        except Exception as e:
            carb.log_error(f"{LOG_PREFIX} Error setting up trigger {slot.trigger_path}: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _set_trigger_attributes(self, trigger_prim: Usd.Prim, slot: TriggerSlot):
        """
        トリガーにカスタム属性を設定

        Args:
            trigger_prim: トリガーPrim
            slot: スロット設定
        """
        try:
            # 正解のNumber値リスト
            correct_numbers_attr = trigger_prim.CreateAttribute(
                "custom:correct_numbers",
                Sdf.ValueTypeNames.IntArray,
                False
            )
            correct_numbers_attr.Set(slot.correct_numbers)

            # 配置先translate（正解時）
            placement_translate_attr = trigger_prim.CreateAttribute(
                "custom:placement_translate",
                Sdf.ValueTypeNames.Float3,
                False
            )
            placement_translate_attr.Set(Gf.Vec3f(*slot.placement_translate))

            # 配置時の回転角度（正解時、度数法、デフォルト: (0, 0, 0)）
            placement_rotate_attr = trigger_prim.CreateAttribute(
                "custom:placement_rotate",
                Sdf.ValueTypeNames.Float3,
                False
            )
            placement_rotate_attr.Set(Gf.Vec3f(*slot.placement_rotate))

            # 不正解時のリセット位置（デフォルト: (0, 0, 0)）
            translate_wrong_attr = trigger_prim.CreateAttribute(
                "custom:translate_wrong",
                Sdf.ValueTypeNames.Float3,
                False
            )
            translate_wrong_attr.Set(Gf.Vec3f(0, 0, 0))

            # 不正解時のリセット回転角度（デフォルト: (0, 0, 0)）
            rotate_wrong_attr = trigger_prim.CreateAttribute(
                "custom:rotate_wrong",
                Sdf.ValueTypeNames.Float3,
                False
            )
            rotate_wrong_attr.Set(Gf.Vec3f(0, 0, 0))

            # 配置先パス（設定されている場合）
            if slot.placement_path:
                placement_path_attr = trigger_prim.CreateAttribute(
                    "custom:placement_path",
                    Sdf.ValueTypeNames.String,
                    False
                )
                placement_path_attr.Set(slot.placement_path)

            # シナリオID
            scenario_id_attr = trigger_prim.CreateAttribute(
                "custom:scenario_id",
                Sdf.ValueTypeNames.Int,
                False
            )
            scenario_id_attr.Set(slot.scenario_id)

            # プロキシマッピング情報（設定されている場合）
            if slot.proxy_mapping:
                # プロキシパス
                proxy_path_attr = trigger_prim.CreateAttribute(
                    "custom:proxy_path",
                    Sdf.ValueTypeNames.String,
                    False
                )
                proxy_path_attr.Set(slot.proxy_mapping.proxy_path)

                # 実オブジェクトパス
                real_path_attr = trigger_prim.CreateAttribute(
                    "custom:real_path",
                    Sdf.ValueTypeNames.String,
                    False
                )
                real_path_attr.Set(slot.proxy_mapping.real_path)

                carb.log_info(f"{LOG_PREFIX}   - Proxy mapping set: {slot.proxy_mapping.proxy_path} -> {slot.proxy_mapping.real_path}")
            else:
                # proxy_mapping=Noneの場合、既存の属性をクリア
                proxy_path_attr = trigger_prim.GetAttribute("custom:proxy_path")
                if proxy_path_attr and proxy_path_attr.IsValid():
                    trigger_prim.RemoveProperty("custom:proxy_path")
                    carb.log_info(f"{LOG_PREFIX}   - Cleared custom:proxy_path attribute")

                real_path_attr = trigger_prim.GetAttribute("custom:real_path")
                if real_path_attr and real_path_attr.IsValid():
                    trigger_prim.RemoveProperty("custom:real_path")
                    carb.log_info(f"{LOG_PREFIX}   - Cleared custom:real_path attribute")

            # プロキシの元の位置（placement_translateから設定）
            proxy_original_pos_attr = trigger_prim.CreateAttribute(
                "custom:proxy_original_position",
                Sdf.ValueTypeNames.Float3,
                False
            )
            proxy_original_pos_attr.Set(Gf.Vec3f(*slot.placement_translate))

            # プロキシのリセット位置（デフォルト: 上空に隠す）
            proxy_reset_pos_attr = trigger_prim.CreateAttribute(
                "custom:proxy_reset_position",
                Sdf.ValueTypeNames.Float3,
                False
            )
            proxy_reset_pos_attr.Set(Gf.Vec3f(0, 100, 0))

            # タスクタイプ
            task_type_attr = trigger_prim.CreateAttribute(
                "custom:task_type",
                Sdf.ValueTypeNames.String,
                False
            )
            task_type_attr.Set(slot.task_type)

            # スロットID
            slot_id_attr = trigger_prim.CreateAttribute(
                "custom:slot_id",
                Sdf.ValueTypeNames.String,
                False
            )
            slot_id_attr.Set(slot.slot_id)

            carb.log_info(f"{LOG_PREFIX}   - Attributes set: correct_numbers={slot.correct_numbers}, task_type={slot.task_type}")

        except Exception as e:
            carb.log_error(f"{LOG_PREFIX} Error setting trigger attributes: {e}")

    def get_trigger_status(self) -> Dict:
        """
        トリガーシステムの現在の状態を取得

        Returns:
            Dict: トリガー状態情報
        """
        status = {
            "enabled": self._enabled,
            "slot_count": len(self._slots),
            "monitors": []
        }

        stage = self._usd_context.get_stage()
        if not stage:
            return status

        for slot in self._slots:
            monitor_info = {
                "slot_id": slot.slot_id,
                "display_name": slot.display_name,
                "trigger_path": slot.trigger_path,
                "expected_items": slot.correct_numbers,
                "active_colliders": 0,
                "collider_paths": []
            }

            # トリガー内のコライダーを取得
            trigger_state_api = self._trigger_state_apis.get(slot.slot_id)
            if trigger_state_api:
                try:
                    # 正しいメソッド名はGetTriggeredCollisionsRel
                    triggered_colliders = trigger_state_api.GetTriggeredCollisionsRel().GetTargets()
                    monitor_info["active_colliders"] = len(triggered_colliders)
                    monitor_info["collider_paths"] = [str(path) for path in triggered_colliders]
                except Exception as e:
                    carb.log_warn(f"{LOG_PREFIX} Error getting trigger state for {slot.slot_id}: {e}")

            status["monitors"].append(monitor_info)

        return status

    def get_all_slots(self) -> List[TriggerSlot]:
        """
        全てのトリガースロットを取得

        Returns:
            List[TriggerSlot]: トリガースロットのリスト
        """
        return self._slots

    def enable_trigger_detection(self, enabled: bool):
        """
        トリガー検知の有効/無効を切り替え

        Args:
            enabled: True=有効, False=無効
        """
        self._enabled = enabled
        carb.log_info(f"{LOG_PREFIX} Trigger detection {'enabled' if enabled else 'disabled'}")

    def diagnose_trigger_system(self):
        """トリガーシステムの診断情報を出力"""
        carb.log_info(f"{LOG_PREFIX} === Trigger System Diagnosis ===")
        carb.log_info(f"{LOG_PREFIX} Enabled: {self._enabled}")
        carb.log_info(f"{LOG_PREFIX} Script Path: {self._script_path}")
        carb.log_info(f"{LOG_PREFIX} Script Exists: {os.path.exists(self._script_path)}")
        carb.log_info(f"{LOG_PREFIX} Configured Slots: {len(self._slots)}")

        stage = self._usd_context.get_stage()
        if not stage:
            carb.log_warn(f"{LOG_PREFIX} Stage not available")
            return

        for i, slot in enumerate(self._slots, 1):
            carb.log_info(f"{LOG_PREFIX} --- Slot {i}: {slot.display_name} ---")
            carb.log_info(f"{LOG_PREFIX}   ID: {slot.slot_id}")
            carb.log_info(f"{LOG_PREFIX}   Trigger Path: {slot.trigger_path}")
            carb.log_info(f"{LOG_PREFIX}   Expected Numbers: {slot.correct_numbers}")
            carb.log_info(f"{LOG_PREFIX}   Placement: {slot.placement_translate}")

            # Primの存在確認
            trigger_prim = stage.GetPrimAtPath(slot.trigger_path)
            if trigger_prim.IsValid():
                carb.log_info(f"{LOG_PREFIX}   Prim Status: Valid ✅")

                # APIの確認
                has_collision = trigger_prim.HasAPI(UsdPhysics.CollisionAPI)
                has_trigger = trigger_prim.HasAPI(PhysxSchema.PhysxTriggerAPI)
                carb.log_info(f"{LOG_PREFIX}   CollisionAPI: {has_collision}")
                carb.log_info(f"{LOG_PREFIX}   PhysxTriggerAPI: {has_trigger}")

                # スクリプト設定確認
                if has_trigger:
                    trigger_api = PhysxSchema.PhysxTriggerAPI(trigger_prim)
                    enter_script = trigger_api.GetOnEnterScriptAttr().Get()
                    carb.log_info(f"{LOG_PREFIX}   Enter Script: {enter_script}")

                # カスタム属性確認
                correct_numbers_attr = trigger_prim.GetAttribute("custom:correct_numbers")
                if correct_numbers_attr.IsValid():
                    carb.log_info(f"{LOG_PREFIX}   Custom Attr 'correct_numbers': {correct_numbers_attr.Get()}")

            else:
                carb.log_warn(f"{LOG_PREFIX}   Prim Status: INVALID ❌")

        carb.log_info(f"{LOG_PREFIX} === Diagnosis Complete ===")

    def add_slot(self, slot: TriggerSlot):
        """
        新しいトリガースロットを追加

        Args:
            slot: 追加するスロット設定
        """
        self._slots.append(slot)
        stage = self._usd_context.get_stage()
        if stage:
            self._setup_trigger(stage, slot)
            carb.log_info(f"{LOG_PREFIX} Slot added: {slot.display_name}")

    def remove_slot(self, slot_id: str) -> bool:
        """
        トリガースロットを削除

        Args:
            slot_id: 削除するスロットID

        Returns:
            bool: 削除成功フラグ
        """
        for i, slot in enumerate(self._slots):
            if slot.slot_id == slot_id:
                del self._slots[i]
                if slot_id in self._trigger_state_apis:
                    del self._trigger_state_apis[slot_id]
                carb.log_info(f"{LOG_PREFIX} Slot removed: {slot_id}")
                return True
        return False

    def update_slot_from_scenario(self, slot_id: str, scenario_data: Dict):
        """
        シナリオコントローラーからのデータでスロットを更新（将来の拡張用）

        Args:
            slot_id: 更新するスロットID
            scenario_data: シナリオデータ
        """
        # TODO: シナリオコントローラー実装後に実装
        carb.log_info(f"{LOG_PREFIX} Scenario update for {slot_id}: {scenario_data}")


# グローバルインスタンス
_trigger_manager_instance: Optional[TriggerManager] = None


def get_trigger_manager() -> TriggerManager:
    """
    TriggerManagerのシングルトンインスタンスを取得

    Returns:
        TriggerManager: インスタンス
    """
    global _trigger_manager_instance
    if _trigger_manager_instance is None:
        _trigger_manager_instance = TriggerManager()
    return _trigger_manager_instance
