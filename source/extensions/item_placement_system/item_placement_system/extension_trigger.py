"""
Item Placement System Extension (Trigger-based)
トリガーベースのアイテム配置システム拡張機能

PhysX Triggerを使用して、アイテムの正誤判定と自動配置を行います。
プロキシ/本物オブジェクトシステムとタスクシステムをサポートします。
"""

import omni.ext
import omni.timeline
import omni.ui as ui
import carb
from .trigger_manager import get_trigger_manager, TriggerManager, TriggerSlot
from .task_manager import get_task_manager
from .placement_state_manager import get_placement_state_manager

LOG_PREFIX = "[ItemPlacement][Extension]"

# グローバル拡張機能インスタンス
_extension_instance = None


class ItemPlacementTriggerExtension(omni.ext.IExt):
    """
    トリガーベースのアイテム配置システム拡張機能
    """

    def __init__(self):
        super().__init__()
        self._trigger_manager: TriggerManager = None
        self._task_manager = None
        self._placement_state_manager = None
        self._timeline_subscription = None
        self._ui_window = None
        self._ui_update_counter = 0
        self._ui_update_interval = 30  # 30フレームごとにUI更新
        self._feedback_messages = []

        # 処理済みアイテム追跡（同じアイテムを複数回処理しないため）
        self._processed_items = set()  # {(trigger_path, item_path), ...}

    def on_startup(self, ext_id):
        """拡張機能起動時の処理"""
        global _extension_instance
        _extension_instance = self

        carb.log_info(f"{LOG_PREFIX} Starting Item Placement System (Trigger-based)...")

        try:
            # TaskManagerを取得して初期化
            self._task_manager = get_task_manager()
            carb.log_info(f"{LOG_PREFIX} TaskManager initialized")

            # PlacementStateManagerを取得して初期化
            self._placement_state_manager = get_placement_state_manager()
            self._placement_state_manager.set_task_manager(self._task_manager)
            carb.log_info(f"{LOG_PREFIX} PlacementStateManager initialized")

            # TriggerManagerを取得して初期化
            self._trigger_manager = get_trigger_manager()
            self._trigger_manager.initialize()
            carb.log_info(f"{LOG_PREFIX} TriggerManager initialized")

            # プロキシマッピングがあるスロットをPlacementStateManagerに登録
            self._register_proxy_slots()

            # タイムラインイベント購読
            timeline = omni.timeline.get_timeline_interface()
            self._timeline_subscription = timeline.get_timeline_event_stream().create_subscription_to_pop(
                self._on_timeline_event
            )

            # UIセットアップ
            self._setup_ui()

            carb.log_info(f"{LOG_PREFIX} Extension started successfully")

        except Exception as e:
            carb.log_error(f"{LOG_PREFIX} Startup error: {e}")
            import traceback
            traceback.print_exc()

    def on_shutdown(self):
        """拡張機能終了時の処理"""
        global _extension_instance

        carb.log_info(f"{LOG_PREFIX} Shutting down...")

        try:
            # タイムライン購読解除
            if self._timeline_subscription:
                self._timeline_subscription.unsubscribe()
                self._timeline_subscription = None

            # UI クリーンアップ
            if self._ui_window:
                self._ui_window.destroy()
                self._ui_window = None

            # インスタンスクリア
            _extension_instance = None

            carb.log_info(f"{LOG_PREFIX} Extension shutdown complete")

        except Exception as e:
            carb.log_error(f"{LOG_PREFIX} Shutdown error: {e}")

    def _register_proxy_slots(self):
        """プロキシマッピングがあるスロットをPlacementStateManagerに登録"""
        try:
            if not self._trigger_manager or not self._placement_state_manager:
                return

            # TriggerManagerからすべてのスロットを取得
            slots = self._trigger_manager._slots
            registered_count = 0

            for slot in slots:
                if slot.proxy_mapping:
                    # PlacementStateManagerに登録
                    self._placement_state_manager.register_object(
                        slot_id=slot.slot_id,
                        proxy_path=slot.proxy_mapping.proxy_path,
                        real_path=slot.proxy_mapping.real_path
                    )
                    registered_count += 1
                    carb.log_info(f"{LOG_PREFIX} Registered proxy slot: {slot.slot_id}")

            carb.log_info(f"{LOG_PREFIX} Registered {registered_count} proxy slots")

        except Exception as e:
            carb.log_error(f"{LOG_PREFIX} Error registering proxy slots: {e}")
            import traceback
            traceback.print_exc()

    def _on_timeline_event(self, event):
        """タイムラインイベントハンドラ"""
        # フレームごとの更新処理
        if event.type == int(omni.timeline.TimelineEventType.CURRENT_TIME_TICKED):
            # TriggerStateAPIを監視して安全にUSD変更を行う
            self._update_trigger_detection()

            # 定期的にUIを更新
            self._ui_update_counter += 1
            if self._ui_update_counter >= self._ui_update_interval:
                self._ui_update_counter = 0
                self._update_trigger_status_display()

        # シミュレーション開始時の処理
        elif event.type == int(omni.timeline.TimelineEventType.PLAY):
            carb.log_info(f"{LOG_PREFIX} Simulation started - resetting processed items")
            self._processed_items.clear()

        # シミュレーション停止時の処理
        elif event.type == int(omni.timeline.TimelineEventType.STOP):
            carb.log_info(f"{LOG_PREFIX} Simulation stopped - cleaning up placed items")
            self._processed_items.clear()
            self._cleanup_on_simulation_stop()

    def _setup_ui(self):
        """UIの設定"""
        try:
            self._ui_window = ui.Window("Item Placement System (Trigger)", width=450, height=600)
            with self._ui_window.frame:
                # スクロール可能なフレームでコンテンツ全体を囲む
                with ui.ScrollingFrame(
                    horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                    vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_AS_NEEDED
                ):
                    with ui.VStack(spacing=10):
                        ui.Label("アイテム配置システム (Trigger版)", height=30, style={"font_size": 18})

                        ui.Separator()
                        ui.Label("🎯 概要", height=20)
                        with ui.VStack(spacing=2):
                            ui.Label("• Triggerにアイテムが入ると自動判定", style={"font_size": 12})
                            ui.Label("• Number属性で正誤を判定", style={"font_size": 12})
                            ui.Label("• 正解→指定位置に配置", style={"font_size": 12})
                            ui.Label("• 不正解→原点(0,0,0)にリセット", style={"font_size": 12})

                        # トリガーシステム状態
                        ui.Separator()
                        ui.Label("トリガーシステム状態", height=20)

                        self._trigger_status_frame = ui.Frame(height=280)
                        with self._trigger_status_frame:
                            self._trigger_status_container = ui.VStack(spacing=5)

                        # 制御ボタン
                        ui.Separator()
                        ui.Label("制御", height=20)

                        with ui.HStack(height=30):
                            ui.Button("状態更新", clicked_fn=self._refresh_status)
                            ui.Button("トリガー診断", clicked_fn=self._diagnose_triggers)

                        with ui.HStack(height=30):
                            ui.Button("トリガー有効化", clicked_fn=lambda: self._toggle_trigger(True))
                            ui.Button("トリガー無効化", clicked_fn=lambda: self._toggle_trigger(False))

                        with ui.HStack(height=30):
                            ui.Button("トリガー再セットアップ", clicked_fn=self._reinitialize_triggers, width=200)

                        # フィードバック表示エリア
                        ui.Separator()
                        ui.Label("システムメッセージ", height=20)

                        self._feedback_frame = ui.Frame(height=120)
                        with self._feedback_frame:
                            self._feedback_container = ui.VStack()

            # 初期状態更新
            self._refresh_status()

        except Exception as e:
            carb.log_error(f"{LOG_PREFIX} UI setup error: {e}")
            import traceback
            traceback.print_exc()

    def _refresh_status(self):
        """状態表示を更新"""
        try:
            self._update_trigger_status_display()
        except Exception as e:
            carb.log_error(f"{LOG_PREFIX} Status refresh error: {e}")

    def _update_trigger_detection(self):
        """
        TriggerStateAPIを監視してアイテムを検知・処理する
        物理コールバックではなくUpdateループで実行されるため、USD変更が安全
        """
        if not self._trigger_manager:
            return

        try:
            import omni.usd
            from pxr import Usd, UsdGeom, UsdPhysics, PhysxSchema, Sdf, Gf

            stage = omni.usd.get_context().get_stage()
            if not stage:
                return

            # 各トリガースロットを監視
            for slot in self._trigger_manager._slots:
                trigger_prim = stage.GetPrimAtPath(slot.trigger_path)
                if not trigger_prim or not trigger_prim.IsValid():
                    continue

                # TriggerStateAPIを取得
                trigger_state_api = PhysxSchema.PhysxTriggerStateAPI.Get(stage, slot.trigger_path)
                if not trigger_state_api:
                    continue

                # アクティブな衝突を取得（正しいメソッド名はGetTriggeredCollisionsRel）
                colliders_rel = trigger_state_api.GetTriggeredCollisionsRel()
                if not colliders_rel:
                    continue

                collider_paths = colliders_rel.GetTargets()

                # 各衝突しているコライダーを処理
                for collider_path in collider_paths:
                    # 処理済みチェック
                    item_key = (str(slot.trigger_path), str(collider_path))
                    if item_key in self._processed_items:
                        continue

                    # アイテムのNumber属性を取得
                    item_number = self._get_item_number(stage, collider_path)
                    if item_number == -1:
                        carb.log_warn(f"{LOG_PREFIX} Item has no valid Number attribute: {collider_path}")
                        continue

                    # 親Prim（Xform）を取得
                    parent_prim = self._get_parent_xform(stage, collider_path)
                    if not parent_prim:
                        carb.log_error(f"{LOG_PREFIX} Cannot find parent Xform for {collider_path}")
                        continue

                    # 正誤判定と処理
                    if item_number in slot.correct_numbers:
                        # 正解
                        carb.log_info(f"{LOG_PREFIX} ✅ CORRECT: Number={item_number} in trigger {slot.display_name}")

                        if slot.proxy_mapping:
                            # Proxy有り
                            self._handle_correct_item_with_proxy(
                                stage, parent_prim, slot
                            )
                        else:
                            # Proxy無し
                            self._handle_correct_item_no_proxy(
                                stage, parent_prim, collider_path, slot
                            )
                    else:
                        # 不正解
                        carb.log_info(f"{LOG_PREFIX} ❌ INCORRECT: Number={item_number} not in {slot.correct_numbers}")
                        self._handle_incorrect_item(
                            stage, parent_prim
                        )

                    # 処理済みとしてマーク
                    self._processed_items.add(item_key)

        except Exception as e:
            carb.log_error(f"{LOG_PREFIX} Error in _update_trigger_detection: {e}")
            import traceback
            traceback.print_exc()

    def _update_trigger_status_display(self):
        """トリガーシステム状態表示の更新"""
        if not self._trigger_status_container:
            return

        try:
            # 既存のウィジェットをクリア
            self._trigger_status_container.clear()

            # トリガー状態を取得
            trigger_status = self._trigger_manager.get_trigger_status()

            with self._trigger_status_container:
                # トリガー有効/無効
                with ui.HStack(height=20):
                    ui.Label("トリガー検知:", width=100)
                    status_text = "有効" if trigger_status["enabled"] else "無効"
                    status_color = {"color": 0xFF00AA00} if trigger_status["enabled"] else {"color": 0xFF666666}
                    ui.Label(status_text, style=status_color)

                # スロット数
                with ui.HStack(height=20):
                    ui.Label("監視スロット数:", width=100)
                    ui.Label(f"{trigger_status['slot_count']} 個")

                ui.Separator()

                # 各トリガーの状態
                for monitor_info in trigger_status["monitors"]:
                    with ui.VStack(height=60, spacing=2):
                        # スロット名と検知数
                        with ui.HStack(height=20):
                            ui.Label(f"📍 {monitor_info['display_name']}", width=180)
                            collider_count = monitor_info["active_colliders"]
                            count_color = {"color": 0xFF00AA00} if collider_count > 0 else {"color": 0xFF666666}
                            ui.Label(f"検知: {collider_count}", width=60, style=count_color)

                        # トリガーパス
                        with ui.HStack(height=16):
                            ui.Spacer(width=12)
                            ui.Label(f"Path: {monitor_info['trigger_path']}",
                                    style={"color": 0xFF999999, "font_size": 10})

                        # 期待アイテム番号
                        with ui.HStack(height=18):
                            ui.Spacer(width=12)
                            expected_items_str = ", ".join(map(str, monitor_info["expected_items"]))
                            ui.Label(f"正解Number: [{expected_items_str}]",
                                    style={"color": 0xFFFFAA00, "font_size": 11})

        except Exception as e:
            carb.log_error(f"{LOG_PREFIX} Trigger status display error: {e}")
            import traceback
            traceback.print_exc()

    def _toggle_trigger(self, enabled: bool):
        """トリガー検知の有効/無効切り替え"""
        try:
            self._trigger_manager.enable_trigger_detection(enabled)
            self._refresh_status()
            status_text = "有効化" if enabled else "無効化"
            self._add_feedback(f"トリガー検知を{status_text}しました", "info")

        except Exception as e:
            carb.log_error(f"{LOG_PREFIX} Toggle trigger error: {e}")
            self._add_feedback(f"エラー: {e}", "error")

    def _diagnose_triggers(self):
        """トリガーシステムの診断を実行"""
        try:
            carb.log_info("\n" + "="*60)
            carb.log_info(f"{LOG_PREFIX} Running Trigger System Diagnosis")
            carb.log_info("="*60)
            self._trigger_manager.diagnose_trigger_system()
            self._add_feedback("診断完了。コンソールを確認してください", "success")

        except Exception as e:
            carb.log_error(f"{LOG_PREFIX} Diagnosis error: {e}")
            self._add_feedback(f"診断エラー: {e}", "error")
            import traceback
            traceback.print_exc()

    def _reinitialize_triggers(self):
        """トリガーを再セットアップ"""
        try:
            self._trigger_manager.initialize()
            self._refresh_status()
            self._add_feedback("トリガーを再セットアップしました", "success")

        except Exception as e:
            carb.log_error(f"{LOG_PREFIX} Reinitialize error: {e}")
            self._add_feedback(f"再セットアップエラー: {e}", "error")

    def _cleanup_on_simulation_stop(self):
        """シミュレーション停止時のクリーンアップ処理"""
        try:
            import omni.usd
            from pxr import Usd, UsdPhysics, Sdf, UsdGeom

            stage = omni.usd.get_context().get_stage()
            if not stage:
                carb.log_warn(f"{LOG_PREFIX} Stage not available for cleanup")
                return

            cleanup_count = 0

            # 1. 全てのreal_objectを強制的に非表示＆コリジョン無効化（trigger_managerから）
            cleanup_count += self._cleanup_all_real_objects(stage)

            # 2. プロキシシステムを使用したオブジェクトのクリーンアップ（USD属性から読み取り）
            cleanup_count += self._cleanup_proxy_placed_items(stage)

            # 3. トリガーマネージャーから配置されたオブジェクトを取得してRigidBody再有効化
            if self._trigger_manager:
                cleanup_count += self._cleanup_standard_placed_items(stage)

            carb.log_info(f"{LOG_PREFIX} Cleanup complete: {cleanup_count} objects processed")
            self._add_feedback(f"シミュレーション停止: {cleanup_count}個のオブジェクトをクリーンアップ", "info")

        except Exception as e:
            carb.log_error(f"{LOG_PREFIX} Cleanup error: {e}")
            import traceback
            traceback.print_exc()

    def _cleanup_all_real_objects(self, stage) -> int:
        """全てのreal_objectを強制的に非表示＆コリジョン無効化（trigger_managerから取得）"""
        try:
            from pxr import UsdPhysics, UsdGeom

            if not self._trigger_manager:
                return 0

            cleanup_count = 0

            # trigger_managerから全てのスロットを取得
            slots = self._trigger_manager.get_all_slots()
            for slot in slots:
                # proxy_mappingがあるスロットのみ処理
                if slot.proxy_mapping and slot.proxy_mapping.real_path:
                    real_path = slot.proxy_mapping.real_path
                    real_prim = stage.GetPrimAtPath(real_path)

                    if real_prim and real_prim.IsValid():
                        # visibility を invisible に
                        imageable = UsdGeom.Imageable(real_prim)
                        visibility_attr = imageable.GetVisibilityAttr()
                        if not visibility_attr:
                            visibility_attr = imageable.CreateVisibilityAttr()
                        visibility_attr.Set(UsdGeom.Tokens.invisible)
                        carb.log_info(f"{LOG_PREFIX} [All Real Objects] Set visibility=invisible for: {real_path}")

                        # collisionEnabled を False に
                        collision_api = UsdPhysics.CollisionAPI.Get(stage, real_path)
                        if collision_api:
                            collision_enabled_attr = collision_api.GetCollisionEnabledAttr()
                            if collision_enabled_attr:
                                collision_enabled_attr.Set(False)
                                carb.log_info(f"{LOG_PREFIX} [All Real Objects] Set collisionEnabled=False for: {real_path}")

                        cleanup_count += 1

            carb.log_info(f"{LOG_PREFIX} All real objects cleanup: {cleanup_count} objects processed")
            return cleanup_count

        except Exception as e:
            carb.log_error(f"{LOG_PREFIX} Error cleaning all real objects: {e}")
            import traceback
            traceback.print_exc()
            return 0

    def _cleanup_proxy_placed_items(self, stage) -> int:
        """プロキシシステムで配置されたアイテムのクリーンアップ（USD属性から読み取り）"""
        try:
            from pxr import UsdPhysics, UsdGeom, Sdf

            cleanup_count = 0

            # Stageから全てのPrimをチェックして、custom:proxy_placed属性がTrueのものを探す
            for prim in stage.Traverse():
                proxy_placed_attr = prim.GetAttribute("custom:proxy_placed")
                if proxy_placed_attr and proxy_placed_attr.IsValid() and proxy_placed_attr.Get():
                    # 実オブジェクトのパスを取得
                    real_path_attr = prim.GetAttribute("custom:real_object_path")
                    if real_path_attr and real_path_attr.IsValid():
                        real_path = real_path_attr.Get()
                        real_prim = stage.GetPrimAtPath(real_path)

                        if real_prim and real_prim.IsValid():
                            # visibility を invisible に
                            imageable = UsdGeom.Imageable(real_prim)
                            visibility_attr = imageable.GetVisibilityAttr()
                            if not visibility_attr:
                                visibility_attr = imageable.CreateVisibilityAttr()
                            visibility_attr.Set(UsdGeom.Tokens.invisible)
                            carb.log_info(f"{LOG_PREFIX} Set visibility=invisible for: {real_path}")

                            # collisionEnabled を False に
                            collision_api = UsdPhysics.CollisionAPI.Get(stage, real_path)
                            if collision_api:
                                collision_enabled_attr = collision_api.GetCollisionEnabledAttr()
                                if collision_enabled_attr:
                                    collision_enabled_attr.Set(False)
                                    carb.log_info(f"{LOG_PREFIX} Set collisionEnabled=False for: {real_path}")

                            cleanup_count += 1

                    # custom:proxy_placed属性をクリア
                    proxy_placed_attr.Set(False)

            carb.log_info(f"{LOG_PREFIX} Proxy placement cleanup: {cleanup_count} objects processed")
            return cleanup_count

        except Exception as e:
            carb.log_error(f"{LOG_PREFIX} Error cleaning proxy items: {e}")
            import traceback
            traceback.print_exc()
            return 0

    def _cleanup_standard_placed_items(self, stage):
        """標準配置アイテムのクリーンアップ（RigidBody再有効化 + 角度リセット）"""
        try:
            from pxr import UsdPhysics, Sdf, UsdGeom, Gf

            cleanup_count = 0

            # Stageから全てのPrimをチェックして、custom:placed属性がTrueのものを探す
            for prim in stage.Traverse():
                placed_attr = prim.GetAttribute("custom:placed")
                if placed_attr and placed_attr.IsValid() and placed_attr.Get():
                    # RigidBodyを再有効化
                    rb_api = UsdPhysics.RigidBodyAPI.Get(stage, prim.GetPath())
                    if rb_api:
                        # disableSimulationをFalseに
                        disable_sim_attr = prim.GetAttribute("physxRigidBody:disableSimulation")
                        if disable_sim_attr and disable_sim_attr.IsValid():
                            disable_sim_attr.Set(False)
                            carb.log_info(f"{LOG_PREFIX} Re-enabled RigidBody for: {prim.GetPath()}")

                        # kinematicEnabledをFalseに
                        kinematic_attr = rb_api.GetKinematicEnabledAttr()
                        if kinematic_attr and kinematic_attr.IsValid():
                            kinematic_attr.Set(False)

                        cleanup_count += 1

                    # 角度を(0, 0, 0)にリセット
                    self._reset_rotation(prim)

                    # custom:placed属性をクリア
                    placed_attr.Set(False)

            carb.log_info(f"{LOG_PREFIX} Standard placement cleanup: {cleanup_count} objects processed")
            return cleanup_count

        except Exception as e:
            carb.log_error(f"{LOG_PREFIX} Error cleaning standard items: {e}")
            import traceback
            traceback.print_exc()
            return 0

    def _reset_rotation(self, prim):
        """Primの回転を(0, 0, 0)にリセット"""
        try:
            from pxr import UsdGeom, Gf

            xformable = UsdGeom.Xformable(prim)

            # 全てのRotate opをクリアして(0,0,0)に設定
            existing_ops = xformable.GetOrderedXformOps()
            has_rotate = False

            for op in existing_ops:
                op_type = op.GetOpType()
                # Rotate系のopを見つけたら(0,0,0)に設定
                if (op_type == UsdGeom.XformOp.TypeRotateXYZ or
                    op_type == UsdGeom.XformOp.TypeRotateX or
                    op_type == UsdGeom.XformOp.TypeRotateY or
                    op_type == UsdGeom.XformOp.TypeRotateZ or
                    op_type == UsdGeom.XformOp.TypeRotateXZY or
                    op_type == UsdGeom.XformOp.TypeRotateYXZ or
                    op_type == UsdGeom.XformOp.TypeRotateYZX or
                    op_type == UsdGeom.XformOp.TypeRotateZXY or
                    op_type == UsdGeom.XformOp.TypeRotateZYX):

                    if op_type == UsdGeom.XformOp.TypeRotateXYZ:
                        op.Set(Gf.Vec3f(0, 0, 0))
                    else:
                        op.Set(0.0)  # 単一軸回転は単一値

                    has_rotate = True
                    carb.log_info(f"{LOG_PREFIX} Reset rotation to (0,0,0) for: {prim.GetPath()}")

            if not has_rotate:
                # Rotate opが存在しない場合は何もしない
                pass

        except Exception as e:
            carb.log_warn(f"{LOG_PREFIX} Could not reset rotation for {prim.GetPath()}: {e}")

    def _add_feedback(self, message: str, feedback_type: str):
        """フィードバックメッセージを追加"""
        try:
            if not self._feedback_container:
                return

            # フィードバックの色設定
            color_map = {
                "success": 0xFF00AA00,
                "error": 0xFFAA0000,
                "warning": 0xFFAA6600,
                "info": 0xFF0066AA
            }

            color = color_map.get(feedback_type, 0xFF666666)

            # コンテナをクリアして再構築
            self._feedback_container.clear()

            # メッセージリストを保持
            if not hasattr(self, '_feedback_messages'):
                self._feedback_messages = []

            # 新しいメッセージを追加
            import datetime
            timestamp = datetime.datetime.now().strftime("%H:%M:%S")
            self._feedback_messages.append((timestamp, message, feedback_type, color))

            # 最新8件のみ保持
            if len(self._feedback_messages) > 8:
                self._feedback_messages = self._feedback_messages[-8:]

            # UIを再構築
            with self._feedback_container:
                for ts, msg, ftype, col in self._feedback_messages:
                    ui.Label(f"[{ts}] {msg}",
                            height=15, style={"color": col, "font_size": 11})

            # コンソールにも出力
            carb.log_info(f"{LOG_PREFIX} [{feedback_type.upper()}] {message}")

        except Exception as e:
            carb.log_error(f"{LOG_PREFIX} Feedback error: {e}")

    # 公開API
    def get_trigger_manager(self) -> TriggerManager:
        """TriggerManagerを取得"""
        return self._trigger_manager

    def get_task_manager(self):
        """TaskManagerを取得"""
        return self._task_manager

    def get_placement_state_manager(self):
        """PlacementStateManagerを取得"""
        return self._placement_state_manager

    def add_trigger_slot(
        self,
        slot_id: str,
        trigger_path: str,
        correct_numbers: list,
        placement_translate: tuple = (0, 0, 0),
        display_name: str = ""
    ):
        """
        新しいトリガースロットを追加

        Args:
            slot_id: スロットID
            trigger_path: トリガーPrimのパス
            correct_numbers: 正解Number値のリスト
            placement_translate: 配置先座標
            display_name: 表示名
        """
        slot = TriggerSlot(
            slot_id=slot_id,
            trigger_path=trigger_path,
            correct_numbers=correct_numbers,
            placement_translate=placement_translate,
            display_name=display_name
        )
        self._trigger_manager.add_slot(slot)
        self._refresh_status()
        self._add_feedback(f"スロット追加: {display_name}", "success")

    # ヘルパーメソッド（USD変更を含む）
    def _get_item_number(self, stage, item_path):
        """
        アイテムのNumber属性を取得

        Args:
            stage: USD Stage
            item_path: アイテムのパス

        Returns:
            int: Number属性の値。見つからない場合は-1
        """
        try:
            item_prim = stage.GetPrimAtPath(item_path)
            if not item_prim.IsValid():
                return -1

            # Number属性を取得
            number_attr = item_prim.GetAttribute("Number")
            if not number_attr.IsValid():
                # custom:Number も試す
                number_attr = item_prim.GetAttribute("custom:Number")

            if not number_attr.IsValid():
                return -1

            return number_attr.Get()

        except Exception as e:
            carb.log_error(f"{LOG_PREFIX} Error getting item number: {e}")
            return -1

    def _get_parent_xform(self, stage, item_path):
        """
        アイテムの親Prim（Xformタイプ）を取得

        Args:
            stage: USD Stage
            item_path: アイテムのパス

        Returns:
            Prim: 親XformのPrim、見つからない場合はNone
        """
        try:
            from pxr import UsdGeom

            item_prim = stage.GetPrimAtPath(item_path)
            if not item_prim.IsValid():
                return None

            # 親を取得
            parent_prim = item_prim.GetParent()
            if not parent_prim or not parent_prim.IsValid():
                carb.log_warn(f"{LOG_PREFIX} No valid parent for {item_path}")
                return None

            # Xformableかチェック
            if parent_prim.IsA(UsdGeom.Xformable):
                return parent_prim
            else:
                carb.log_warn(f"{LOG_PREFIX} Parent is not Xformable: {parent_prim.GetPath()}")
                return None

        except Exception as e:
            carb.log_error(f"{LOG_PREFIX} Error getting parent xform: {e}")
            return None

    def _handle_correct_item_no_proxy(self, stage, parent_prim, collider_path, slot):
        """
        正解時の処理（Proxy無し）
        Updateループ内で実行されるため、USD変更が安全

        Args:
            stage: USD Stage
            parent_prim: 親Prim（RigidBodyを持つXform）
            collider_path: コライダーのパス（Object）
            slot: TriggerSlot
        """
        try:
            from pxr import UsdGeom, UsdPhysics, Sdf, Gf

            # 子Prim（Object）を取得（属性はObjectに設定する）
            object_prim = stage.GetPrimAtPath(collider_path)
            if not object_prim or not object_prim.IsValid():
                object_prim = parent_prim  # フォールバック

            # 0. 現在位置を original_position として保存（移動前）
            xformable = UsdGeom.Xformable(parent_prim)
            if xformable:
                current_transform = xformable.ComputeLocalToWorldTransform(0)
                current_pos = current_transform.ExtractTranslation()

                original_pos_attr = object_prim.GetAttribute("custom:original_position")
                if not original_pos_attr:
                    original_pos_attr = object_prim.CreateAttribute("custom:original_position", Sdf.ValueTypeNames.Float3, False)
                original_pos_attr.Set(Gf.Vec3f(current_pos[0], current_pos[1], current_pos[2]))

            # 0-2. slot_id を保存
            if slot.slot_id:
                slot_id_attr = object_prim.GetAttribute("custom:slot_id")
                if not slot_id_attr:
                    slot_id_attr = object_prim.CreateAttribute("custom:slot_id", Sdf.ValueTypeNames.String, False)
                slot_id_attr.Set(slot.slot_id)

            # 1. 位置を設定
            translate_op = None
            for op in xformable.GetOrderedXformOps():
                if op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
                    translate_op = op
                    break

            if not translate_op:
                translate_op = xformable.AddTranslateOp()

            translate_vec = Gf.Vec3f(slot.placement_translate[0], slot.placement_translate[1], slot.placement_translate[2])
            translate_op.Set(translate_vec)

            # 2. RigidBodyAPIを取得して無効化
            rb_api = UsdPhysics.RigidBodyAPI.Get(stage, parent_prim.GetPath())
            if rb_api:
                # 速度をゼロに
                velocity_attr = rb_api.GetVelocityAttr()
                if velocity_attr:
                    velocity_attr.Set(Gf.Vec3f(0, 0, 0))

                angular_velocity_attr = rb_api.GetAngularVelocityAttr()
                if angular_velocity_attr:
                    angular_velocity_attr.Set(Gf.Vec3f(0, 0, 0))

                # RigidBody無効化（静的コライダー化）
                rb_enabled_attr = parent_prim.GetAttribute("physics:rigidBodyEnabled")
                if not rb_enabled_attr or not rb_enabled_attr.IsValid():
                    rb_enabled_attr = parent_prim.CreateAttribute("physics:rigidBodyEnabled", Sdf.ValueTypeNames.Bool, False)
                rb_enabled_attr.Set(False)

            # 3. placed属性をObjectにTrueに
            placed_attr = object_prim.GetAttribute("custom:placed")
            if not placed_attr:
                placed_attr = object_prim.CreateAttribute("custom:placed", Sdf.ValueTypeNames.Bool, False)
            placed_attr.Set(True)

            # 4. task属性をObjectに設定
            task_required = slot.task_type and slot.task_type != "none"
            task_attr = object_prim.GetAttribute("custom:task")
            if not task_attr:
                task_attr = object_prim.CreateAttribute("custom:task", Sdf.ValueTypeNames.Bool, False)
            # タスクあり（True）→task=False、タスクなし（False）→task=True
            task_value = not task_required
            task_attr.Set(task_value)

            carb.log_info(f"{LOG_PREFIX} ✅ Item placed at {translate_vec}, task={task_required}, slot={slot.slot_id}")

        except Exception as e:
            carb.log_error(f"{LOG_PREFIX} Error in _handle_correct_item_no_proxy: {e}")
            import traceback
            traceback.print_exc()

    def _handle_correct_item_with_proxy(self, stage, parent_prim, slot):
        """
        正解時の処理（Proxy有り）
        Updateループ内で実行されるため、USD変更が安全

        Args:
            stage: USD Stage
            parent_prim: プロキシの親Prim
            slot: TriggerSlot
        """
        try:
            from pxr import UsdGeom, UsdPhysics, Sdf, Gf

            # Proxyの元の位置を保存
            xformable = UsdGeom.Xformable(parent_prim)
            if xformable:
                current_transform = xformable.ComputeLocalToWorldTransform(0)
                current_pos = current_transform.ExtractTranslation()
                proxy_original_pos = Gf.Vec3f(current_pos[0], current_pos[1], current_pos[2])
            else:
                proxy_original_pos = Gf.Vec3f(0, 0, 0)

            # 1. ProxyのRigidBody無効化
            rb_api = UsdPhysics.RigidBodyAPI.Get(stage, parent_prim.GetPath())
            if rb_api:
                rb_enabled_attr = parent_prim.GetAttribute("physics:rigidBodyEnabled")
                if not rb_enabled_attr or not rb_enabled_attr.IsValid():
                    rb_enabled_attr = parent_prim.CreateAttribute("physics:rigidBodyEnabled", Sdf.ValueTypeNames.Bool, False)
                rb_enabled_attr.Set(False)

            # 2. Proxyを隠す位置に移動（proxy_reset_positionまたは(0,100,0)）
            reset_pos = slot.proxy_reset_position if slot.proxy_reset_position else (0, 100, 0)
            translate_op = None
            for op in xformable.GetOrderedXformOps():
                if op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
                    translate_op = op
                    break

            if not translate_op:
                translate_op = xformable.AddTranslateOp()

            translate_op.Set(Gf.Vec3f(reset_pos[0], reset_pos[1], reset_pos[2]))

            # 3. Real objectを表示＆コリジョン有効化
            real_path = slot.proxy_mapping.real_path
            real_prim = stage.GetPrimAtPath(real_path)
            if real_prim and real_prim.IsValid():
                # Visibility設定
                imageable = UsdGeom.Imageable(real_prim)
                visibility_attr = imageable.GetVisibilityAttr()
                if visibility_attr:
                    visibility_attr.Set(UsdGeom.Tokens.inherited)

                # Collision設定
                collision_api = UsdPhysics.CollisionAPI.Get(stage, real_path)
                if collision_api:
                    collision_attr = collision_api.GetCollisionEnabledAttr()
                    if collision_attr:
                        collision_attr.Set(True)

                # 4. Real objectにUSD属性を保存
                task_required = slot.task_type and slot.task_type != "none"

                task_attr = real_prim.GetAttribute("custom:task")
                if not task_attr:
                    task_attr = real_prim.CreateAttribute("custom:task", Sdf.ValueTypeNames.Bool, False)
                task_value = not task_required
                task_attr.Set(task_value)

                proxy_placed_attr = real_prim.GetAttribute("custom:proxy_placed")
                if not proxy_placed_attr:
                    proxy_placed_attr = real_prim.CreateAttribute("custom:proxy_placed", Sdf.ValueTypeNames.Bool, False)
                proxy_placed_attr.Set(True)

                proxy_path_attr = real_prim.GetAttribute("custom:proxy_path")
                if not proxy_path_attr:
                    proxy_path_attr = real_prim.CreateAttribute("custom:proxy_path", Sdf.ValueTypeNames.String, False)
                proxy_path_attr.Set(str(parent_prim.GetPath()))

                original_pos_attr = real_prim.GetAttribute("custom:original_position")
                if not original_pos_attr:
                    original_pos_attr = real_prim.CreateAttribute("custom:original_position", Sdf.ValueTypeNames.Float3, False)
                original_pos_attr.Set(proxy_original_pos)

                if slot.slot_id:
                    slot_id_attr = real_prim.GetAttribute("custom:slot_id")
                    if not slot_id_attr:
                        slot_id_attr = real_prim.CreateAttribute("custom:slot_id", Sdf.ValueTypeNames.String, False)
                    slot_id_attr.Set(slot.slot_id)

                placed_attr = real_prim.GetAttribute("custom:placed")
                if not placed_attr:
                    placed_attr = real_prim.CreateAttribute("custom:placed", Sdf.ValueTypeNames.Bool, False)
                placed_attr.Set(True)

            # 5. ProxyにProxy配置情報を記録
            proxy_placed_attr_on_proxy = parent_prim.GetAttribute("custom:proxy_placed")
            if not proxy_placed_attr_on_proxy:
                proxy_placed_attr_on_proxy = parent_prim.CreateAttribute("custom:proxy_placed", Sdf.ValueTypeNames.Bool, False)
            proxy_placed_attr_on_proxy.Set(True)

            real_path_attr = parent_prim.GetAttribute("custom:real_object_path")
            if not real_path_attr:
                real_path_attr = parent_prim.CreateAttribute("custom:real_object_path", Sdf.ValueTypeNames.String, False)
            real_path_attr.Set(real_path)

            carb.log_info(f"{LOG_PREFIX} ✅ Proxy hidden, Real object shown: {real_path}, task={task_required}, slot={slot.slot_id}")

        except Exception as e:
            carb.log_error(f"{LOG_PREFIX} Error in _handle_correct_item_with_proxy: {e}")
            import traceback
            traceback.print_exc()

    def _handle_incorrect_item(self, stage, parent_prim):
        """
        不正解時の処理
        Updateループ内で実行されるため、USD変更が安全

        Args:
            stage: USD Stage
            parent_prim: 親Prim
        """
        try:
            from pxr import UsdGeom, UsdPhysics, Sdf, Gf

            # 原点(0,0,0)に移動
            xformable = UsdGeom.Xformable(parent_prim)
            translate_op = None
            for op in xformable.GetOrderedXformOps():
                if op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
                    translate_op = op
                    break

            if not translate_op:
                translate_op = xformable.AddTranslateOp()

            translate_op.Set(Gf.Vec3f(0, 0, 0))

            # RigidBodyAPIを取得して速度をゼロに
            rb_api = UsdPhysics.RigidBodyAPI.Get(stage, parent_prim.GetPath())
            if rb_api:
                velocity_attr = rb_api.GetVelocityAttr()
                if velocity_attr:
                    velocity_attr.Set(Gf.Vec3f(0, 0, 0))

                angular_velocity_attr = rb_api.GetAngularVelocityAttr()
                if angular_velocity_attr:
                    angular_velocity_attr.Set(Gf.Vec3f(0, 0, 0))

                # RigidBody無効化
                rb_enabled_attr = parent_prim.GetAttribute("physics:rigidBodyEnabled")
                if not rb_enabled_attr or not rb_enabled_attr.IsValid():
                    rb_enabled_attr = parent_prim.CreateAttribute("physics:rigidBodyEnabled", Sdf.ValueTypeNames.Bool, False)
                rb_enabled_attr.Set(False)

            carb.log_info(f"{LOG_PREFIX} ❌ INCORRECT! Item reset to (0,0,0)")

        except Exception as e:
            carb.log_error(f"{LOG_PREFIX} Error in _handle_incorrect_item: {e}")
            import traceback
            traceback.print_exc()


def get_extension_instance() -> ItemPlacementTriggerExtension:
    """
    拡張機能のグローバルインスタンスを取得

    Returns:
        ItemPlacementTriggerExtension: 拡張機能インスタンス
    """
    return _extension_instance
