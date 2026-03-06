# coding: utf-8

import omni.ext
import omni.ui as ui
import omni.kit.app
import carb

# VR拡張機能のインポート
_xr_core = None
_has_xr_core = False

try:
    from omni.kit.xr.core import XRCore
    _has_xr_core = True
    print("[VR Test UI] omni.kit.xr.core をインポートしました")
except ImportError as e:
    print(f"[VR Test UI] Warning: omni.kit.xr.core が利用できません: {e}")
    print("[VR Test UI] VR機能なしで動作します（通常ウィンドウモード）")


class VRTestUIExtension(omni.ext.IExt):
    """VRテスト用UI拡張機能

    機能:
    1. テキスト表示（英語・日本語）
    2. コントローラー入力表示
    3. クリック可能なボタン
    """

    def on_startup(self, ext_id):
        global _extension_instance
        _extension_instance = self

        print("[VR Test UI] VRテストUI拡張機能を起動中...")

        self._window = None
        self._update_subscription = None
        self._xr_core = None

        # コントローラー状態
        self._controller_states = {
            "left": {},
            "right": {}
        }

        # UI要素
        self._controller_labels = {}

        # XR Coreの初期化
        if _has_xr_core:
            try:
                self._xr_core = XRCore.get_singleton()
                print("[VR Test UI] XRCore シングルトンを取得しました")
            except Exception as e:
                print(f"[VR Test UI] Warning: XRCore取得失敗: {e}")
                self._xr_core = None

        # UIの作成
        self._create_ui()

        # 更新ループの開始
        self._start_update_loop()

        print("[VR Test UI] 起動完了")

    def on_shutdown(self):
        global _extension_instance
        _extension_instance = None

        print("[VR Test UI] VRテストUI拡張機能を終了中...")

        # 更新ループの停止
        if self._update_subscription:
            self._update_subscription.unsubscribe()
            self._update_subscription = None

        # ウィンドウの破棄
        if self._window:
            self._window.destroy()
            self._window = None

        print("[VR Test UI] 終了完了")

    def _create_ui(self):
        """UIウィンドウの作成"""
        self._window = ui.Window("VR Test UI", width=500, height=600)

        with self._window.frame:
            with ui.VStack(spacing=10, style={"margin": 10}):
                # ========== 1. テキスト表示テスト ==========
                ui.Label("VR Text Display Test", style={"font_size": 20, "color": 0xFFFFFFFF})
                ui.Separator()

                with ui.HStack(height=0):
                    ui.Label("Test 1 (English):", width=150)
                    ui.Label("Hello World", style={"font_size": 16, "color": 0xFF00FF00})

                with ui.HStack(height=0):
                    ui.Label("Test 2 (Japanese):", width=150)
                    ui.Label("ハローワールド", style={"font_size": 16, "color": 0xFF00FFFF})

                with ui.HStack(height=0):
                    ui.Label("Test 3 (Mixed):", width=150)
                    ui.Label("Hello World ハローワールド", style={"font_size": 16, "color": 0xFFFFFF00})

                ui.Spacer(height=10)
                ui.Separator()

                # ========== 2. コントローラー入力表示 ==========
                ui.Label("VR Controller Input Status", style={"font_size": 20, "color": 0xFFFFFFFF})
                ui.Separator()

                # XR Coreの状態表示
                if self._xr_core:
                    ui.Label("✓ XRCore Available", style={"color": 0xFF00FF00})
                else:
                    ui.Label("✗ XRCore Not Available (VR機能なし)", style={"color": 0xFFFF0000})

                ui.Spacer(height=5)

                # 左コントローラー
                ui.Label("Left Controller:", style={"font_size": 16})
                with ui.VStack(spacing=3, style={"margin": 5}):
                    self._controller_labels["left_trigger"] = ui.Label("Trigger: -")
                    self._controller_labels["left_grip"] = ui.Label("Grip: -")
                    self._controller_labels["left_a_button"] = ui.Label("A Button: -")
                    self._controller_labels["left_b_button"] = ui.Label("B Button: -")
                    self._controller_labels["left_position"] = ui.Label("Position: -")

                ui.Spacer(height=5)

                # 右コントローラー
                ui.Label("Right Controller:", style={"font_size": 16})
                with ui.VStack(spacing=3, style={"margin": 5}):
                    self._controller_labels["right_trigger"] = ui.Label("Trigger: -")
                    self._controller_labels["right_grip"] = ui.Label("Grip: -")
                    self._controller_labels["right_a_button"] = ui.Label("A Button: -")
                    self._controller_labels["right_b_button"] = ui.Label("B Button: -")
                    self._controller_labels["right_position"] = ui.Label("Position: -")

                ui.Spacer(height=10)
                ui.Separator()

                # ========== 3. テストボタン ==========
                ui.Label("Interactive Button Test", style={"font_size": 20, "color": 0xFFFFFFFF})
                ui.Separator()

                with ui.HStack(height=40):
                    ui.Spacer(width=10)
                    ui.Button(
                        "Click Me / クリックしてください",
                        clicked_fn=self._on_test_button_clicked,
                        height=40,
                        style={"Button": {"background_color": 0xFF4488FF}}
                    )
                    ui.Spacer(width=10)

                ui.Spacer(height=5)

                # ボタンクリック回数表示
                with ui.HStack(height=0):
                    ui.Label("Button Click Count:", width=150)
                    self._click_count = 0
                    self._click_count_label = ui.Label(f"{self._click_count}", style={"color": 0xFFFFFF00})

    def _start_update_loop(self):
        """更新ループの開始"""
        if self._xr_core:
            update_stream = omni.kit.app.get_app().get_update_event_stream()
            self._update_subscription = update_stream.create_subscription_to_pop(
                self._on_update, name="vr_test_ui_update"
            )
            print("[VR Test UI] 更新ループを開始しました")
        else:
            print("[VR Test UI] XRCoreが利用できないため、更新ループは開始しません")

    def _on_update(self, e):
        """フレーム毎の更新 - コントローラー状態を取得・表示"""
        if not self._xr_core:
            return

        try:
            # 左コントローラー状態を取得
            left_controller = self._xr_core.get_controller_state(0)
            if left_controller:
                self._update_controller_display("left", left_controller)

            # 右コントローラー状態を取得
            right_controller = self._xr_core.get_controller_state(1)
            if right_controller:
                self._update_controller_display("right", right_controller)

        except Exception as e:
            # エラーが発生しても拡張機能を止めない
            pass

    def _update_controller_display(self, hand, controller):
        """コントローラー状態をUIに表示"""
        try:
            # Trigger
            trigger_pressed = getattr(controller, 'trigger_pressed', False)
            self._controller_labels[f"{hand}_trigger"].text = f"Trigger: {'PRESSED' if trigger_pressed else 'Released'}"
            self._controller_labels[f"{hand}_trigger"].style = {"color": 0xFF00FF00 if trigger_pressed else 0xFF888888}

            # Grip
            grip_pressed = getattr(controller, 'grip_pressed', False)
            self._controller_labels[f"{hand}_grip"].text = f"Grip: {'PRESSED' if grip_pressed else 'Released'}"
            self._controller_labels[f"{hand}_grip"].style = {"color": 0xFF00FF00 if grip_pressed else 0xFF888888}

            # A Button
            a_button = getattr(controller, 'a_button_pressed', False)
            self._controller_labels[f"{hand}_a_button"].text = f"A Button: {'PRESSED' if a_button else 'Released'}"
            self._controller_labels[f"{hand}_a_button"].style = {"color": 0xFF00FF00 if a_button else 0xFF888888}

            # B Button
            b_button = getattr(controller, 'b_button_pressed', False)
            self._controller_labels[f"{hand}_b_button"].text = f"B Button: {'PRESSED' if b_button else 'Released'}"
            self._controller_labels[f"{hand}_b_button"].style = {"color": 0xFF00FF00 if b_button else 0xFF888888}

            # Position
            position = getattr(controller, 'position', None)
            if position:
                pos_str = f"Position: ({position[0]:.2f}, {position[1]:.2f}, {position[2]:.2f})"
            else:
                pos_str = "Position: N/A"
            self._controller_labels[f"{hand}_position"].text = pos_str

        except Exception as e:
            # 属性が存在しない場合でもエラーを出さない
            pass

    def _on_test_button_clicked(self):
        """テストボタンがクリックされた時の処理"""
        # コンソールに出力
        print("Click OK")

        # クリック回数を更新
        self._click_count += 1
        self._click_count_label.text = f"{self._click_count}"

        # carbログにも出力（より確実なログ）
        carb.log_info("Click OK")
        carb.log_info(f"Button clicked {self._click_count} times")


# グローバルインスタンス
_extension_instance = None


def get_extension_instance():
    """拡張機能のインスタンスを取得"""
    global _extension_instance
    return _extension_instance
