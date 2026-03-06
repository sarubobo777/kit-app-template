# SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

"""
Item Placement System Extension
アイテム設置システムのメイン拡張機能
"""

import omni.ext
import omni.timeline
import omni.ui as ui
from .placement_manager import get_placement_manager, ItemPlacementManager
from .machine_status import get_machine_status, MachineStatus

# グローバル拡張機能インスタンス
_extension_instance = None

class ItemPlacementExtension(omni.ext.IExt):
    """
    アイテム設置システム拡張機能
    """

    def __init__(self):
        super().__init__()
        self._placement_manager: ItemPlacementManager = None
        self._machine_status: MachineStatus = None
        self._timeline_subscription = None
        self._ui_window = None
        self._ui_update_counter = 0
        self._ui_update_interval = 30  # 30フレームごとにUI更新
        self._feedback_messages = []  # UIフィードバックメッセージリスト

    def on_startup(self, ext_id):
        """拡張機能起動時の処理"""
        global _extension_instance
        _extension_instance = self

        print("[ItemPlacement] 拡張機能を開始します...")

        try:
            # マネージャーインスタンス取得
            self._placement_manager = get_placement_manager()
            self._machine_status = get_machine_status()

            # USD Stage接続
            self._placement_manager.initialize_usd_connection()

            # タイムラインイベント購読
            timeline = omni.timeline.get_timeline_interface()
            self._timeline_subscription = timeline.get_timeline_event_stream().create_subscription_to_pop(
                self._on_timeline_event
            )

            # UIセットアップ
            self._setup_ui()

            # UIフィードバックコールバック登録
            self._placement_manager.add_ui_feedback_callback(self._on_ui_feedback)

            print("[ItemPlacement] 拡張機能の起動が完了しました")

        except Exception as e:
            print(f"[ItemPlacement] 起動エラー: {e}")

    def on_shutdown(self):
        """拡張機能終了時の処理"""
        global _extension_instance

        print("[ItemPlacement] 拡張機能を終了します...")

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

            print("[ItemPlacement] 拡張機能の終了が完了しました")

        except Exception as e:
            print(f"[ItemPlacement] 終了エラー: {e}")

    def _on_timeline_event(self, event):
        """タイムラインイベントハンドラ（placement_managerとUI更新）"""
        # placement_managerのイベント処理
        self._placement_manager.on_timeline_event(event)

        # 定期的にUIを更新
        if event.type == int(omni.timeline.TimelineEventType.CURRENT_TIME_TICKED):
            self._ui_update_counter += 1
            if self._ui_update_counter >= self._ui_update_interval:
                self._ui_update_counter = 0
                # トリガー状態のみを更新（軽量）
                self._update_trigger_status_display()

    def _setup_ui(self):
        """UIの設定"""
        try:
            self._ui_window = ui.Window("Item Placement System", width=420, height=750)
            with self._ui_window.frame:
                with ui.VStack(spacing=10):
                    ui.Label("アイテム設置システム", height=30, style={"font_size": 18})

                    # 設置スロット状態表示
                    ui.Separator()
                    ui.Label("設置スロット状態", height=20)

                    self._slot_status_frame = ui.Frame(height=200)
                    with self._slot_status_frame:
                        self._slot_status_container = ui.VStack()

                    # マシンステータス表示
                    ui.Separator()
                    ui.Label("マシンステータス", height=20)

                    self._machine_status_frame = ui.Frame(height=150)
                    with self._machine_status_frame:
                        self._machine_status_container = ui.VStack()

                    # トリガーシステム状態
                    ui.Separator()
                    ui.Label("トリガーシステム", height=20)

                    self._trigger_status_frame = ui.Frame(height=220)
                    with self._trigger_status_frame:
                        self._trigger_status_container = ui.VStack(spacing=5)

                    # 制御ボタン
                    ui.Separator()
                    ui.Label("制御", height=20)

                    with ui.HStack(height=30):
                        ui.Button("状態更新", clicked_fn=self._refresh_status)
                        ui.Button("全取り外し", clicked_fn=self._remove_all_items)

                    with ui.HStack(height=30):
                        ui.Button("トリガー有効化", clicked_fn=lambda: self._toggle_trigger(True))
                        ui.Button("トリガー無効化", clicked_fn=lambda: self._toggle_trigger(False))

                    with ui.HStack(height=30):
                        ui.Button("トリガー診断", clicked_fn=self._diagnose_triggers, width=200)

                    # フィードバック表示エリア
                    ui.Separator()
                    ui.Label("システムメッセージ", height=20)

                    self._feedback_frame = ui.Frame(height=100)
                    with self._feedback_frame:
                        self._feedback_container = ui.VStack()

            # 初期状態更新
            self._refresh_status()

        except Exception as e:
            print(f"[ItemPlacement] UI設定エラー: {e}")

    def _refresh_status(self):
        """状態表示を更新"""
        try:
            # スロット状態更新
            self._update_slot_status_display()

            # マシンステータス更新
            self._update_machine_status_display()

            # トリガーシステム状態更新
            self._update_trigger_status_display()

        except Exception as e:
            print(f"[ItemPlacement] 状態更新エラー: {e}")

    def _update_slot_status_display(self):
        """スロット状態表示の更新"""
        if not self._slot_status_container:
            return

        try:
            # 既存のウィジェットをクリア
            self._slot_status_container.clear()

            # 現在のスロット状態を取得
            slot_status = self._placement_manager.get_slot_status()

            with self._slot_status_container:
                for slot_id, status in slot_status.items():
                    with ui.HStack(height=25):
                        # スロット名
                        ui.Label(status["name"], width=120)

                        # 占有状態
                        status_text = "使用中" if status["occupied"] else "空き"
                        status_color = {"color": 0xFF00AA00} if status["occupied"] else {"color": 0xFF666666}
                        ui.Label(status_text, width=60, style=status_color)

                        # 取り外しボタン（使用中の場合のみ）
                        if status["occupied"]:
                            ui.Button("取り外し", width=80,
                                    clicked_fn=lambda slot_id=slot_id: self._remove_item_from_slot(slot_id))
                        else:
                            ui.Spacer(width=80)

        except Exception as e:
            print(f"[ItemPlacement] スロット表示更新エラー: {e}")

    def _update_machine_status_display(self):
        """マシンステータス表示の更新"""
        if not self._machine_status_container:
            return

        try:
            # 既存のウィジェットをクリア
            self._machine_status_container.clear()

            # 現在のマシンステータスを取得
            all_status = self._machine_status.get_all_status()

            with self._machine_status_container:
                for status_type, value in all_status.items():
                    with ui.HStack(height=20):
                        # ステータス名
                        status_name = status_type.value.replace("_", " ").title()
                        ui.Label(status_name, width=150)

                        # 状態表示
                        status_text = "ON" if value else "OFF"
                        status_color = {"color": 0xFF00AA00} if value else {"color": 0xFF666666}
                        ui.Label(status_text, style=status_color)

                # 安全運転可能状態
                with ui.HStack(height=25):
                    ui.Separator()

                with ui.HStack(height=25):
                    ui.Label("安全運転可能:", width=150)
                    safe_to_operate = self._machine_status.is_safe_to_operate()
                    safety_text = "YES" if safe_to_operate else "NO"
                    safety_color = {"color": 0xFF00AA00} if safe_to_operate else {"color": 0xFFAA0000}
                    ui.Label(safety_text, style=safety_color)

        except Exception as e:
            print(f"[ItemPlacement] マシンステータス表示更新エラー: {e}")

    def _remove_item_from_slot(self, slot_id: str):
        """指定スロットからアイテムを取り外し"""
        try:
            success, message = self._placement_manager.remove_item(slot_id)
            if success:
                self._refresh_status()

            print(f"[ItemPlacement] 取り外し結果: {message}")

        except Exception as e:
            print(f"[ItemPlacement] 取り外しエラー: {e}")

    def _remove_all_items(self):
        """全アイテムを取り外し"""
        try:
            slot_status = self._placement_manager.get_slot_status()
            removed_count = 0

            for slot_id, status in slot_status.items():
                if status["occupied"]:
                    success, _ = self._placement_manager.remove_item(slot_id)
                    if success:
                        removed_count += 1

            self._refresh_status()
            print(f"[ItemPlacement] {removed_count} 個のアイテムを取り外しました")

        except Exception as e:
            print(f"[ItemPlacement] 全取り外しエラー: {e}")

    def _update_trigger_status_display(self):
        """トリガーシステム状態表示の更新"""
        if not self._trigger_status_container:
            return

        try:
            # 既存のウィジェットをクリア
            self._trigger_status_container.clear()

            # トリガー状態を取得
            trigger_status = self._placement_manager.get_trigger_status()

            with self._trigger_status_container:
                # トリガー有効/無効
                with ui.HStack(height=20):
                    ui.Label("トリガー検知:", width=100)
                    status_text = "有効" if trigger_status["enabled"] else "無効"
                    status_color = {"color": 0xFF00AA00} if trigger_status["enabled"] else {"color": 0xFF666666}
                    ui.Label(status_text, style=status_color)

                # モニター数
                with ui.HStack(height=20):
                    ui.Label("監視トリガー数:", width=100)
                    ui.Label(f"{trigger_status['monitor_count']} 個")

                # 各トリガーの状態
                for monitor_info in trigger_status["monitors"]:
                    with ui.VStack(height=42, spacing=2):
                        # トリガー名と検知数
                        with ui.HStack(height=20):
                            ui.Label(f"  {monitor_info['display_name']}", width=100)
                            collider_count = monitor_info["active_colliders"]
                            count_color = {"color": 0xFF00AA00} if collider_count > 0 else {"color": 0xFF666666}
                            ui.Label(f"検知: {collider_count}", width=60, style=count_color)

                        # 期待アイテム番号
                        with ui.HStack(height=18):
                            ui.Spacer(width=12)
                            expected_items_str = ", ".join(map(str, monitor_info["expected_items"]))
                            ui.Label(f"正解: [{expected_items_str}]",
                                    style={"color": 0xFF999999, "font_size": 11})

        except Exception as e:
            print(f"[ItemPlacement] トリガー状態表示更新エラー: {e}")
            import traceback
            traceback.print_exc()

    def _toggle_trigger(self, enabled: bool):
        """トリガー検知の有効/無効切り替え"""
        try:
            self._placement_manager.enable_trigger_detection(enabled)
            self._refresh_status()
            status_text = "有効化" if enabled else "無効化"
            print(f"[ItemPlacement] トリガー検知を{status_text}しました")

        except Exception as e:
            print(f"[ItemPlacement] トリガー切り替えエラー: {e}")

    def _diagnose_triggers(self):
        """トリガーシステムの診断を実行"""
        try:
            print("\n" + "="*60)
            print("[ItemPlacement] トリガーシステム診断を実行します")
            print("="*60)
            self._placement_manager.diagnose_trigger_system()
            print("[ItemPlacement] 診断完了。コンソール出力を確認してください。")

        except Exception as e:
            print(f"[ItemPlacement] トリガー診断エラー: {e}")
            import traceback
            traceback.print_exc()

    def _on_ui_feedback(self, message: str, feedback_type: str):
        """UIフィードバック処理"""
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

            # コンテナをクリアして再構築（get_children()エラー回避）
            self._feedback_container.clear()

            # メッセージリストを保持
            if not hasattr(self, '_feedback_messages'):
                self._feedback_messages = []

            # 新しいメッセージを追加
            self._feedback_messages.append((message, feedback_type, color))

            # 最新10件のみ保持
            if len(self._feedback_messages) > 10:
                self._feedback_messages = self._feedback_messages[-10:]

            # UIを再構築
            with self._feedback_container:
                for msg, ftype, col in self._feedback_messages:
                    ui.Label(f"[{ftype.upper()}] {msg}",
                            height=20, style={"color": col})

            # トリガー状態も更新
            self._update_trigger_status_display()

        except Exception as e:
            print(f"[ItemPlacement] UIフィードバックエラー: {e}")
            import traceback
            traceback.print_exc()

    # 公開API
    def get_placement_manager(self) -> ItemPlacementManager:
        """PlacementManagerを取得"""
        return self._placement_manager

    def get_machine_status(self) -> MachineStatus:
        """MachineStatusを取得"""
        return self._machine_status

    def attempt_place_item_by_path(self, item_path: str, slot_id: str) -> tuple[bool, str]:
        """
        外部からのアイテム設置API

        Args:
            item_path: アイテムのUSDパス
            slot_id: 目標スロットID

        Returns:
            tuple[bool, str]: (成功フラグ, メッセージ)
        """
        if self._placement_manager:
            return self._placement_manager.attempt_place_item(item_path, slot_id)
        return False, "Placement Manager が利用できません"

    def auto_detect_and_place_item(self, item_path: str) -> tuple[bool, str]:
        """
        アイテムの位置から自動的に最適なスロットを検出して設置

        Args:
            item_path: アイテムのUSDパス

        Returns:
            tuple[bool, str]: (成功フラグ, メッセージ)
        """
        if not self._placement_manager:
            return False, "Placement Manager が利用できません"

        # 近くのスロットを検出
        nearby_slot = self._placement_manager.detect_item_near_slot(item_path)

        if nearby_slot:
            return self._placement_manager.attempt_place_item(item_path, nearby_slot)
        else:
            return False, "設置可能なスロットが近くにありません"

def get_extension_instance() -> ItemPlacementExtension:
    """
    拡張機能のグローバルインスタンスを取得

    Returns:
        ItemPlacementExtension: 拡張機能インスタンス
    """
    return _extension_instance