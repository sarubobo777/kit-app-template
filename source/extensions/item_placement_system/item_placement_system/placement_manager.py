# SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

"""
Placement Manager System
アイテムの設置・検証・管理を行うメインシステム
"""

import omni.usd
import omni.timeline
import omni.kit.app
import typing
from pxr import Usd, UsdGeom, UsdPhysics, PhysxSchema, Gf, Sdf
from .machine_status import get_machine_status, MachineStatus


class TriggerMonitor:
    """
    PhysX Trigger APIを使用したトリガー監視クラス
    """
    def __init__(self, trigger_path: str, slot_id: str, expected_item_numbers: list,
                 display_name: str = "", target_parent_path: str = "", target_position: tuple = (0, 0, 0)):
        self.trigger_path = trigger_path
        self.slot_id = slot_id
        self.expected_item_numbers = expected_item_numbers
        self.display_name = display_name or slot_id
        self.target_parent_path = target_parent_path  # 正解プリムの移動先親パス
        self.target_position = target_position  # 正解プリムの移動先座標
        self.trigger_state_api = None
        self.previous_colliders = set()
        self.debug_enabled = True  # デバッグ出力を有効化

    def initialize(self, stage: Usd.Stage) -> bool:
        """
        トリガーを初期化

        Returns:
            bool: 初期化成功フラグ
        """
        try:
            print(f"[TriggerMonitor] トリガー初期化開始: {self.display_name}")
            print(f"  パス: {self.trigger_path}")

            trigger_prim = stage.GetPrimAtPath(self.trigger_path)
            if not trigger_prim.IsValid():
                print(f"[TriggerMonitor] ERROR: トリガーPrimが見つかりません: {self.trigger_path}")
                return False

            print(f"[TriggerMonitor] トリガーPrimは有効です")

            # PhysxTriggerAPIの確認
            has_trigger_api = trigger_prim.HasAPI(PhysxSchema.PhysxTriggerAPI)
            has_collision_api = trigger_prim.HasAPI(UsdPhysics.CollisionAPI)
            has_trigger_state_api = trigger_prim.HasAPI(PhysxSchema.PhysxTriggerStateAPI)

            print(f"  PhysxTriggerAPI: {'✓' if has_trigger_api else '✗'}")
            print(f"  CollisionAPI: {'✓' if has_collision_api else '✗'}")
            print(f"  PhysxTriggerStateAPI: {'✓' if has_trigger_state_api else '✗'}")

            # PhysxTriggerStateAPIを取得（既にUIで設定済みと仮定）
            self.trigger_state_api = PhysxSchema.PhysxTriggerStateAPI(trigger_prim)

            # TriggerStateAPIが適用されていない場合は適用
            if not has_trigger_state_api:
                self.trigger_state_api = PhysxSchema.PhysxTriggerStateAPI.Apply(trigger_prim)
                print(f"[TriggerMonitor] PhysxTriggerStateAPIを適用しました: {self.trigger_path}")

            # トリガーの状態を確認（正しいメソッド名はGetTriggeredCollisionsRel）
            triggered_rel = self.trigger_state_api.GetTriggeredCollisionsRel()
            print(f"[TriggerMonitor] TriggeredCollisionsRel取得成功: {triggered_rel}")

            print(f"[TriggerMonitor] ✓ トリガー初期化完了: {self.display_name} -> スロット: {self.slot_id}")
            return True

        except Exception as e:
            print(f"[TriggerMonitor] トリガー初期化エラー ({self.trigger_path}): {e}")
            import traceback
            traceback.print_exc()
            return False

    def check_trigger_state(self, stage: Usd.Stage) -> tuple[list, list]:
        """
        トリガー状態をチェックし、Enter/Leaveしたオブジェクトを返す

        Returns:
            tuple[list, list]: (entered_paths, left_paths)
        """
        if not self.trigger_state_api:
            if self.debug_enabled:
                print(f"[TriggerMonitor] WARNING: trigger_state_api is None for {self.trigger_path}")
            return [], []

        try:
            # 現在トリガー内にあるColliderを取得（正しいメソッド名はGetTriggeredCollisionsRel）
            triggered_rel = self.trigger_state_api.GetTriggeredCollisionsRel()
            current_colliders_list = triggered_rel.GetTargets()
            current_colliders = set(current_colliders_list)

            # デバッグ：トリガー内のオブジェクト数を表示（Enter/Leave時のみ）
            # if self.debug_enabled and len(current_colliders) > 0:
            #     print(f"[TriggerMonitor] {self.display_name} ({self.trigger_path}): 検知中のオブジェクト数 = {len(current_colliders)}")
            #     for collider_path in current_colliders:
            #         print(f"  - {collider_path}")

            # Enter検知（新しく入ったオブジェクト）
            entered = list(current_colliders - self.previous_colliders)

            # Leave検知（出て行ったオブジェクト）
            left = list(self.previous_colliders - current_colliders)

            # デバッグ：Enter/Leave検知
            if self.debug_enabled:
                if len(entered) > 0:
                    print(f"[TriggerMonitor] {self.display_name}: ENTER検知 - {len(entered)} 個")
                    for path in entered:
                        print(f"  ENTER -> {path}")
                if len(left) > 0:
                    print(f"[TriggerMonitor] {self.display_name}: LEAVE検知 - {len(left)} 個")
                    for path in left:
                        print(f"  LEAVE <- {path}")

            # 状態更新
            self.previous_colliders = current_colliders

            return entered, left

        except Exception as e:
            print(f"[TriggerMonitor] トリガー状態チェックエラー ({self.trigger_path}): {e}")
            import traceback
            traceback.print_exc()
            return [], []

class PlacementSlot:
    """
    設置スロットの情報を管理するクラス
    """
    def __init__(self, slot_id: str, name: str, position: tuple, allowed_items: list,
                 scenario_requirements: dict = None):
        self.slot_id = slot_id
        self.name = name
        self.position = position  # 設置位置 (x, y, z)
        self.allowed_items = allowed_items  # 許可されたアイテム番号のリスト
        self.scenario_requirements = scenario_requirements or {}  # シナリオ進行度による制限
        self.current_item = None  # 現在設置されているアイテム
        self.is_occupied = False

        # 物理設定
        self.detection_radius = 2.0  # 検出範囲
        self.force_threshold = 50.0  # 取り外しに必要な力の閾値

    def can_accept_item(self, item_number: int, current_scenario_step: int = 0) -> tuple[bool, str]:
        """
        アイテムが設置可能かチェック

        Args:
            item_number: アイテム番号
            current_scenario_step: 現在のシナリオステップ

        Returns:
            tuple[bool, str]: (設置可能かどうか, エラーメッセージ)
        """
        # スロットが占有されているかチェック
        if self.is_occupied:
            return False, f"スロット '{self.name}' は既に使用中です"

        # 基本的なアイテム許可チェック
        if item_number not in self.allowed_items:
            return False, f"アイテム番号 {item_number} はこのスロットに設置できません"

        # シナリオ進行度による制限チェック
        if self.scenario_requirements:
            required_step = self.scenario_requirements.get(item_number, 0)
            if current_scenario_step < required_step:
                return False, f"シナリオ進行度 {required_step} 以上で設置可能です（現在: {current_scenario_step}）"

        return True, ""

class ItemPlacementManager:
    """
    アイテム設置システムのメインマネージャー
    """

    def __init__(self):
        self._stage = None
        self._timeline = None
        self._machine_status = get_machine_status()

        # 設置スロットの設定
        self._placement_slots = self._initialize_placement_slots()

        # アイテムの初期位置記録
        self._item_initial_positions = {}

        # UI フィードバックシステム
        self._ui_feedback_callbacks = []

        # フォース監視用
        self._force_monitoring_enabled = True
        self._force_check_interval = 30  # フレーム間隔
        self._force_check_counter = 0

        # PhysX Trigger監視システム
        self._trigger_monitors = []
        self._trigger_enabled = True
        self._trigger_check_interval = 10  # トリガーチェック間隔（フレーム）
        self._trigger_check_counter = 0

        print("[PlacementManager] システム初期化完了")

    def _initialize_placement_slots(self) -> dict:
        """
        設置スロットの初期化

        Returns:
            dict: スロットID -> PlacementSlot のマッピング
        """
        slots = {}

        # スロット1: ドリル設置場所
        slots["drill_mount"] = PlacementSlot(
            slot_id="drill_mount",
            name="ドリル取り付け部",
            position=(75, 115, -70),  # ここに入力してください: 実際の設置位置
            allowed_items=[1, 2],  # ここに入力してください: 許可されたアイテム番号
            scenario_requirements={1: 0, 2: 1}  # アイテム番号: 必要シナリオステップ
        )

        # スロット2: ワークピース設置場所
        slots["workpiece_mount"] = PlacementSlot(
            slot_id="workpiece_mount",
            name="ワークピース固定台",
            position=(85, 115, -70),  # ここに入力してください: 実際の設置位置
            allowed_items=[3, 4],  # ここに入力してください: 許可されたアイテム番号
            scenario_requirements={3: 0, 4: 0}
        )

        # スロット3: 安全ガード
        slots["safety_guard"] = PlacementSlot(
            slot_id="safety_guard",
            name="安全ガード",
            position=(95, 115, -70),  # 安全ガード設置位置
            allowed_items=[5],  # 安全ガードアイテム
            scenario_requirements={5: 0}
        )

        # スロット4: クーラント供給装置
        slots["coolant_system"] = PlacementSlot(
            slot_id="coolant_system",
            name="クーラント装置",
            position=(105, 115, -70),  # クーラント装置設置位置
            allowed_items=[6, 7],  # クーラント関連アイテム
            scenario_requirements={6: 0, 7: 1}
        )

        return slots

    def initialize_usd_connection(self):
        """
        USD Stage との接続を初期化
        """
        try:
            self._stage = omni.usd.get_context().get_stage()
            self._timeline = omni.timeline.get_timeline_interface()

            if self._stage:
                print("[PlacementManager] USD Stage接続完了")
                self._scan_initial_item_positions()
                self._initialize_trigger_monitors()
            else:
                print("[PlacementManager] USD Stage接続失敗")

        except Exception as e:
            print(f"[PlacementManager] 初期化エラー: {e}")

    def _initialize_trigger_monitors(self):
        """
        PhysX Triggerモニターの初期化
        """
        if not self._stage:
            return

        # トリガーパスとスロットのマッピング
        trigger_configs = [
            {
                "path": "/World/New_MillingMachine/Main/Doril/Trigger_Drill",
                "slot_id": "drill_mount",
                "display_name": "ドリルチャック",
                "expected_items": [1, 2],
                "target_parent_path": "/World/New_MillingMachine/Main/Doril",
                "target_position": (0.015432648818485717, -0.013736448036276452, -0.9882536584245827)
            },
            {
                "path": "/World/New_MillingMachine/Table/Set_Base/Trigger_Table",
                "slot_id": "workpiece_mount",
                "display_name": "テーブル",
                "expected_items": [3, 4],
                "target_parent_path": "/World/New_MillingMachine/Table/Set_Base",
                "target_position": (-8.303561985568642, 105.69149619771949, -119.22765869190322)
            },
            {
                "path": "/World/Industrial/Industrial/Trigger_Plug",
                "slot_id": "safety_guard",
                "display_name": "電源",
                "expected_items": [5],
                "target_parent_path": "/World/Industrial/Industrial",
                "target_position": (117.73048706357947, -3.6861373143285903, 81.84444102267189)
            },
            {
                "path": "/World/New_MillingMachine/Table/Set_Base/Bolt/Trigger_Bolt",
                "slot_id": "coolant_system",
                "display_name": "固定台ボルト",
                "expected_items": [6, 7],
                "target_parent_path": "/World/New_MillingMachine/Table/Set_Base",
                "target_position": (-3.204076253459357, 0.23429412264234561, -2.960320652122478)
            }
        ]

        # トリガーモニターを作成
        for config in trigger_configs:
            monitor = TriggerMonitor(
                trigger_path=config["path"],
                slot_id=config["slot_id"],
                expected_item_numbers=config["expected_items"],
                display_name=config["display_name"],
                target_parent_path=config["target_parent_path"],
                target_position=config["target_position"]
            )

            if monitor.initialize(self._stage):
                self._trigger_monitors.append(monitor)
                print(f"[PlacementManager] トリガーモニター追加: {config['display_name']} ({config['path']}) -> {config['slot_id']}")
            else:
                print(f"[PlacementManager] トリガーモニター初期化失敗: {config['display_name']} ({config['path']})")

        print(f"[PlacementManager] {len(self._trigger_monitors)} 個のトリガーモニターを初期化しました")

    def _scan_initial_item_positions(self):
        """
        アイテムの初期位置をスキャンして記録
        """
        # ここに入力してください: 机の上のアイテムのベースパス
        table_base_path = "/World/ItemTray"  # 例: "/World/Table/Items"

        if not self._stage:
            return

        table_prim = self._stage.GetPrimAtPath(table_base_path)
        if not table_prim.IsValid():
            print(f"[PlacementManager] テーブルパス {table_base_path} が見つかりません")
            return

        # テーブル上のアイテムをスキャン
        for child in table_prim.GetChildren():
            # Number属性をチェック
            if child.HasAttribute("Number"):
                number_attr = child.GetAttribute("Number")
                item_number = number_attr.Get()

                if item_number is not None:
                    # 初期位置を記録
                    xform = UsdGeom.Xformable(child)
                    if xform:
                        transform_matrix = xform.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
                        position = transform_matrix.ExtractTranslation()
                        self._item_initial_positions[child.GetPath()] = position

                        print(f"[PlacementManager] アイテム {item_number} の初期位置を記録: {position}")

    def on_timeline_event(self, event):
        """
        タイムラインイベントのハンドリング（トリガー監視・フォース監視用）
        """
        if event.type == int(omni.timeline.TimelineEventType.CURRENT_TIME_TICKED):
            # トリガー検知
            if self._trigger_enabled:
                self._check_trigger_events()

            # フォース監視
            if self._force_monitoring_enabled:
                self._check_force_removal()

    def _check_trigger_events(self):
        """
        PhysX Triggerイベントをチェックして自動配置を実行
        """
        self._trigger_check_counter += 1
        if self._trigger_check_counter < self._trigger_check_interval:
            return

        self._trigger_check_counter = 0

        # デバッグ：トリガーチェックが実行されていることを確認
        # print(f"[PlacementManager] トリガーチェック実行中... (モニター数: {len(self._trigger_monitors)})")

        if not self._stage:
            print(f"[PlacementManager] WARNING: Stage is None, トリガーチェックをスキップ")
            return

        if len(self._trigger_monitors) == 0:
            print(f"[PlacementManager] WARNING: トリガーモニターが0個です")
            return

        # 各トリガーモニターをチェック
        for monitor in self._trigger_monitors:
            entered_paths, left_paths = monitor.check_trigger_state(self._stage)

            # Enter検知：トリガーに入ったアイテムを自動配置
            for item_path in entered_paths:
                self._handle_trigger_enter(item_path, monitor)

            # Leave検知：トリガーから出たアイテム（必要に応じて処理）
            for item_path in left_paths:
                self._handle_trigger_leave(item_path, monitor)

    def _handle_trigger_enter(self, item_path: str, monitor: TriggerMonitor):
        """
        トリガーEnterイベント処理：アイテムを自動的に配置

        Args:
            item_path: トリガーに入ったアイテムのパス（例: /World/ItemTray/Drill/Drill/_______001）
                      → 2階層遡って /World/ItemTray/Drill/Drill を取得
            monitor: トリガーモニター
        """
        try:
            print(f"[PlacementManager] === トリガーEnter処理開始 ===")
            print(f"  アイテムパス: {item_path}")
            print(f"  トリガー: {monitor.display_name} ({monitor.trigger_path})")
            print(f"  期待アイテム番号: {monitor.expected_item_numbers}")

            item_prim = self._stage.GetPrimAtPath(item_path)
            if not item_prim.IsValid():
                print(f"[PlacementManager] ERROR: アイテムPrimが無効です: {item_path}")
                return

            # Number属性チェック
            if not item_prim.HasAttribute("Number"):
                print(f"[PlacementManager] WARNING: Number属性が存在しません ({item_path})")
                self._show_ui_feedback(
                    f"アイテムにNumber属性がありません: {item_path}",
                    "error"
                )
                # 不正解プリムとして処理
                self._handle_incorrect_item(item_path)
                return

            item_number = item_prim.GetAttribute("Number").Get()
            print(f"[PlacementManager] Number属性取得: {item_number}")

            if item_number is None:
                print(f"[PlacementManager] ERROR: Number属性の値がNoneです")
                self._handle_incorrect_item(item_path)
                return

            # 正解/不正解のチェック
            if item_number in monitor.expected_item_numbers:
                # 正解プリムの処理
                print(f"[PlacementManager] ✓ 正解アイテム検知: Number {item_number}")
                success = self._handle_correct_item(item_path, monitor, item_number)

                if success:
                    self._show_ui_feedback(
                        f"{monitor.display_name}にアイテム {item_number} を配置しました",
                        "success"
                    )
                else:
                    self._show_ui_feedback(
                        f"配置処理でエラーが発生しました",
                        "error"
                    )
            else:
                # 不正解プリムの処理
                print(f"[PlacementManager] ✗ 不正解アイテム検知: Number {item_number}")
                print(f"  期待される番号: {monitor.expected_item_numbers}")
                self._show_ui_feedback(
                    f"アイテム {item_number} は{monitor.display_name}に設置できません",
                    "warning"
                )
                self._handle_incorrect_item(item_path)

        except Exception as e:
            print(f"[PlacementManager] トリガーEnter処理エラー: {e}")
            import traceback
            traceback.print_exc()

    def _get_parent_path_up_n_levels(self, path_str: str, levels: int = 2) -> str:
        """
        パスをN階層遡る

        Args:
            path_str: 元のパス（例: /World/ItemTray/Drill/Drill/_______001）
            levels: 遡る階層数（デフォルト2）

        Returns:
            str: 遡ったパス（例: /World/ItemTray/Drill/Drill）
        """
        path = Sdf.Path(path_str)
        for _ in range(levels):
            path = path.GetParentPath()
        return str(path)

    def _handle_correct_item(self, item_path: str, monitor: TriggerMonitor, item_number: int) -> bool:
        """
        正解プリムの処理

        Args:
            item_path: アイテムのパス
            monitor: トリガーモニター
            item_number: アイテム番号

        Returns:
            bool: 成功フラグ
        """
        try:
            print(f"[PlacementManager] 正解プリム処理開始: {item_path}")

            # 1. パスを2つ戻る（例: /World/ItemTray/Drill/Drill/_______001 → /World/ItemTray/Drill/Drill）
            parent_path_str = self._get_parent_path_up_n_levels(item_path, 2)
            print(f"  1. パスを2つ遡る: {item_path} → {parent_path_str}")

            parent_prim = self._stage.GetPrimAtPath(parent_path_str)
            if not parent_prim.IsValid():
                print(f"[PlacementManager] ERROR: 親Primが無効です: {parent_path_str}")
                return False

            # 2. 物理機能を無効にする
            print(f"  2. 物理機能を無効化")
            self._disable_physics(parent_prim)

            # 3. 正解プリムを指定パスと座標に移動
            # 親パスを変更: /World/ItemTray/Drill/Drill → /World/New_MillingMachine/Main/Doril/Drill
            parent_name = parent_prim.GetName()  # "Drill"
            new_parent_path = f"{monitor.target_parent_path}/{parent_name}"
            print(f"  3. 移動先: {new_parent_path}")
            print(f"     座標: {monitor.target_position}")

            # Primを新しい親に移動（Reparent）
            success = self._reparent_prim(parent_prim, monitor.target_parent_path, monitor.target_position)

            if success:
                print(f"[PlacementManager] ✓ 正解プリム配置完了: {new_parent_path}")
                # MachineStatusに通知
                self._machine_status.on_item_placed(item_number, monitor.slot_id)
                return True
            else:
                print(f"[PlacementManager] ✗ 正解プリム配置失敗")
                return False

        except Exception as e:
            print(f"[PlacementManager] 正解プリム処理エラー: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _handle_incorrect_item(self, item_path: str):
        """
        不正解プリムの処理

        Args:
            item_path: アイテムのパス
        """
        try:
            print(f"[PlacementManager] 不正解プリム処理開始: {item_path}")

            # 1. パスを2つ戻る
            parent_path_str = self._get_parent_path_up_n_levels(item_path, 2)
            print(f"  1. パスを2つ遡る: {item_path} → {parent_path_str}")

            parent_prim = self._stage.GetPrimAtPath(parent_path_str)
            if not parent_prim.IsValid():
                print(f"[PlacementManager] ERROR: 親Primが無効です: {parent_path_str}")
                return

            # 2. (0, 0, 0)に移動
            print(f"  2. 座標を(0, 0, 0)に移動")
            self._move_prim_to_position(parent_prim, (0, 0, 0))

            print(f"[PlacementManager] ✓ 不正解プリム処理完了")

        except Exception as e:
            print(f"[PlacementManager] 不正解プリム処理エラー: {e}")
            import traceback
            traceback.print_exc()

    def _disable_physics(self, prim: Usd.Prim):
        """
        Primの物理機能を無効化

        注意: ドリルなど、動作が必要なPrimは物理を無効化しない

        Args:
            prim: 対象Prim
        """
        try:
            # ドリルの場合は物理を無効化しない（voxel_carverで使用するため）
            prim_name_lower = prim.GetName().lower()
            if "drill" in prim_name_lower or "carver" in prim_name_lower:
                print(f"    - スキップ: ドリルのため物理を保持します: {prim.GetPath()}")
                return

            # RigidBodyAPIを無効化
            if prim.HasAPI(UsdPhysics.RigidBodyAPI):
                rigid_body = UsdPhysics.RigidBodyAPI(prim)
                # キネマティックに設定（物理シミュレーションから除外）
                rigid_body.GetKinematicEnabledAttr().Set(True)
                print(f"    - RigidBodyをキネマティック化: {prim.GetPath()}")

            # 子Primの物理も無効化（ただしドリル以外）
            for child in prim.GetChildren():
                child_name_lower = child.GetName().lower()
                if "drill" in child_name_lower or "carver" in child_name_lower:
                    print(f"    - スキップ: ドリル子Primのため物理を保持します: {child.GetPath()}")
                    continue

                if child.HasAPI(UsdPhysics.RigidBodyAPI):
                    child_rigid_body = UsdPhysics.RigidBodyAPI(child)
                    child_rigid_body.GetKinematicEnabledAttr().Set(True)

        except Exception as e:
            print(f"[PlacementManager] 物理無効化エラー: {e}")

    def _reparent_prim(self, prim: Usd.Prim, new_parent_path: str, position: tuple) -> bool:
        """
        Primを新しい親に移動し、座標を設定

        Args:
            prim: 移動するPrim
            new_parent_path: 新しい親のパス
            position: 移動先座標

        Returns:
            bool: 成功フラグ
        """
        try:
            from pxr import Sdf

            # 新しいパスを作成
            prim_name = prim.GetName()
            new_path = f"{new_parent_path}/{prim_name}"

            print(f"    - Reparent: {prim.GetPath()} → {new_path}")

            # Primを移動（SdfCopySpec使用）
            edit = Sdf.BatchNamespaceEdit()
            edit.Add(prim.GetPath(), Sdf.Path(new_path))

            if self._stage.GetRootLayer().Apply(edit):
                # 移動後のPrimを取得
                moved_prim = self._stage.GetPrimAtPath(new_path)
                if moved_prim.IsValid():
                    # 座標を設定
                    self._move_prim_to_position(moved_prim, position)
                    print(f"    - 移動成功: {new_path}")
                    return True
                else:
                    print(f"    - ERROR: 移動後のPrimが無効: {new_path}")
                    return False
            else:
                print(f"    - ERROR: Reparent失敗")
                return False

        except Exception as e:
            print(f"[PlacementManager] Reparentエラー: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _move_prim_to_position(self, prim: Usd.Prim, position: tuple):
        """
        Primを指定座標に移動

        Args:
            prim: 対象Prim
            position: 移動先座標 (x, y, z)
        """
        try:
            xform = UsdGeom.Xformable(prim)
            if xform:
                # 既存のTransform操作をクリア
                xform.ClearXformOpOrder()

                # 新しい位置を設定
                translate_op = xform.AddTranslateOp()
                translate_op.Set(Gf.Vec3d(position[0], position[1], position[2]))

                print(f"    - 座標設定: {position}")

        except Exception as e:
            print(f"[PlacementManager] 座標移動エラー: {e}")

    def _handle_trigger_leave(self, item_path: str, monitor: TriggerMonitor):
        """
        トリガーLeaveイベント処理

        Args:
            item_path: トリガーから出たアイテムのパス
            monitor: トリガーモニター
        """
        # 必要に応じてLeave時の処理を実装
        print(f"[PlacementManager] トリガーLeave検知: {item_path} <- {monitor.slot_id}")

    def _check_force_removal(self):
        """
        設置されたアイテムにかかる力をチェックして取り外し判定
        """
        self._force_check_counter += 1
        if self._force_check_counter < self._force_check_interval:
            return

        self._force_check_counter = 0

        for slot in self._placement_slots.values():
            if slot.is_occupied and slot.current_item:
                if self._check_item_force(slot.current_item, slot.force_threshold):
                    print(f"[PlacementManager] 力による取り外し検出: {slot.name}")
                    self._force_remove_item(slot)

    def _check_item_force(self, item_path: str, threshold: float) -> bool:
        """
        アイテムにかかる力をチェック

        Args:
            item_path: アイテムのUSDパス
            threshold: 力の閾値

        Returns:
            bool: 閾値を超える力がかかっているかどうか
        """
        if not self._stage:
            return False

        try:
            item_prim = self._stage.GetPrimAtPath(item_path)
            if not item_prim.IsValid():
                return False

            # RigidBodyAPIの確認
            if item_prim.HasAPI(UsdPhysics.RigidBodyAPI):
                rigid_body = UsdPhysics.RigidBodyAPI(item_prim)

                # PhysXからの力情報取得（実装は環境依存）
                # ここに入力してください: 実際の力取得ロジック
                # 例: PhysXからの力ベクトル取得
                # force_vector = get_applied_force(item_prim)
                # force_magnitude = force_vector.GetLength()
                # return force_magnitude > threshold

                # 仮実装: 位置変化による簡易判定
                current_pos = self._get_item_current_position(item_path)
                expected_pos = self._get_item_expected_position(item_path)

                if current_pos and expected_pos:
                    distance = (current_pos - expected_pos).GetLength()
                    return distance > 0.1  # 10cm以上移動したら取り外しとみなす

        except Exception as e:
            print(f"[PlacementManager] 力チェックエラー: {e}")

        return False

    def _get_item_current_position(self, item_path: str):
        """
        アイテムの現在位置を取得
        """
        if not self._stage:
            return None

        try:
            item_prim = self._stage.GetPrimAtPath(item_path)
            if item_prim.IsValid():
                xform = UsdGeom.Xformable(item_prim)
                if xform:
                    transform_matrix = xform.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
                    return transform_matrix.ExtractTranslation()
        except Exception as e:
            print(f"[PlacementManager] 位置取得エラー: {e}")

        return None

    def _get_item_expected_position(self, item_path: str):
        """
        アイテムの期待位置を取得（設置されている場合はスロット位置）
        """
        for slot in self._placement_slots.values():
            if slot.current_item == item_path:
                return Gf.Vec3d(slot.position)
        return None

    def attempt_place_item(self, item_path: str, target_slot_id: str) -> tuple[bool, str]:
        """
        アイテムの設置を試行

        Args:
            item_path: 設置するアイテムのUSDパス
            target_slot_id: 目標スロットID

        Returns:
            tuple[bool, str]: (成功フラグ, メッセージ)
        """
        if not self._stage:
            return False, "USD Stageが利用できません"

        # アイテムの有効性チェック
        item_prim = self._stage.GetPrimAtPath(item_path)
        if not item_prim.IsValid():
            return False, f"アイテム {item_path} が見つかりません"

        # Number属性の取得
        if not item_prim.HasAttribute("Number"):
            return False, f"アイテム {item_path} にNumber属性がありません"

        number_attr = item_prim.GetAttribute("Number")
        item_number = number_attr.Get()

        if item_number is None:
            return False, f"アイテム {item_path} のNumber属性が無効です"

        # スロットの有効性チェック
        if target_slot_id not in self._placement_slots:
            return False, f"スロット {target_slot_id} が見つかりません"

        slot = self._placement_slots[target_slot_id]

        # 設置可能性チェック
        can_place, error_msg = slot.can_accept_item(item_number, current_scenario_step=0)
        if not can_place:
            self._show_ui_feedback(f"設置失敗: {error_msg}", "error")
            self._return_item_to_initial_position(item_path)
            return False, error_msg

        # 実際の設置処理
        success = self._execute_placement(item_path, item_number, slot)

        if success:
            self._show_ui_feedback(f"設置成功: {slot.name}", "success")
            return True, f"アイテム {item_number} を {slot.name} に設置しました"
        else:
            self._show_ui_feedback("設置処理に失敗しました", "error")
            self._return_item_to_initial_position(item_path)
            return False, "設置処理エラー"

    def _execute_placement(self, item_path: str, item_number: int, slot: PlacementSlot) -> bool:
        """
        実際の設置処理を実行

        Args:
            item_path: アイテムパス
            item_number: アイテム番号
            slot: 設置スロット

        Returns:
            bool: 成功フラグ
        """
        try:
            item_prim = self._stage.GetPrimAtPath(item_path)

            # 1. アイテムを指定位置に移動
            xform = UsdGeom.Xformable(item_prim)
            if xform:
                # 位置設定
                target_position = Gf.Vec3d(slot.position)
                transform_matrix = Gf.Matrix4d()
                transform_matrix.SetTranslateOnly(target_position)

                xform.ClearXformOpOrder()
                translate_op = xform.AddTranslateOp()
                translate_op.Set(target_position)

            # 2. 物理を無効化（固定）
            if item_prim.HasAPI(UsdPhysics.RigidBodyAPI):
                rigid_body = UsdPhysics.RigidBodyAPI(item_prim)
                rigid_body.GetKinematicEnabledAttr().Set(True)  # キネマティックに設定

            # 3. スロット状態更新
            slot.current_item = item_path
            slot.is_occupied = True

            # 4. MachineStatusに通知
            self._machine_status.on_item_placed(item_number, slot.slot_id)

            print(f"[PlacementManager] 設置完了: アイテム {item_number} -> {slot.name}")
            return True

        except Exception as e:
            print(f"[PlacementManager] 設置実行エラー: {e}")
            return False

    def _force_remove_item(self, slot: PlacementSlot):
        """
        力による強制的なアイテム取り外し

        Args:
            slot: 対象スロット
        """
        if not slot.current_item:
            return

        try:
            item_path = slot.current_item
            item_prim = self._stage.GetPrimAtPath(item_path)

            if item_prim.IsValid():
                # 物理を再有効化
                if item_prim.HasAPI(UsdPhysics.RigidBodyAPI):
                    rigid_body = UsdPhysics.RigidBodyAPI(item_prim)
                    rigid_body.GetKinematicEnabledAttr().Set(False)  # 物理有効化

                # Number属性取得
                if item_prim.HasAttribute("Number"):
                    number_attr = item_prim.GetAttribute("Number")
                    item_number = number_attr.Get()

                    # MachineStatusに通知
                    self._machine_status.on_item_removed(item_number, slot.slot_id)

                # スロット状態更新
                slot.current_item = None
                slot.is_occupied = False

                self._show_ui_feedback(f"アイテムが外れました: {slot.name}", "warning")
                print(f"[PlacementManager] 力による取り外し: {slot.name}")

        except Exception as e:
            print(f"[PlacementManager] 強制取り外しエラー: {e}")

    def _return_item_to_initial_position(self, item_path: str):
        """
        アイテムを初期位置に戻す

        Args:
            item_path: アイテムパス
        """
        if item_path not in self._item_initial_positions:
            print(f"[PlacementManager] 初期位置が記録されていません: {item_path}")
            return

        try:
            item_prim = self._stage.GetPrimAtPath(item_path)
            if not item_prim.IsValid():
                return

            # 初期位置に戻す
            initial_position = self._item_initial_positions[item_path]
            xform = UsdGeom.Xformable(item_prim)

            if xform:
                xform.ClearXformOpOrder()
                translate_op = xform.AddTranslateOp()
                translate_op.Set(initial_position)

            # 物理を再有効化
            if item_prim.HasAPI(UsdPhysics.RigidBodyAPI):
                rigid_body = UsdPhysics.RigidBodyAPI(item_prim)
                rigid_body.GetKinematicEnabledAttr().Set(False)

            print(f"[PlacementManager] アイテムを初期位置に戻しました: {item_path}")

        except Exception as e:
            print(f"[PlacementManager] 初期位置復帰エラー: {e}")

    def remove_item(self, slot_id: str) -> tuple[bool, str]:
        """
        アイテムを手動で取り外し

        Args:
            slot_id: スロットID

        Returns:
            tuple[bool, str]: (成功フラグ, メッセージ)
        """
        if slot_id not in self._placement_slots:
            return False, f"スロット {slot_id} が見つかりません"

        slot = self._placement_slots[slot_id]

        if not slot.is_occupied:
            return False, f"スロット {slot.name} は空です"

        try:
            item_path = slot.current_item
            item_prim = self._stage.GetPrimAtPath(item_path)

            if item_prim.IsValid():
                # Number属性取得
                item_number = None
                if item_prim.HasAttribute("Number"):
                    number_attr = item_prim.GetAttribute("Number")
                    item_number = number_attr.Get()

                # 初期位置に戻す
                self._return_item_to_initial_position(item_path)

                # スロット状態更新
                slot.current_item = None
                slot.is_occupied = False

                # MachineStatusに通知
                if item_number is not None:
                    self._machine_status.on_item_removed(item_number, slot.slot_id)

                self._show_ui_feedback(f"取り外し完了: {slot.name}", "info")
                return True, f"アイテムを {slot.name} から取り外しました"
            else:
                return False, "アイテムが見つかりません"

        except Exception as e:
            print(f"[PlacementManager] 取り外しエラー: {e}")
            return False, f"取り外し処理エラー: {e}"

    def get_slot_status(self) -> dict:
        """
        全スロットの状態を取得

        Returns:
            dict: スロット状態の辞書
        """
        status = {}
        for slot_id, slot in self._placement_slots.items():
            status[slot_id] = {
                "name": slot.name,
                "occupied": slot.is_occupied,
                "current_item": slot.current_item,
                "allowed_items": slot.allowed_items
            }
        return status

    def add_ui_feedback_callback(self, callback):
        """
        UIフィードバックコールバックを追加

        Args:
            callback: フィードバック関数 (message: str, type: str) -> None
        """
        self._ui_feedback_callbacks.append(callback)

    def _show_ui_feedback(self, message: str, feedback_type: str):
        """
        UIフィードバックを表示

        Args:
            message: メッセージ
            feedback_type: フィードバックタイプ ("success", "error", "warning", "info")
        """
        print(f"[PlacementManager] UI Feedback ({feedback_type}): {message}")

        for callback in self._ui_feedback_callbacks:
            try:
                callback(message, feedback_type)
            except Exception as e:
                print(f"[PlacementManager] UIコールバックエラー: {e}")

    def detect_item_near_slot(self, item_path: str) -> typing.Optional[str]:
        """
        アイテムが設置スロットの近くにあるかチェック

        Args:
            item_path: アイテムパス

        Returns:
            Optional[str]: 近くにあるスロットID（なければNone）
        """
        current_position = self._get_item_current_position(item_path)
        if not current_position:
            return None

        for slot_id, slot in self._placement_slots.items():
            slot_position = Gf.Vec3d(slot.position)
            distance = (current_position - slot_position).GetLength()

            if distance <= slot.detection_radius:
                return slot_id

        return None

    # PhysX Trigger制御メソッド
    def enable_trigger_detection(self, enabled: bool = True):
        """
        トリガー検知の有効/無効を切り替え

        Args:
            enabled: 有効化フラグ
        """
        self._trigger_enabled = enabled
        status = "有効" if enabled else "無効"
        print(f"[PlacementManager] トリガー検知を{status}にしました")

    def diagnose_trigger_system(self):
        """
        トリガーシステムの診断情報を出力（デバッグ用）
        """
        print("=" * 60)
        print("[PlacementManager] トリガーシステム診断")
        print("=" * 60)
        print(f"トリガー検知: {'有効' if self._trigger_enabled else '無効'}")
        print(f"モニター数: {len(self._trigger_monitors)}")
        print(f"Stage: {'有効' if self._stage else '無効'}")
        print()

        for i, monitor in enumerate(self._trigger_monitors):
            print(f"--- トリガー {i+1}: {monitor.display_name} ---")
            print(f"  パス: {monitor.trigger_path}")
            print(f"  スロットID: {monitor.slot_id}")
            print(f"  期待アイテム: {monitor.expected_item_numbers}")
            print(f"  TriggerStateAPI: {'有効' if monitor.trigger_state_api else '無効'}")
            print(f"  現在検知中: {len(monitor.previous_colliders)} 個")

            if monitor.trigger_state_api and self._stage:
                try:
                    # 現在の状態を確認（正しいメソッド名はGetTriggeredCollisionsRel）
                    current_colliders = monitor.trigger_state_api.GetTriggeredCollisionsRel().GetTargets()
                    print(f"  リアルタイム検知数: {len(current_colliders)}")
                    if len(current_colliders) > 0:
                        print(f"  検知中のオブジェクト:")
                        for path in current_colliders:
                            item_prim = self._stage.GetPrimAtPath(path)
                            if item_prim.IsValid() and item_prim.HasAttribute("Number"):
                                item_number = item_prim.GetAttribute("Number").Get()
                                print(f"    - {path} (Number: {item_number})")
                            else:
                                print(f"    - {path} (Number属性なし)")
                except Exception as e:
                    print(f"  エラー: {e}")
            print()
        print("=" * 60)

    def get_trigger_status(self) -> dict:
        """
        トリガーシステムの状態を取得

        Returns:
            dict: トリガー状態情報
        """
        return {
            "enabled": self._trigger_enabled,
            "monitor_count": len(self._trigger_monitors),
            "monitors": [
                {
                    "trigger_path": m.trigger_path,
                    "slot_id": m.slot_id,
                    "display_name": m.display_name,
                    "expected_items": m.expected_item_numbers,
                    "active_colliders": len(m.previous_colliders)
                }
                for m in self._trigger_monitors
            ]
        }

# グローバルインスタンス
_placement_manager_instance = None

def get_placement_manager() -> ItemPlacementManager:
    """
    PlacementManagerのグローバルインスタンスを取得

    Returns:
        ItemPlacementManager: グローバルインスタンス
    """
    global _placement_manager_instance
    if _placement_manager_instance is None:
        _placement_manager_instance = ItemPlacementManager()
    return _placement_manager_instance