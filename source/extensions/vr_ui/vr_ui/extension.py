# coding: utf-8

import omni.ext
import omni.ui as ui
import omni.kit.app
import omni.usd
import carb
import carb.settings

# VR拡張機能のインポート
_xr_core = None
_has_xr_core = False
_has_xr_ui = False
_xr_gui_layer = None

try:
    import omni.kit.xr.core as xr_core_module
    from pxr import Gf
    _has_xr_core = True
except ImportError as e:
    xr_core_module = None
    print(f"[VR Test UI] Warning: omni.kit.xr.core が利用できません: {e}")
    print("[VR Test UI] VR機能なしで動作します（通常ウィンドウモード）")

try:
    from omni.kit.xr.core import XRGuiLayerComponentBase
    _has_xr_ui = True
except ImportError as e:
    XRGuiLayerComponentBase = None
    print(f"[VR Test UI] Warning: XR GUI Layer が利用できません: {e}")
    print("[VR Test UI] VR GUIレイヤー機能は使用できません")

# PhysX マウスインタラクションのインポート
_has_physx = False
_physx_bindings = None
_physx_interface = None
_physx_simulation_interface = None
try:
    import omni.physx.bindings._physx as physx_bindings
    import omni.physx
    from pxr import UsdPhysics, UsdGeom, Sdf, Gf
    _physx_bindings = physx_bindings
    _has_physx = True

    # PhysX Interfaceを取得
    try:
        _physx_interface = omni.physx.get_physx_interface()
    except Exception as e:
        print(f"[VR Test UI] Warning: PhysX Interface取得失敗: {e}")

    # PhysX Simulation Interfaceを取得（Mouse Interactionで使用）
    try:
        _physx_simulation_interface = omni.physx.get_physx_simulation_interface()
    except Exception as e:
        print(f"[VR Test UI] Warning: PhysX Simulation Interface取得失敗: {e}")

except ImportError as e:
    print(f"[VR Test UI] Warning: omni.physx.bindings が利用できません: {e}")
    print("[VR Test UI] マウスインタラクション機能は使用できません")
    # Fallback imports for USD types
    try:
        from pxr import UsdPhysics, UsdGeom, Sdf, Gf
    except ImportError:
        pass


class VRTestUIExtension(omni.ext.IExt):
    """VRテスト用UI拡張機能

    機能:
    1. テキスト表示（英語・日本語）
    2. コントローラー入力表示
    3. クリック可能なボタン
    4. HMD追従画像ビューアーUI
    5. VRコントローラー物理インタラクション
    """

    def on_startup(self, ext_id):
        global _extension_instance
        _extension_instance = self

        print("[VR Test UI] 起動中...")

        self._ext_id = ext_id  # Save extension ID

        self._window = None
        self._update_subscription = None
        self._xr_core = None
        self._xr_profile = None
        self._xr_devices = []
        self._xr_gui_layer = None  # VR GUI Layer
        self._vr_ui_path = None  # VR空間のUI prim path
        self._usd_context = None  # USD context

        # VR UI System - HMD追従UI (NEW)
        self._vr_ui_system = None
        self._vr_ui_image_folder = None  # 画像フォルダパス（設定で変更可能）

        # コントローラー状態
        self._controller_states = {
            "left": {},
            "right": {}
        }

        # UI要素
        self._controller_labels = {}
        self._last_button_values = {}  # UI更新最適化：ボタン値の変化検出用

        # デバッグ用：最初の数フレームだけログ出力
        self._debug_frame_count = 0
        self._max_debug_frames = 100

        # UI表示制御（Aボタントグル）
        self._vr_ui_placed = False  # VR UIが配置されているか
        self._a_button_was_pressed = False  # Aボタンの前回の状態（トグル用）

        # マウスインタラクション制御（トリガーボタン）
        self._mouse_interaction_enabled = False  # マウスインタラクションの元の状態
        self._mouse_interaction_original_value = None  # 元の設定値を保存
        self._trigger_active = False  # トリガーが押されているか
        self._settings = carb.settings.get_settings()  # Carb settings

        # VRコントローラーによる物理インタラクション（Force-at-point方式）
        # 左右両手で独立して動作
        self._grab_data = {
            'left': {
                'grabbed_prim_path': None,
                'grab_point_world': None,
                'grab_point_local': None,
                'target_position': None,
                'debug_line_prim': None,
                'grabbed_joint_path': None,
                'joint_axis': None,
                'joint_axis_local': None,
                'joint_center': None,
                'initial_angle': None,
                'cumulative_rotation': 0.0,
                'awaiting_removal': False,  # 取り外し待機モード
                'removal_target_path': None,  # 取り外し対象のオブジェクトパス
            },
            'right': {
                'grabbed_prim_path': None,
                'grab_point_world': None,
                'grab_point_local': None,
                'target_position': None,
                'debug_line_prim': None,
                'grabbed_joint_path': None,
                'joint_axis': None,
                'joint_axis_local': None,
                'joint_center': None,
                'initial_angle': None,
                'cumulative_rotation': 0.0,
                'awaiting_removal': False,  # 取り外し待機モード
                'removal_target_path': None,  # 取り外し対象のオブジェクトパス
            }
        }

        self._grab_force_strength = 1000.0  # 引っ張る力の強さ
        self._grab_damping = 0.2  # 速度減衰係数（0.0-1.0）
        self._grab_torque_strength = 50000.0  # トルクの強さ（Joint用）
        self._angular_velocity_gain = 5.0  # 角度差から角速度への変換ゲイン

        # コントローラーデバイスキャッシュ
        self._left_controller_device = None
        self._right_controller_device = None

        # XR Coreの初期化とプロファイル取得
        if _has_xr_core and xr_core_module:
            try:
                self._xr_core = xr_core_module.XRCore.get_singleton()

                # XR Profileを早期に取得
                if hasattr(self._xr_core, 'is_xr_display_enabled') and self._xr_core.is_xr_display_enabled():
                    if hasattr(self._xr_core, 'get_current_xr_profile'):
                        self._xr_profile = self._xr_core.get_current_xr_profile()
                        if not self._xr_profile:
                            print("[VR Test UI] Warning: XR Profile is None")
            except Exception as e:
                print(f"[VR Test UI] Warning: XRCore取得失敗: {e}")
                self._xr_core = None

        # XR GUI Layerの初期化 (Kit 107.3 新しいAPI)
        if _has_xr_ui and XRGuiLayerComponentBase and self._xr_core:
            try:
                # Kit 107では、XRCoreから直接GUI Layerを取得
                # XRGuiLayerComponentBaseを使う代わりに、XRCoreのcreate_xr_usd_layerを使用
                self._xr_gui_layer = self._xr_core.create_xr_usd_layer("/_xr/vr_test_ui")
                self._usd_context = omni.usd.get_context()
            except Exception as e:
                print(f"[VR Test UI] Warning: XR GUI Layer取得失敗: {e}")
                import traceback
                traceback.print_exc()
                self._xr_gui_layer = None

        # UIの作成
        self._create_ui()

        # 更新ループの開始
        self._start_update_loop()

        # VR UI System（HMD追従UI）の初期化 (NEW)
        try:
            from .vr_ui_system import VRUISystem
            # デフォルト画像フォルダ（拡張機能のdataフォルダ内）
            import os
            ext_path = os.path.dirname(__file__)
            default_image_folder = os.path.join(ext_path, "..", "data", "images")
            # 存在しない場合は作成
            os.makedirs(default_image_folder, exist_ok=True)
            self._vr_ui_image_folder = default_image_folder

            self._vr_ui_system = VRUISystem(
                self._ext_id,
                self._xr_core,
                self._vr_ui_image_folder
            )
            self._vr_ui_system.startup()
        except Exception as e:
            print(f"[VR Test UI] Warning: VR UI System initialization failed: {e}")
            import traceback
            traceback.print_exc()
            self._vr_ui_system = None

        print("[VR Test UI] 起動完了")

    def on_shutdown(self):
        global _extension_instance
        _extension_instance = None

        print("[VR Test UI] 終了中...")

        # VR UI Systemのシャットダウン (NEW - 最優先)
        if self._vr_ui_system:
            try:
                self._vr_ui_system.shutdown()
                self._vr_ui_system = None
            except Exception as e:
                print(f"[VR Test UI] Error shutting down VR UI System: {e}")

        # 更新ループの停止
        if self._update_subscription:
            self._update_subscription.unsubscribe()
            self._update_subscription = None

        # 掴んでいる物体を離す（物理インタラクション終了）
        if hasattr(self, '_grab_data'):
            for hand in ['left', 'right']:
                if self._grab_data[hand]['grabbed_prim_path'] is not None:
                    try:
                        self._end_vr_grab_interaction(hand)
                    except Exception as e:
                        print(f"[VR Test UI] Error releasing grabbed object on shutdown ({hand}): {e}")

                # デバッグ用の線を削除
                if self._grab_data[hand]['debug_line_prim']:
                    try:
                        stage = omni.usd.get_context().get_stage()
                        if stage and stage.GetPrimAtPath(self._grab_data[hand]['debug_line_prim']):
                            stage.RemovePrim(self._grab_data[hand]['debug_line_prim'])
                    except Exception:
                        pass

        # マウスインタラクション設定を元に戻す
        if _has_physx and _physx_bindings and self._mouse_interaction_original_value is not None:
            try:
                self._settings.set(
                    _physx_bindings.SETTING_MOUSE_INTERACTION_ENABLED,
                    self._mouse_interaction_original_value
                )
            except Exception as e:
                print(f"[VR Test UI] Error restoring mouse interaction setting: {e}")

        # VR UIオブジェクトの完全削除
        if self._vr_ui_path:
            try:
                stage = omni.usd.get_context().get_stage()
                if stage:
                    vr_ui_prim = stage.GetPrimAtPath(self._vr_ui_path)
                    if vr_ui_prim and vr_ui_prim.IsValid():
                        # 非表示にする
                        from pxr import UsdGeom
                        imageable = UsdGeom.Imageable(vr_ui_prim)
                        imageable.MakeInvisible()

                        # Primを削除（GPUリソースも解放される）
                        stage.RemovePrim(self._vr_ui_path)

                    # 親Prim（XR GUI Layer Prim）も削除を試みる
                    if self._xr_gui_layer:
                        coord_path = self._xr_gui_layer.get_top_level_prim_path()
                        coord_prim = stage.GetPrimAtPath(coord_path)
                        if coord_prim and coord_prim.IsValid():
                            stage.RemovePrim(coord_path)
            except Exception as e:
                print(f"[VR Test UI] Warning: VR UI削除失敗: {e}")
                import traceback
                traceback.print_exc()

        # XR GUI Layerの解放
        if self._xr_gui_layer:
            try:
                # XR GUI Layerの明示的な解放を試みる
                self._xr_gui_layer = None
            except Exception as e:
                print(f"[VR Test UI] Warning: XR GUI Layer解放失敗: {e}")

        # XRデバイス参照のクリア
        self._left_controller_device = None
        self._right_controller_device = None
        self._xr_devices = []
        self._xr_core = None
        self._xr_profile = None

        # ウィンドウの破棄
        if self._window:
            self._window.destroy()
            self._window = None

        print("[VR Test UI] 終了完了")

    def _create_ui(self):
        """UIウィンドウの作成"""
        self._window = ui.Window("VR Test UI", width=500, height=500)

        with self._window.frame:
            # スクロール可能なフレームを作成
            with ui.ScrollingFrame(
                horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_ON,
                style={"background_color": 0xFF23211F}
            ):
                with ui.VStack(spacing=10, style={"margin": 10}):
                    # ========== コントローラー入力表示 ==========
                    ui.Label("VR Controller Input Status", style={"font_size": 20, "color": 0xFFFFFFFF})
                    ui.Separator()

                    # XR Coreの状態表示
                    if self._xr_core:
                        ui.Label("✓ XRCore Available", style={"color": 0xFF00FF00})
                    else:
                        ui.Label("✗ XRCore Not Available (VR機能なし)", style={"color": 0xFFFF0000})

                    ui.Spacer(height=5)

                    # VR UI制御のヒント
                    with ui.HStack(height=0):
                        ui.Label("💡 VR Tip:", width=80, style={"color": 0xFFFFAA00})
                        ui.Label("Press A Button (right controller) to toggle UI visibility", style={"color": 0xFFCCCCCC})
                    with ui.HStack(height=0):
                        ui.Label("", width=80)
                        ui.Label("右コントローラーのAボタンでUI表示/非表示を切り替え", style={"color": 0xFFCCCCCC})

                    ui.Spacer(height=5)

                    # 左コントローラー
                    ui.Label("Left Controller:", style={"font_size": 16})
                    with ui.VStack(spacing=3, style={"margin": 5}):
                        self._controller_labels["left_trigger"] = ui.Label("Trigger: -")
                        self._controller_labels["left_x_button"] = ui.Label("X Button: -")
                        self._controller_labels["left_y_button"] = ui.Label("Y Button: -")
                        self._controller_labels["left_thumbstick"] = ui.Label("Thumbstick: -")

                    ui.Spacer(height=5)

                    # 右コントローラー
                    ui.Label("Right Controller:", style={"font_size": 16})
                    with ui.VStack(spacing=3, style={"margin": 5}):
                        self._controller_labels["right_trigger"] = ui.Label("Trigger: -")
                        self._controller_labels["right_a_button"] = ui.Label("A Button: -")
                        self._controller_labels["right_b_button"] = ui.Label("B Button: -")
                        self._controller_labels["right_thumbstick"] = ui.Label("Thumbstick: -")

                    ui.Spacer(height=10)
                    ui.Separator()

                    # ========== テストボタン ==========
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
        # XRCoreの利用可能なメソッドとプロパティをデバッグ出力
        if self._xr_core:
            print("[VR Test UI] XRCore available methods and properties:")
            for attr in dir(self._xr_core):
                if not attr.startswith('_'):
                    print(f"  - {attr}")

            # XR Profileとデバイス情報を取得して保存
            self._xr_profile = None
            self._xr_devices = []

            try:
                if hasattr(self._xr_core, 'is_xr_display_enabled') and self._xr_core.is_xr_display_enabled():
                    print("[VR Test UI] XR Display is enabled")

                    if hasattr(self._xr_core, 'get_current_xr_profile'):
                        self._xr_profile = self._xr_core.get_current_xr_profile()
                        if self._xr_profile:
                            print(f"[VR Test UI] Current XR Profile: {self._xr_profile}")
                            print(f"[VR Test UI] Profile methods: {[m for m in dir(self._xr_profile) if not m.startswith('_')]}")

                    # XRCoreから直接デバイスリストを取得
                    if hasattr(self._xr_core, 'get_all_input_devices'):
                        try:
                            self._xr_devices = self._xr_core.get_all_input_devices()
                            print(f"[VR Test UI] Found {len(self._xr_devices)} input devices via get_all_input_devices()")
                            for i, device in enumerate(self._xr_devices):
                                print(f"[VR Test UI] Device {i}: {device}")
                                print(f"[VR Test UI] Device {i} type: {type(device)}")
                                device_methods = [m for m in dir(device) if not m.startswith('_')]
                                print(f"[VR Test UI] Device {i} methods: {device_methods}")

                                # 各メソッドの引数を調べる
                                import inspect
                                for method_name in device_methods[:15]:  # 最初の15個のメソッドを調査
                                    try:
                                        method = getattr(device, method_name)
                                        if callable(method):
                                            sig = inspect.signature(method)
                                            print(f"[VR Test UI]   {method_name}{sig}")
                                    except Exception:
                                        pass
                        except Exception as e:
                            print(f"[VR Test UI] Error calling get_all_input_devices(): {e}")

                    # 代替方法：get_input_devices() を試す（引数が必要かもしれない）
                    if not self._xr_devices and hasattr(self._xr_core, 'get_input_devices'):
                        print("[VR Test UI] Trying get_input_devices() with various parameters...")
                        # 引数なしで試す
                        try:
                            self._xr_devices = self._xr_core.get_input_devices()
                            print(f"[VR Test UI] get_input_devices() succeeded with no args: {len(self._xr_devices)} devices")
                        except TypeError as e:
                            print(f"[VR Test UI] get_input_devices() requires arguments: {e}")
                else:
                    print("[VR Test UI] XR Display is NOT enabled")
            except Exception as e:
                print(f"[VR Test UI] Error during XR initialization: {e}")
                import traceback
                traceback.print_exc()

        # 常に更新ループを開始（デバッグのため）
        update_stream = omni.kit.app.get_app().get_update_event_stream()
        self._update_subscription = update_stream.create_subscription_to_pop(
            self._on_update, name="vr_test_ui_update"
        )
        print("[VR Test UI] 更新ループを開始しました")

    def _on_update(self, e):
        """フレーム毎の更新 - コントローラー状態を取得・表示"""
        if not self._xr_core:
            return

        # デバイスが初期化されていない場合はスキップ
        if not hasattr(self, '_xr_devices') or not self._xr_devices:
            return

        # デバッグ用：最初の数フレームのみ詳細ログ
        self._debug_frame_count += 1
        debug_mode = self._debug_frame_count <= self._max_debug_frames

        try:
            # 各デバイスからコントローラー情報を取得
            for i, device in enumerate(self._xr_devices):
                if device is None:
                    continue

                # デバイス名とタイプを取得
                device_name = "Unknown"
                device_type = "Unknown"
                try:
                    device_name = str(device.get_name())
                    device_type = str(device.get_type())
                except Exception:
                    pass

                # デバッグ：最初のフレームでデバイス情報を表示
                if debug_mode and self._debug_frame_count == 1:
                    print(f"[VR Test UI] Device {i}: name='{device_name}', type='{device_type}'")
                    # 利用可能な入力名を取得
                    try:
                        input_names = device.get_input_names()
                        print(f"[VR Test UI] Device {i} inputs: {input_names}")
                    except Exception as e:
                        print(f"[VR Test UI] Device {i} get_input_names() error: {e}")

                # コントローラーのボタン状態を取得
                # Meta Quest コントローラーの一般的な入力名
                input_checks = {
                    'trigger': ['trigger', 'select', 'trigger_value'],
                    'a_button': ['a', 'button_a', 'a_button'],
                    'b_button': ['b', 'button_b', 'b_button'],
                    'x_button': ['x', 'button_x', 'x_button'],
                    'y_button': ['y', 'button_y', 'y_button'],
                    'thumbstick': ['thumbstick', 'joystick'],
                }

                # 左右のコントローラーを識別
                hand = None
                if 'left' in device_name.lower():
                    hand = 'left'
                elif 'right' in device_name.lower():
                    hand = 'right'

                if hand is None:
                    continue  # コントローラーでない場合はスキップ

                # 各入力をチェック
                for button_key, possible_names in input_checks.items():
                    button_value = 0.0  # デフォルト値
                    for input_name in possible_names:
                        try:
                            # ジェスチャー値を取得（ボタンは "click" ジェスチャー）
                            value = device.get_input_gesture_value(input_name, 'click')
                            button_value = value

                            # Aボタンは常に処理（押されていない時も含む）
                            if button_key == 'a_button' and hand == 'right':
                                self._handle_a_button_toggle(value)

                            # トリガーボタンでマウスインタラクションを制御（左右両手対応）
                            if button_key == 'trigger':
                                self._handle_trigger_mouse_interaction(value, hand)

                            # B/Yボタンでアイテム取り外し（右手=B、左手=Y）
                            if button_key == 'b_button' and hand == 'right':
                                self._handle_by_button_remove_item(value, hand)
                            if button_key == 'y_button' and hand == 'left':
                                self._handle_by_button_remove_item(value, hand)

                            break  # 最初に見つかった入力名を使用
                        except Exception:
                            # この入力名が存在しない、または値を取得できない
                            pass

                    # UIを更新（値が変わった時のみ）
                    key = f"{hand}_{button_key}"
                    if self._last_button_values.get(key) != button_value:
                        self._update_button_state(hand, button_key, button_value)
                        self._last_button_values[key] = button_value

        except Exception as e:
            if debug_mode:
                print(f"[VR Test UI] Error in _on_update: {e}")
                import traceback
                traceback.print_exc()

    def _handle_a_button_toggle(self, value):
        """AボタンでVR UI表示を切り替え（NEW: VR UI System使用）"""
        try:
            is_pressed = value > 0.5

            # ボタンが押された瞬間のみトグル（押しっぱなしでは反応しない）
            if is_pressed and not self._a_button_was_pressed:
                print("[VR Test UI] A button pressed - toggling VR UI")

                # VR UI Systemを使用してUIを切り替え
                if self._vr_ui_system:
                    self._vr_ui_system.toggle_ui()
                else:
                    print("[VR Test UI] Warning: VR UI System not initialized")

            # 現在の状態を保存
            self._a_button_was_pressed = is_pressed

        except Exception as e:
            print(f"[VR Test UI] Error in _handle_a_button_toggle: {e}")
            import traceback
            traceback.print_exc()

    def _handle_trigger_mouse_interaction(self, value, hand):
        """トリガーボタンで物理インタラクションを制御

        VRコントローラーで物体を掴む・動かす・離す
        トリガー押下 = 物体に力を加えて目標位置に引っ張る（物理演算有効）

        Args:
            value (float): トリガーの押し込み量（0.0～1.0）
            hand (str): 'left' または 'right'
        """
        try:
            if not _has_physx:
                return

            is_pressed = value > 0.5
            grab_data = self._grab_data[hand]

            # トリガーが押された瞬間 - 物体を掴む（取り外し待機モードでない場合のみ）
            if is_pressed and grab_data['grabbed_prim_path'] is None and not grab_data['awaiting_removal']:
                self._start_vr_grab_interaction(hand)

            # トリガーが押されている間 - 物体に力を加える
            elif is_pressed and grab_data['grabbed_prim_path'] is not None:
                self._update_vr_grab_interaction(hand)

            # トリガーが離された瞬間 - 物体を離す or 取り外し待機モードをリセット
            elif not is_pressed:
                if grab_data['grabbed_prim_path'] is not None:
                    self._end_vr_grab_interaction(hand)
                elif grab_data['awaiting_removal']:
                    # 取り外し待機モード中にトリガーが離されたらリセット

                    # デバッグラインを削除
                    self._delete_detachment_debug_line(hand)

                    # grab属性をFalseに戻す
                    target_path = grab_data['removal_target_path']
                    if target_path:
                        stage = omni.usd.get_context().get_stage()
                        if stage:
                            obj_prim = stage.GetPrimAtPath(target_path)
                            if obj_prim and obj_prim.IsValid():
                                grab_attr = obj_prim.GetAttribute("custom:grab")
                                if grab_attr:
                                    grab_attr.Set(False)
                                    print(f"[VR Test UI] [{hand}] custom:grab属性をFalseに戻しました")

                    # 待機モードをリセット
                    grab_data['awaiting_removal'] = False
                    grab_data['removal_target_path'] = None

        except Exception as e:
            print(f"[VR Test UI] Error in _handle_trigger_mouse_interaction ({hand}): {e}")
            import traceback
            traceback.print_exc()

    def _get_controller(self, hand):
        """コントローラーを取得（キャッシュ付き）

        Args:
            hand (str): 'left' または 'right'
        """
        # キャッシュされているコントローラーが有効ならそれを返す
        if hand == 'left':
            if self._left_controller_device is not None:
                return self._left_controller_device
        elif hand == 'right':
            if self._right_controller_device is not None:
                return self._right_controller_device

        # デバイスリストから該当する手を探す
        if hasattr(self, '_xr_devices') and self._xr_devices:
            for device in self._xr_devices:
                if device is None:
                    continue
                try:
                    device_name = str(device.get_name()).lower()
                    if hand in device_name:
                        if hand == 'left':
                            self._left_controller_device = device
                        else:
                            self._right_controller_device = device
                        print(f"[VR Test UI] {hand}手コントローラーを発見してキャッシュ: {device.get_name()}")
                        return device
                except Exception:
                    pass

        # 代替方法: get_input_device()を試す
        try:
            device = self._xr_core.get_input_device(hand)
            if device:
                if hand == 'left':
                    self._left_controller_device = device
                else:
                    self._right_controller_device = device
                print(f"[VR Test UI] get_input_device('{hand}')で{hand}手コントローラーを取得しました")
                return device
        except Exception as e:
            print(f"[VR Test UI] get_input_device('{hand}') error: {e}")

        return None

    def _get_right_controller(self):
        """右手コントローラーを取得（後方互換性のため）"""
        return self._get_controller('right')

    def _get_left_controller(self):
        """左手コントローラーを取得"""
        return self._get_controller('left')

    def _start_vr_grab_interaction(self, hand):
        """VRコントローラーで物体を掴む（トリガー押下）

        Force-based方式：物体はDynamicのまま、力を加えて目標位置に引っ張る

        Args:
            hand (str): 'left' または 'right'
        """
        try:
            grab_data = self._grab_data[hand]

            # コントローラーを取得
            controller = self._get_controller(hand)
            if not controller:
                print(f"[VR Test UI] Warning: {hand}手コントローラーが見つかりません")
                return

            # コントローラーのワールドポーズを取得
            controller_pose = controller.get_virtual_world_pose()
            controller_pos = Gf.Vec3d(
                controller_pose[3][0],
                controller_pose[3][1],
                controller_pose[3][2]
            )

            # コントローラーの前方向ベクトルを取得（Z軸の負の方向）
            forward_vec = Gf.Vec3d(
                -controller_pose[2][0],
                -controller_pose[2][1],
                -controller_pose[2][2]
            ).GetNormalized()

            print(f"[VR Test UI] VR Grab Interaction開始: pos={controller_pos}, dir={forward_vec}")

            # PhysX Raycastを実行して掴む物体を検索
            ray_length = 200.0  # 200cm
            import omni.physx
            scene_query = omni.physx.get_physx_scene_query_interface()

            if not scene_query:
                print("[VR Test UI] Warning: PhysX Scene Query Interfaceが取得できません")
                return

            # レイキャストを実行
            hit = scene_query.raycast_closest(
                tuple(controller_pos),  # origin
                tuple(forward_vec),      # direction
                ray_length               # distance
            )

            # デバッグ: Raycastの詳細情報を出力
            print(f"[VR Test UI] Raycast実行:")
            print(f"  - Origin: {controller_pos}")
            print(f"  - Direction: {forward_vec}")
            print(f"  - Ray Length: {ray_length}cm")
            print(f"  - Hit result: {hit}")

            if not hit or not hit["hit"]:
                print("[VR Test UI] 掴める物体が見つかりませんでした")
                print("[VR Test UI] 可能性:")
                print("  1. Rayがオブジェクトに当たっていない（方向が合っていない）")
                print("  2. オブジェクトにCollisionAPIが適用されていない")
                print("  3. コライダーとメッシュの位置がズレている")

                # 近くのRigidBodyを検索（診断用）
                stage = omni.usd.get_context().get_stage()
                if stage:
                    print("[VR Test UI] 近くのRigidBody一覧:")
                    for prim in stage.Traverse():
                        if prim.HasAPI(UsdPhysics.RigidBodyAPI):
                            xformable = UsdGeom.Xformable(prim)
                            if xformable:
                                world_tf = xformable.ComputeLocalToWorldTransform(0)
                                obj_pos = world_tf.ExtractTranslation()
                                distance = (obj_pos - controller_pos).GetLength()
                                if distance < 100.0:  # 100cm以内
                                    print(f"  - {prim.GetPath()}: {distance:.1f}cm away at {obj_pos}")
                return

            # ヒットした物体のパスを取得
            hit_collision_path = hit.get("collision", None)  # 実際にヒットしたメッシュ
            hit_rigidbody_path = hit.get("rigidBody", None)  # RigidBodyが適用されている親Xform

            if not hit_collision_path:
                print("[VR Test UI] ヒットしたCollisionパスがありません")
                return

            if not hit_rigidbody_path:
                print("[VR Test UI] ヒットしたPrimにRigidBodyがありません")
                return

            print(f"[VR Test UI] 物体を検出:")
            print(f"  - Collision: {hit_collision_path}")
            print(f"  - RigidBody: {hit_rigidbody_path}")
            print(f"[VR Test UI] ヒット詳細:")
            print(f"  - Hit position: {hit.get('position', 'N/A')}")
            print(f"  - Hit distance: {hit.get('distance', 'N/A')}cm")
            print(f"  - Hit normal: {hit.get('normal', 'N/A')}")

            # USD Stageを取得
            stage = omni.usd.get_context().get_stage()
            if not stage:
                print("[VR Test UI] Warning: USD Stageが取得できません")
                return

            # CollisionパスからObject Primを取得（custom属性はここにある）
            object_prim = stage.GetPrimAtPath(hit_collision_path)
            if not object_prim or not object_prim.IsValid():
                print(f"[VR Test UI] Warning: Collision Prim {hit_collision_path} が無効です")
                return

            # RigidBodyパスからPrimを取得（物理演算で使用）
            prim = stage.GetPrimAtPath(hit_rigidbody_path)
            if not prim or not prim.IsValid():
                print(f"[VR Test UI] Warning: RigidBody Prim {hit_rigidbody_path} が無効です")
                return

            # custom:grab属性を確認
            grab_attr = object_prim.GetAttribute("custom:grab")
            if not grab_attr or not grab_attr.HasValue():
                print(f"[VR Test UI] custom:grab属性がないため、通常の掴み処理をスキップ: {object_prim.GetPath()}")
                return

            # grab属性をTrueに設定
            grab_attr.Set(True)
            print(f"[VR Test UI] custom:grab属性をTrueに設定: {object_prim.GetPath()}")

            # custom:placed属性を確認
            placed_attr = object_prim.GetAttribute("custom:placed")
            is_placed = placed_attr.Get() if placed_attr and placed_attr.HasValue() else False

            if is_placed:
                # placed属性がTrueの場合は、取り外し待機モードに入る
                print(f"[VR Test UI] [{hand}] placed=Trueのオブジェクト検出: {object_prim.GetPath()}")
                print(f"[VR Test UI] [{hand}] トリガー+B/Yボタン同時押し待機モードに入ります")

                # ヒット位置を取得（デバッグライン用）
                hit_pos_raw = hit["position"]
                hit_pos = Gf.Vec3d(hit_pos_raw[0], hit_pos_raw[1], hit_pos_raw[2])

                # 取り外し用デバッグラインを作成（黄色）
                self._create_detachment_debug_line(hand, controller_pos, hit_pos)

                # 待機モードフラグを設定
                grab_data['awaiting_removal'] = True
                grab_data['removal_target_path'] = str(object_prim.GetPath())

                return  # 通常の掴み処理をスキップ

            # placed=Falseの場合は、通常の掴み処理を続行
            print(f"[VR Test UI] [{hand}] placed=Falseのオブジェクト: 通常の掴み処理を実行")

            # RigidBodyAPIを確認（Kinematicは設定しない）
            rb_api = UsdPhysics.RigidBodyAPI(prim)
            if not rb_api:
                print(f"[VR Test UI] Warning: {hit_rigidbody_path} にRigidBodyAPIがありません")
                return

            # Kinematicでないことを確認（Kinematicだと力を加えられない）
            kinematic_attr = rb_api.GetKinematicEnabledAttr()
            if kinematic_attr and kinematic_attr.Get():
                print(f"[VR Test UI] Warning: {hit_rigidbody_path} はKinematicモードなので掴めません")
                return

            # コライダー情報を診断
            print(f"[VR Test UI] オブジェクトの物理情報:")
            collision_api = UsdPhysics.CollisionAPI(prim)
            if collision_api:
                print(f"  - CollisionAPI: 適用済み")
            else:
                print(f"  - CollisionAPI: なし（警告：コライダーがない可能性）")

            # メッシュとコライダーの位置を比較
            xformable = UsdGeom.Xformable(prim)
            if xformable:
                mesh_world_pos = xformable.ComputeLocalToWorldTransform(0).ExtractTranslation()
                hit_pos = Gf.Vec3d(hit["position"][0], hit["position"][1], hit["position"][2])
                offset = mesh_world_pos - hit_pos
                print(f"  - Mesh中心位置: {mesh_world_pos}")
                print(f"  - ヒット位置: {hit_pos}")
                print(f"  - オフセット: {offset} (長さ: {offset.GetLength():.2f}cm)")

            # 子Primにコライダーがあるか確認
            collider_children = []
            for child in prim.GetChildren():
                if child.HasAPI(UsdPhysics.CollisionAPI):
                    collider_children.append(str(child.GetPath()))
            if collider_children:
                print(f"  - 子コライダー: {collider_children}")
            else:
                print(f"  - 子コライダー: なし")

            # ヒット位置をワールド座標で保存（掴んだ点）
            # hit["position"]はcarb.Float3型なので、要素ごとに取り出してGf.Vec3dに変換
            hit_pos_raw = hit["position"]
            grab_data['grab_point_world'] = Gf.Vec3d(hit_pos_raw[0], hit_pos_raw[1], hit_pos_raw[2])

            # 掴んだ点の物体に対するローカル座標を計算
            xformable = UsdGeom.Xformable(prim)
            if xformable:
                world_to_local = xformable.ComputeLocalToWorldTransform(0).GetInverse()
                grab_data['grab_point_local'] = world_to_local.Transform(grab_data['grab_point_world'])
            else:
                grab_data['grab_point_local'] = grab_data['grab_point_world']

            # 掴んだPrimのパスを保存
            grab_data['grabbed_prim_path'] = hit_rigidbody_path

            # RevoluteJointの検出
            grab_data['grabbed_joint_path'] = None
            grab_data['joint_axis'] = None
            grab_data['joint_axis_local'] = None
            grab_data['has_joint_constraint'] = False  # ★追加：制約有無フラグ
            self._detect_revolute_joint(hand, prim, stage, grab_data['grab_point_world'])

            # 初期目標位置を設定（コントローラー位置）
            grab_data['target_position'] = controller_pos

            # 累積回転をリセット
            grab_data['cumulative_rotation'] = 0.0

            # デバッグカウンタをリセット
            self._update_debug_count = 0
            self._angle_calc_debug_count = 0

            # デバッグ用の線を作成
            self._create_debug_line(hand)

            print(f"[VR Test UI] [{hand}] 物体を掴みました: {hit_rigidbody_path}")
            print(f"[VR Test UI] [{hand}] Grab point (world): {grab_data['grab_point_world']}")
            print(f"[VR Test UI] [{hand}] Grab point (local): {grab_data['grab_point_local']}")
            print(f"[VR Test UI] [{hand}] Target (controller): {grab_data['target_position']}")

            # 制御方式を表示
            if grab_data['grabbed_joint_path']:
                print(f"[VR Test UI] [{hand}] 制御方式: 角度ベース制御（DriveAPI targetPosition）")
                print(f"[VR Test UI] [{hand}] RevoluteJoint: {grab_data['grabbed_joint_path']}")
                print(f"[VR Test UI] [{hand}] Joint axis (world): {grab_data['joint_axis']}")
            elif grab_data.get('has_joint_constraint', False):
                print(f"[VR Test UI] [{hand}] 制御方式: Y軸速度制御（RevoluteJoint制約用）")
                print(f"[VR Test UI] [{hand}] コントローラーY方向の動きで回転")
            else:
                print(f"[VR Test UI] [{hand}] 制御方式: 速度ベース制御（通常オブジェクト用）")
                print(f"[VR Test UI] [{hand}] 並進速度を直接設定")

        except Exception as e:
            print(f"[VR Test UI] Error in _start_vr_grab_interaction: {e}")
            import traceback
            traceback.print_exc()

    def _detect_revolute_joint(self, hand, prim, stage, hit_position):
        """掴んだ物体に接続されているRevoluteJointを検出

        Args:
            hand (str): 'left' または 'right'
            prim: 掴んだ物体のPrim
            stage: USD Stage
            hit_position: Raycastでヒットした位置（ワールド座標）
        """
        try:
            grab_data = self._grab_data[hand]
            prim_path = str(prim.GetPath())
            print(f"[VR Test UI] [{hand}] RevoluteJoint検出開始: {prim_path}")

            # ステージ内の全てのRevoluteJointを探索
            for stage_prim in stage.Traverse():
                if stage_prim.IsA(UsdPhysics.RevoluteJoint):
                    joint = UsdPhysics.RevoluteJoint(stage_prim)

                    # Body0またはBody1が掴んだ物体かチェック
                    body0_rel = joint.GetBody0Rel()
                    body1_rel = joint.GetBody1Rel()

                    body0_targets = body0_rel.GetTargets() if body0_rel else []
                    body1_targets = body1_rel.GetTargets() if body1_rel else []

                    # 掴んだ物体がJointのいずれかのBodyに接続されているか
                    is_connected = False
                    for target in body0_targets:
                        if str(target) == prim_path:
                            is_connected = True
                            break
                    if not is_connected:
                        for target in body1_targets:
                            if str(target) == prim_path:
                                is_connected = True
                                break

                    if is_connected:
                        # RevoluteJointが見つかった
                        joint_path = str(stage_prim.GetPath())
                        print(f"[VR Test UI] [{hand}] RevoluteJoint発見: {joint_path}")

                        # ★カスタム属性チェック: custom:disable_drive = True の場合は通常の掴み処理を適用
                        disable_drive_attr = stage_prim.GetAttribute("custom:disable_drive")
                        if disable_drive_attr and disable_drive_attr.Get() == True:
                            print(f"[VR Test UI] [{hand}] custom:disable_drive=True → 力ベース制御を使用します")
                            # grabbed_joint_pathをNoneのままにして、力ベース処理にフォールバック
                            grab_data['has_joint_constraint'] = True  # ★制約ありフラグを設定
                            break

                        # custom:disable_drive=False または属性なし → Joint制御を使用
                        grab_data['grabbed_joint_path'] = joint_path

                        # Joint軸を取得（ローカル座標系）
                        axis_attr = joint.GetAxisAttr()
                        if axis_attr:
                            axis_str = axis_attr.Get()  # "X", "Y", "Z"

                            # 軸文字列をベクトルに変換
                            if axis_str.upper() == "X":
                                grab_data['joint_axis_local'] = Gf.Vec3d(1, 0, 0)
                            elif axis_str.upper() == "Y":
                                grab_data['joint_axis_local'] = Gf.Vec3d(0, 1, 0)
                            elif axis_str.upper() == "Z":
                                grab_data['joint_axis_local'] = Gf.Vec3d(0, 0, 1)
                            else:
                                print(f"[VR Test UI] [{hand}] Warning: 不明なJoint軸: {axis_str}")
                                grab_data['joint_axis_local'] = Gf.Vec3d(1, 0, 0)  # デフォルトX軸

                            print(f"[VR Test UI] [{hand}] Joint軸（ローカル、変換前）: {grab_data['joint_axis_local']}")

                            # ローカル軸をワールド座標系に変換
                            # 親の座標系が90度回転している: X→Z, Y→X, Z→Y
                            # この変換を適用
                            if axis_str.upper() == "X":
                                # X軸 → Z軸
                                grab_data['joint_axis'] = Gf.Vec3d(0, 0, 1)
                            elif axis_str.upper() == "Y":
                                # Y軸 → X軸
                                grab_data['joint_axis'] = Gf.Vec3d(1, 0, 0)
                            elif axis_str.upper() == "Z":
                                # Z軸 → Y軸
                                grab_data['joint_axis'] = Gf.Vec3d(0, 1, 0)
                            else:
                                grab_data['joint_axis'] = Gf.Vec3d(1, 0, 0)

                            print(f"[VR Test UI] [{hand}] Joint軸（ワールド、変換後）: {grab_data['joint_axis']}")
                            print(f"[VR Test UI] [{hand}] 使用したプリム: Joint={str(stage_prim.GetPath())}")

                            # Joint中心位置を設定（物体の重心を使用）
                            xformable = UsdGeom.Xformable(prim)
                            if xformable:
                                local_to_world = xformable.ComputeLocalToWorldTransform(0)
                                grab_data['joint_center'] = local_to_world.ExtractTranslation()
                                print(f"[VR Test UI] [{hand}] Joint中心位置: {grab_data['joint_center']}")

                                # 掴んだ瞬間のコントローラー角度を計算
                                # ★変更★ 中心点としてgrab_point_worldを使用
                                grab_data['initial_angle'] = self._calculate_angle_around_axis(
                                    hit_position,
                                    grab_data['grab_point_world'],
                                    grab_data['joint_axis']
                                )
                                print(f"[VR Test UI] [{hand}] 初期角度: {grab_data['initial_angle']} rad ({grab_data['initial_angle'] * 180.0 / 3.14159} deg)")

                                # ★重要★ 掴んだ瞬間にハンドルの角速度を0にリセット（振動防止）
                                try:
                                    rb_api = UsdPhysics.RigidBodyAPI(prim)
                                    if rb_api:
                                        # 線形速度と角速度を両方ゼロにする
                                        rb_api.GetVelocityAttr().Set(Gf.Vec3f(0, 0, 0))
                                        rb_api.GetAngularVelocityAttr().Set(Gf.Vec3f(0, 0, 0))
                                        print(f"[VR Test UI] [{hand}] ハンドルの速度をリセットしました")
                                except Exception as reset_error:
                                    print(f"[VR Test UI] [{hand}] 速度リセットエラー: {reset_error}")

                        break  # 最初に見つかったJointを使用

            if not grab_data['grabbed_joint_path']:
                print(f"[VR Test UI] [{hand}] RevoluteJointは見つかりませんでした")

        except Exception as e:
            print(f"[VR Test UI] Error in _detect_revolute_joint: {e}")
            import traceback
            traceback.print_exc()

    def _calculate_angle_around_axis(self, point, center, axis):
        """Joint軸周りの角度を計算

        Args:
            point: 計算対象の点（ワールド座標）
            center: Joint軸が通る中心点（ワールド座標）※現在は grab_point_world を使用
            axis: Joint軸の方向ベクトル（正規化済み）

        Returns:
            float: 角度（ラジアン、-π ~ +π）
        """
        import math

        # grab_point_worldから点へのベクトル
        vec = point - center

        # Joint軸に垂直な平面に投影
        # 投影ベクトル = vec - (vec · axis) * axis
        projection_along_axis = vec.GetDot(axis)
        vec_projected = vec - axis * projection_along_axis

        # 投影ベクトルの長さをチェック（ほぼゼロの場合は角度を計算できない）
        length = vec_projected.GetLength()
        if length < 0.001:
            return 0.0

        # 正規化
        vec_projected = vec_projected / length

        # 軸に垂直な2つの基底ベクトルを作成
        # 基底1: 軸に垂直な任意のベクトル
        if abs(axis[0]) < 0.9:
            basis1 = Gf.Vec3d(1, 0, 0)
        else:
            basis1 = Gf.Vec3d(0, 1, 0)

        # 基底1を軸に垂直な平面に投影して正規化
        basis1 = basis1 - axis * basis1.GetDot(axis)
        basis1 = basis1.GetNormalized()

        # 基底2: 軸 × 基底1（右手系）
        basis2 = axis.GetCross(basis1).GetNormalized()

        # 投影ベクトルを2つの基底で表現
        x = vec_projected.GetDot(basis1)
        y = vec_projected.GetDot(basis2)

        # atan2で角度を計算（-π ~ +π）
        angle = math.atan2(y, x)

        # デバッグ出力（最初の数回のみ）
        if not hasattr(self, '_angle_calc_debug_count'):
            self._angle_calc_debug_count = 0

        if self._angle_calc_debug_count < 3:
            print(f"[VR Test UI] [角度計算デバッグ]")
            print(f"  Joint軸（ワールド）: {axis}")
            print(f"  回転中心（grab_point_world）: {center}")
            print(f"  コントローラー位置: {point}")
            print(f"  軸方向成分: {projection_along_axis:.3f}")
            print(f"  投影ベクトル長: {length:.3f}")
            print(f"  基底1: {basis1}")
            print(f"  基底2: {basis2}")
            print(f"  座標 (x, y): ({x:.3f}, {y:.3f})")
            print(f"  計算角度: {angle * 180.0 / math.pi:.1f}°")
            self._angle_calc_debug_count += 1

        return angle

    def _update_vr_grab_interaction(self, hand):
        """VRコントローラーの動きに合わせて掴んだ点に力を加える（トリガー押下中）

        RevoluteJointがある場合: Joint軸周りのトルクのみを適用
        RevoluteJointがない場合: Mouse Interaction方式（掴んだ特定の点に力を加える）

        Args:
            hand (str): 'left' または 'right'
        """
        try:
            grab_data = self._grab_data[hand]

            if not grab_data['grabbed_prim_path'] or not grab_data['grab_point_local']:
                return

            # コントローラーを取得
            controller = self._get_controller(hand)
            if not controller:
                return

            # コントローラーのワールドポーズを取得（目標位置）
            controller_pose = controller.get_virtual_world_pose()
            grab_data['target_position'] = Gf.Vec3d(
                controller_pose[3][0],
                controller_pose[3][1],
                controller_pose[3][2]
            )

            # USD Stageを取得
            stage = omni.usd.get_context().get_stage()
            if not stage:
                return

            # Primを取得
            prim = stage.GetPrimAtPath(grab_data['grabbed_prim_path'])
            if not prim or not prim.IsValid():
                print(f"[VR Test UI] [{hand}] Warning: 掴んだPrim {grab_data['grabbed_prim_path']} が無効になりました")
                grab_data['grabbed_prim_path'] = None
                return

            # Xformableを取得
            xformable = UsdGeom.Xformable(prim)
            if not xformable:
                return

            # 掴んだ点の現在のワールド座標を計算
            local_to_world = xformable.ComputeLocalToWorldTransform(0)
            current_grab_point_world = local_to_world.Transform(grab_data['grab_point_local'])

            # RigidBodyAPIを取得
            rb_api = UsdPhysics.RigidBodyAPI(prim)
            if not rb_api:
                return

            # 掴んだ点での速度を計算（物体の回転も考慮）
            velocity_attr = rb_api.GetVelocityAttr()
            angular_velocity_attr = rb_api.GetAngularVelocityAttr()

            linear_velocity = velocity_attr.Get() if velocity_attr else Gf.Vec3f(0, 0, 0)
            angular_velocity = angular_velocity_attr.Get() if angular_velocity_attr else Gf.Vec3f(0, 0, 0)

            if linear_velocity is None:
                linear_velocity = Gf.Vec3f(0, 0, 0)
            if angular_velocity is None:
                angular_velocity = Gf.Vec3f(0, 0, 0)

            # 物体の重心位置
            object_center = local_to_world.ExtractTranslation()

            # 掴んだ点と重心の距離ベクトル
            r = current_grab_point_world - object_center

            # 掴んだ点での速度 = 並進速度 + (角速度 × 距離ベクトル)
            point_velocity = Gf.Vec3d(linear_velocity) + Gf.Vec3d(angular_velocity).GetCross(r)

            # Spring-Damper力を計算
            displacement = grab_data['target_position'] - current_grab_point_world
            distance = displacement.GetLength()

            # RevoluteJointが検出されている場合はトルクベース処理
            if grab_data['grabbed_joint_path'] and grab_data['joint_axis']:
                self._apply_joint_torque(
                    hand,
                    prim,
                    r,
                    displacement,
                    angular_velocity,
                    object_center
                )
            else:
                # ★★★ 条件分岐：RevoluteJoint制約の有無で処理を切り替え ★★★
                if grab_data.get('has_joint_constraint', False):
                    # ═══ 新規：Y軸速度制御（RevoluteJoint制約用）═══
                    try:
                        # コントローラーのY方向の変位を計算
                        y_displacement = grab_data['target_position'][1] - current_grab_point_world[1]

                        """if y_displacement <= 0:
                            new_y_velocity = 0
                            rb_api.GetVelocityAttr().Set(Gf.Vec3f(0, float(new_y_velocity), 0))
                            return"""

                        """# 目標Y軸速度を計算（絶対値を使用して常に正の速度）
                        dt = 1.0 / 60.0  # 60 FPS
                        velocity_multiplier = 1.0  # 速度増幅
                        target_y_velocity = (abs(y_displacement) / dt) * velocity_multiplier

                        # 速度を制限
                        max_velocity = 500.0  # m/s
                        if abs(target_y_velocity) > max_velocity:
                            target_y_velocity = max_velocity if target_y_velocity > 0 else -max_velocity

                        # 現在のY軸速度を取得
                        current_y_velocity = float(linear_velocity[1]) if linear_velocity else 0.0

                        # Spring-Damper制御で速度を調整
                        velocity_error = target_y_velocity - current_y_velocity
                        velocity_adjustment = velocity_error * 0.5  # ゲイン

                        new_y_velocity = current_y_velocity + velocity_adjustment"""

                        new_y_velocity = y_displacement * (-4.0) #ゲイン ＋　ハンドルを下におろす動作をするため符号逆転

                        # Y軸速度のみを設定（X, Z は0）
                        rb_api.GetVelocityAttr().Set(Gf.Vec3f(0, float(new_y_velocity), 0))

                        if self._update_debug_count <= 5:
                            print(f"[VR Test UI] [{hand}] Y軸速度制御（RevoluteJoint制約用）:")
                            print(f"[VR Test UI] Y displacement: {y_displacement:.2f} cm")
                            #print(f"[VR Test UI] Target Y velocity: {target_y_velocity:.2f}")
                            print(f"[VR Test UI] New Y velocity: {new_y_velocity:.2f}")

                    except Exception as e:
                        if self._update_debug_count <= 5:
                            print(f"[VR Test UI] Y-axis velocity control error: {e}")
                            import traceback
                            traceback.print_exc()

                else:
                    # ═══ 既存：速度ベース制御（通常オブジェクト用）═══
                    # Spring力
                    spring_force = displacement * self._grab_force_strength

                    # Damping力
                    damping_force = point_velocity * (-self._grab_damping * self._grab_force_strength)

                    # 合成力
                    total_force = spring_force + damping_force

                    # PhysX Simulation Interfaceを使って特定の点に力を加える
                    # USD RigidBodyAPIを直接使用して速度ベースの制御を行う
                    try:
                        # 目標速度を計算（100倍に増幅）
                        dt = 1.0 / 60.0  # 60 FPSと仮定
                        velocity_multiplier = 5.0  # 速度を100倍に増幅
                        target_velocity = (displacement / dt) * velocity_multiplier if distance > 0.001 else Gf.Vec3d(0, 0, 0)

                        # 速度を制限（100倍に調整）
                        max_velocity = 500.0  # m/s (5.0 * 100)
                        if target_velocity.GetLength() > max_velocity:
                            target_velocity = target_velocity.GetNormalized() * max_velocity

                        # RigidBodyAPIで速度を設定
                        current_velocity = Gf.Vec3d(linear_velocity)

                        # Spring-Damper制御で速度を調整
                        velocity_error = target_velocity - current_velocity
                        velocity_adjustment = velocity_error * 0.5  # ゲイン

                        new_velocity = current_velocity + velocity_adjustment

                        # 速度を適用
                        rb_api.GetVelocityAttr().Set(Gf.Vec3f(
                            float(new_velocity[0]),
                            float(new_velocity[1]),
                            float(new_velocity[2])
                        ))

                        if self._update_debug_count <= 5:
                            print(f"[VR Test UI] [{hand}] 速度ベース制御（通常オブジェクト用）")
                            print(f"  Setting velocity {new_velocity} (target: {target_velocity})")

                    except Exception as e:
                        if self._update_debug_count <= 5:
                            print(f"[VR Test UI] Velocity-based control error: {e}")
                            import traceback
                            traceback.print_exc()

            # デバッグ用の線を更新
            self._update_debug_line(hand, current_grab_point_world, grab_data['target_position'])

        except Exception as e:
            print(f"[VR Test UI] [{hand}] Error in _update_vr_grab_interaction: {e}")
            import traceback
            traceback.print_exc()

    def _apply_joint_torque(self, hand, prim, r, displacement, angular_velocity, object_center):
        """RevoluteJoint用：角度ベース制御（方法A）

        コントローラーのJoint軸周りの角度変化を直接ハンドルの回転に反映

        Args:
            hand (str): 'left' または 'right'
            prim: 掴んだ物体のPrim
            r: 掴んだ点と重心の距離ベクトル（未使用）
            displacement: 目標位置と掴んだ点の変位ベクトル（未使用）
            angular_velocity: 物体の角速度
            object_center: 物体の重心位置
        """
        import math

        try:
            grab_data = self._grab_data[hand]

            # 1. 現在のコントローラー位置からJoint軸周りの角度を計算
            # ★変更★ 中心点としてgrab_point_worldを使用
            current_angle = self._calculate_angle_around_axis(
                grab_data['target_position'],      # 現在のコントローラー位置
                grab_data['grab_point_world'],     # 掴んだ点を中心として使用
                grab_data['joint_axis']            # Joint軸
            )

            # 2. 前回の角度からの差分を計算（累積回転を追跡）
            # ★改善★ handle_angleと同じアルゴリズムを使用
            if not hasattr(self, '_previous_angle_' + hand):
                setattr(self, '_previous_angle_' + hand, current_angle)  # ← 初回はatan2の生値を保存
                setattr(self, '_unwrapped_angle_' + hand, current_angle)  # ← 初回はatan2の生値を保存

            previous_angle = getattr(self, '_previous_angle_' + hand)
            unwrapped_angle = getattr(self, '_unwrapped_angle_' + hand)

            # handle_angleの _calculate_angle_delta() と同じアルゴリズム
            # 前回の角度(atan2生値)と現在の角度(atan2生値)の差分を計算
            raw_delta = current_angle - previous_angle

            # -180～+180の範囲に正規化
            while raw_delta > math.pi:
                raw_delta -= 2 * math.pi
            while raw_delta < -math.pi:
                raw_delta += 2 * math.pi

            # 大きな角度変化の検出と補正（回転方向の連続性を保持）
            if abs(raw_delta) > (150 * math.pi / 180):  # 150°以上の変化を検出
                # 逆方向の可能性をチェック
                alternative_delta = raw_delta - 2 * math.pi if raw_delta > 0 else raw_delta + 2 * math.pi

                # より小さい変化を採用（連続性を保持）
                if abs(alternative_delta) < abs(raw_delta):
                    if self._update_debug_count <= 5:
                        print(f"[VR Test UI] [{hand}] [角度補正] 大きな変化を検出: 元={raw_delta * 180 / math.pi:.1f}°, 補正後={alternative_delta * 180 / math.pi:.1f}°")
                    raw_delta = alternative_delta

            # アンラップ済み角度を更新（境界越えを考慮した連続値）
            unwrapped_angle += raw_delta

            # 累積回転量 = アンラップ済み角度 - 初期角度
            grab_data['cumulative_rotation'] = unwrapped_angle - grab_data['initial_angle']

            # 次回のために現在の角度を保存
            # ★重要★ atan2の生値を保存（handle_angleと同じ方式）
            setattr(self, '_previous_angle_' + hand, current_angle)
            setattr(self, '_unwrapped_angle_' + hand, unwrapped_angle)

            angle_delta_this_frame = raw_delta  # デバッグ表示用

            # デバッグ出力（常に表示）
            print(f"[VR Test UI] [{hand}] 初期角度: {grab_data['initial_angle'] * 180.0 / math.pi:.1f}°")
            print(f"[VR Test UI] [{hand}] 現在角度(atan2): {current_angle * 180.0 / math.pi:.1f}°")
            print(f"[VR Test UI] [{hand}] アンラップ済み角度: {unwrapped_angle * 180.0 / math.pi:.1f}°")
            print(f"[VR Test UI] [{hand}] 今回フレームの角度変化: {angle_delta_this_frame * 180.0 / math.pi:.1f}°")
            print(f"[VR Test UI] [{hand}] 累積回転: {grab_data['cumulative_rotation'] * 180.0 / math.pi:.1f}°")

            # 3. デッドゾーン処理（小さな変化を無視して振動を防止）
            dead_zone_angle = 0.01  # rad（約0.6度）- 小さめに設定
            if abs(angle_delta_this_frame) < dead_zone_angle:
                # 変化が小さすぎる場合はスキップ（現在の目標位置を維持）
                if self._update_debug_count <= 5:
                    print(f"[VR Test UI] [{hand}] デッドゾーン内: 角度変化 {angle_delta_this_frame * 180.0 / 3.14159:.2f}° < {dead_zone_angle * 180.0 / 3.14159:.2f}°")

            # 4. Joint Limitの取得とクランプ処理
            # ★重要★ RevoluteJointのLimitを取得し、目標角度をクランプ
            stage = omni.usd.get_context().get_stage()
            joint_lower_limit_deg = None
            joint_upper_limit_deg = None

            if stage and grab_data['grabbed_joint_path']:
                joint_prim = stage.GetPrimAtPath(grab_data['grabbed_joint_path'])
                if joint_prim and joint_prim.IsValid():
                    # RevoluteJointのLimit属性を取得
                    revolute_joint = UsdPhysics.RevoluteJoint(joint_prim)
                    if revolute_joint:
                        lower_limit_attr = revolute_joint.GetLowerLimitAttr()
                        upper_limit_attr = revolute_joint.GetUpperLimitAttr()

                        if lower_limit_attr and lower_limit_attr.HasValue():
                            joint_lower_limit_deg = lower_limit_attr.Get()
                        if upper_limit_attr and upper_limit_attr.HasValue():
                            joint_upper_limit_deg = upper_limit_attr.Get()

            # Limit情報をログ出力（初回のみ）
            if not hasattr(self, f'_joint_limit_logged_{hand}'):
                if joint_lower_limit_deg is not None or joint_upper_limit_deg is not None:
                    print(f"[VR Test UI] [{hand}] Joint Limits検出:")
                    print(f"  - Lower: {joint_lower_limit_deg}°" if joint_lower_limit_deg is not None else "  - Lower: 無制限")
                    print(f"  - Upper: {joint_upper_limit_deg}°" if joint_upper_limit_deg is not None else "  - Upper: 無制限")
                else:
                    print(f"[VR Test UI] [{hand}] Joint Limits: 制限なし")
                setattr(self, f'_joint_limit_logged_{hand}', True)

            # 目標角度を累積回転として設定（位置ベース制御）
            # コントローラーが回転した分だけハンドルも回転させる
            target_joint_angle = grab_data['cumulative_rotation']

            # ★重要★ 目標角度をJoint Limitでクランプ（degrees単位で比較）
            # rad → deg に変換してクランプ、その後 deg → rad に戻す
            target_joint_angle_deg = target_joint_angle * (180.0 / math.pi)

            # ★修正★ 符号を反転（DriveAPIの回転方向がcumulative_rotationと逆のため）
            target_joint_angle_deg = -target_joint_angle_deg

            clamped = False
            if joint_lower_limit_deg is not None and target_joint_angle_deg < joint_lower_limit_deg:
                target_joint_angle_deg = joint_lower_limit_deg
                clamped = True
            if joint_upper_limit_deg is not None and target_joint_angle_deg > joint_upper_limit_deg:
                target_joint_angle_deg = joint_upper_limit_deg
                clamped = True

            if clamped:
                print(f"[VR Test UI] [{hand}] ⚠️ 目標角度をLimitでクランプ: {target_joint_angle_deg:.1f}° (元: {-target_joint_angle * (180.0 / math.pi):.1f}°)")

            if self._update_debug_count <= 5:
                print(f"[VR Test UI] [{hand}] 目標Joint角度: {target_joint_angle_deg:.1f}° (累積回転: {grab_data['cumulative_rotation'] * 180.0 / math.pi:.1f}°)")
                print(f"[VR Test UI] [{hand}] 制御モード: 位置ベース（DriveAPI targetPosition）")

            # 5. DriveAPIで位置制御を適用（RevoluteJoint制御の正しい方法）
            try:
                # _joint_pathではなく_grabbed_joint_pathを使用
                if stage and grab_data['grabbed_joint_path']:
                    joint_prim = stage.GetPrimAtPath(grab_data['grabbed_joint_path'])
                    if joint_prim and joint_prim.IsValid():
                        # RevoluteJointのDriveAPIを取得/適用
                        # UsdPhysics.DriveAPIのトークンは "angular" (回転Joint用)
                        drive_api = UsdPhysics.DriveAPI.Get(joint_prim, "angular")
                        if not drive_api:
                            drive_api = UsdPhysics.DriveAPI.Apply(joint_prim, "angular")

                        if drive_api:
                            # ★重要★ 位置ベース制御に変更（コントローラーの回転をハンドルに直接反映）
                            # targetPositionの単位は degrees (度)
                            # 既にクランプ済みのtarget_joint_angle_degを使用

                            # DriveAPIで位置制御（掴んでいる間はリアルタイムで連動）
                            # targetPosition: 目標角度 (degrees = 度)
                            # stiffness: 位置制御の剛性（大きいほど速く目標位置に到達）
                            # damping: 減衰係数（大きいほど滑らかだが応答が遅い）
                            # maxForce: 最大トルク
                            # type: "force" または "acceleration"

                            drive_api.GetTargetPositionAttr().Set(float(target_joint_angle_deg))
                            drive_api.GetStiffnessAttr().Set(200000.0)  # 位置モード（高剛性でコントローラーに追従）
                            drive_api.GetDampingAttr().Set(20000.0)     # 減衰力（振動抑制しつつ応答性確保）
                            drive_api.GetMaxForceAttr().Set(500000.0)   # 最大トルク（十分な力で追従）

                            # DriveTypeを設定（force or acceleration）
                            type_attr = drive_api.GetTypeAttr()
                            if not type_attr or not type_attr.Get():
                                # Tokenとして"force"を設定
                                from pxr import Sdf
                                drive_api.CreateTypeAttr(Sdf.ValueTypeNames.Token)
                                drive_api.GetTypeAttr().Set("force")

                            if self._update_debug_count <= 5:
                                print(f"[VR Test UI] [{hand}] DriveAPI設定成功（位置ベース制御）:")
                                print(f"  - targetPosition: {target_joint_angle_deg:.2f} deg")
                                print(f"  - stiffness: 200000.0, damping: 20000.0, maxForce: 500000.0")
                                print(f"  - joint: {grab_data['grabbed_joint_path']}")
                        else:
                            if self._update_debug_count <= 5:
                                print(f"[VR Test UI] [{hand}] DriveAPI取得/適用失敗")
                    else:
                        if self._update_debug_count <= 5:
                            print(f"[VR Test UI] [{hand}] Joint Prim無効: {grab_data['grabbed_joint_path']}")
                else:
                    if self._update_debug_count <= 5:
                        if not grab_data['grabbed_joint_path']:
                            print(f"[VR Test UI] [{hand}] _grabbed_joint_pathが未設定")
                        elif not stage:
                            print(f"[VR Test UI] [{hand}] Stageが取得できません")

            except Exception as e:
                print(f"[VR Test UI] [{hand}] DriveAPI位置制御エラー: {e}")
                import traceback
                traceback.print_exc()

        except Exception as e:
            print(f"[VR Test UI] [{hand}] Error in _apply_joint_torque: {e}")
            import traceback
            traceback.print_exc()

    def _end_vr_grab_interaction(self, hand):
        """VRコントローラーで掴んだ物体を離す（トリガー離した）

        力の適用を停止するだけ（物体はDynamicのまま）

        Args:
            hand (str): 'left' または 'right'
        """
        try:
            grab_data = self._grab_data[hand]

            if not grab_data['grabbed_prim_path']:
                return

            # ★追加★ RevoluteJointの場合、DriveAPI targetPositionを初期位置(0.0)にリセット
            if grab_data['grabbed_joint_path']:
                try:
                    stage = omni.usd.get_context().get_stage()
                    if stage:
                        joint_prim = stage.GetPrimAtPath(grab_data['grabbed_joint_path'])
                        if joint_prim and joint_prim.IsValid():
                            drive_api = UsdPhysics.DriveAPI.Get(joint_prim, "angular")
                            if drive_api:
                                # 初期位置(0.0度)にリセット
                                drive_api.GetTargetPositionAttr().Set(0.0)
                                print(f"[VR Test UI] [{hand}] DriveAPI targetPositionを0.0度にリセット")
                except Exception as e:
                    print(f"[VR Test UI] [{hand}] DriveAPI リセット失敗: {e}")

            # デバッグ用の線を削除
            self._delete_debug_line(hand)

            # 状態をリセット（物理設定は変更しない）
            print(f"[VR Test UI] [{hand}] 物体を離しました: {grab_data['grabbed_prim_path']}")
            if grab_data['grabbed_joint_path']:
                print(f"[VR Test UI] [{hand}] RevoluteJoint制約付き物体を解放しました")
            print(f"[VR Test UI] [{hand}] 物体は慣性と重力の影響を受けて動き続けます")

            grabbed_joint_path = grab_data['grabbed_joint_path']  # リセット前に保存

            # ★追加★ custom:grab属性をFalseに戻す
            grabbed_prim_path = grab_data['grabbed_prim_path']
            if grabbed_prim_path:
                stage = omni.usd.get_context().get_stage()
                if stage:
                    grabbed_prim = stage.GetPrimAtPath(grabbed_prim_path)
                    if grabbed_prim and grabbed_prim.IsValid():
                        # 掴んだPrim自体のcustom:grab属性をチェック
                        grab_attr = grabbed_prim.GetAttribute("custom:grab")
                        if grab_attr:
                            grab_attr.Set(False)
                            print(f"[VR Test UI] [{hand}] custom:grab属性をFalseに戻しました: {grabbed_prim_path}")

                        # 子Meshのcustom:grab属性もチェック
                        for child in grabbed_prim.GetChildren():
                            if child.IsA(UsdGeom.Mesh):
                                child_grab_attr = child.GetAttribute("custom:grab")
                                if child_grab_attr:
                                    child_grab_attr.Set(False)
                                    print(f"[VR Test UI] [{hand}] 子Meshのcustom:grab属性をFalseに戻しました: {child.GetPath()}")

            grab_data['grabbed_prim_path'] = None
            grab_data['grab_point_world'] = None
            grab_data['grab_point_local'] = None
            grab_data['target_position'] = None
            grab_data['grabbed_joint_path'] = None
            grab_data['joint_axis'] = None
            grab_data['joint_axis_local'] = None
            grab_data['joint_center'] = None
            grab_data['initial_angle'] = None
            grab_data['cumulative_rotation'] = 0.0

            # 累積回転もリセット
            if hasattr(self, '_previous_angle_' + hand):
                delattr(self, '_previous_angle_' + hand)
            if hasattr(self, '_unwrapped_angle_' + hand):
                delattr(self, '_unwrapped_angle_' + hand)

        except Exception as e:
            print(f"[VR Test UI] [{hand}] Error in _end_vr_grab_interaction: {e}")
            import traceback
            traceback.print_exc()

    def _create_debug_line(self, hand):
        """デバッグ用の線を作成（緑の線の代わり）

        Args:
            hand (str): 'left' または 'right'
        """
        try:
            grab_data = self._grab_data[hand]
            stage = omni.usd.get_context().get_stage()
            if not stage:
                return

            # 線用のPrimパス（左右で別々）
            debug_line_prim = f"/World/_VR_Debug_Line_{hand}"

            # 既存の線を削除
            if stage.GetPrimAtPath(debug_line_prim):
                stage.RemovePrim(debug_line_prim)

            # BasisCurvesを作成（線を描画）
            from pxr import UsdGeom
            curves = UsdGeom.BasisCurves.Define(stage, debug_line_prim)

            # 線のタイプを設定
            curves.CreateTypeAttr("linear")
            curves.CreateWrapAttr("nonperiodic")

            # 頂点数を設定（2点で1本の線）
            curves.CreateCurveVertexCountsAttr([2])

            # 初期位置（後で更新される）
            curves.CreatePointsAttr([grab_data['grab_point_world'], grab_data['target_position']])

            # 線の太さ
            curves.CreateWidthsAttr([2.0])

            # 色を設定（左手=青、右手=緑）
            from pxr import UsdShade, Sdf
            if hand == 'left':
                curves.CreateDisplayColorAttr([(0.0, 0.0, 1.0)])  # 青
            else:
                curves.CreateDisplayColorAttr([(0.0, 1.0, 0.0)])  # 緑

            grab_data['debug_line_prim'] = debug_line_prim
            print(f"[VR Test UI] [{hand}] デバッグ用の線を作成: {debug_line_prim}")

        except Exception as e:
            print(f"[VR Test UI] [{hand}] Error creating debug line: {e}")

    def _update_debug_line(self, hand, start_point, end_point):
        """デバッグ用の線を更新

        Args:
            hand (str): 'left' または 'right'
            start_point: 開始点
            end_point: 終了点
        """
        try:
            grab_data = self._grab_data[hand]
            if not grab_data['debug_line_prim']:
                return

            stage = omni.usd.get_context().get_stage()
            if not stage:
                return

            prim = stage.GetPrimAtPath(grab_data['debug_line_prim'])
            if not prim or not prim.IsValid():
                return

            from pxr import UsdGeom
            curves = UsdGeom.BasisCurves(prim)

            # 線の頂点を更新
            curves.GetPointsAttr().Set([start_point, end_point])

        except Exception:
            pass  # 更新エラーは無視

    def _delete_debug_line(self, hand):
        """デバッグ用の線を削除

        Args:
            hand (str): 'left' または 'right'
        """
        try:
            grab_data = self._grab_data[hand]
            if not grab_data['debug_line_prim']:
                return

            stage = omni.usd.get_context().get_stage()
            if not stage:
                return

            if stage.GetPrimAtPath(grab_data['debug_line_prim']):
                stage.RemovePrim(grab_data['debug_line_prim'])
                print(f"[VR Test UI] [{hand}] デバッグ用の線を削除: {grab_data['debug_line_prim']}")

            grab_data['debug_line_prim'] = None

        except Exception as e:
            print(f"[VR Test UI] Error deleting debug line: {e}")

    def _create_detachment_debug_line(self, hand, start_point, end_point):
        """取り外し検出用のデバッグ線を作成

        Args:
            hand (str): 'left' または 'right'
            start_point: 開始点（コントローラー位置）
            end_point: 終了点（ヒット位置）
        """
        try:
            stage = omni.usd.get_context().get_stage()
            if not stage:
                return

            # 線用のPrimパス（取り外し専用）
            debug_line_prim = f"/World/_VR_Detach_Debug_Line_{hand}"

            # 既存の線を削除
            if stage.GetPrimAtPath(debug_line_prim):
                stage.RemovePrim(debug_line_prim)

            # BasisCurvesを作成（線を描画）
            from pxr import UsdGeom
            curves = UsdGeom.BasisCurves.Define(stage, debug_line_prim)

            # 線のタイプを設定
            curves.CreateTypeAttr("linear")
            curves.CreateWrapAttr("nonperiodic")

            # 頂点数を設定（2点で1本の線）
            curves.CreateCurveVertexCountsAttr([2])

            # 線の頂点を設定
            curves.CreatePointsAttr([start_point, end_point])

            # 線の太さ
            curves.CreateWidthsAttr([3.0])

            # 色を設定（黄色で目立たせる）
            curves.CreateDisplayColorAttr([(1.0, 1.0, 0.0)])

            # 状態を保存（削除用）
            if not hasattr(self, '_detachment_debug_lines'):
                self._detachment_debug_lines = {}
            self._detachment_debug_lines[hand] = debug_line_prim

            print(f"[VR Test UI] [{hand}] 取り外し用デバッグ線を作成: {debug_line_prim}")

        except Exception as e:
            print(f"[VR Test UI] [{hand}] Error creating detachment debug line: {e}")

    def _delete_detachment_debug_line(self, hand):
        """取り外し検出用のデバッグ線を削除

        Args:
            hand (str): 'left' または 'right'
        """
        try:
            if not hasattr(self, '_detachment_debug_lines'):
                return

            if hand not in self._detachment_debug_lines:
                return

            debug_line_prim = self._detachment_debug_lines[hand]
            stage = omni.usd.get_context().get_stage()
            if not stage:
                return

            if stage.GetPrimAtPath(debug_line_prim):
                stage.RemovePrim(debug_line_prim)
                print(f"[VR Test UI] [{hand}] 取り外し用デバッグ線を削除: {debug_line_prim}")

            del self._detachment_debug_lines[hand]

        except Exception as e:
            print(f"[VR Test UI] Error deleting detachment debug line: {e}")

    def _update_button_state(self, hand, button, value):
        """ボタン状態をUIに反映"""
        try:
            # ボタンラベルの色を変更
            label_key = f"{hand}_{button}"
            if label_key in self._controller_labels:
                is_pressed = value > 0.5
                # 押されている場合は"Pressed"、押されていない場合は"-"
                status_text = "Pressed" if is_pressed else "-"

                # UIラベルを更新
                self._controller_labels[label_key].text = f"{button.replace('_', ' ').title()}: {status_text}"

                # 押されている場合は緑、そうでない場合は灰色
                color = 0xFF00FF00 if is_pressed else 0xFF888888
                self._controller_labels[label_key].style = {"color": color}
            else:
                # ラベルが見つからない場合はログ出力（初回のみ）
                if not hasattr(self, '_missing_labels'):
                    self._missing_labels = set()
                if label_key not in self._missing_labels:
                    print(f"[VR Test UI] Warning: Label '{label_key}' not found in _controller_labels")
                    self._missing_labels.add(label_key)
        except Exception as e:
            print(f"[VR Test UI] Error in _update_button_state: {e}")
            import traceback
            traceback.print_exc()

    def _handle_by_button_remove_item(self, value, hand):
        """B/Yボタンでアイテムを取り外す

        placed属性がTrueのオブジェクトに対して、B(右手)またはY(左手)ボタンを押すと
        item_settingのremove_itemメソッドを呼び出して取り外す

        Args:
            value (float): ボタンの押し込み量（0.0～1.0）
            hand (str): 'left' または 'right'
        """
        try:
            is_pressed = value > 0.5
            grab_data = self._grab_data[hand]

            # 取り外し待機モードでない場合は何もしない
            if not grab_data['awaiting_removal']:
                return

            # トリガーが押されているか確認（トリガー+B/Y同時押しが必要）
            controller = self._get_controller(hand)
            if not controller:
                return

            trigger_value = controller.get_input_gesture_value('trigger', 'value')
            if trigger_value <= 0.5:  # トリガーが押されていない
                return

            # ボタンが押された瞬間のみ処理
            if not hasattr(self, '_by_button_was_pressed'):
                self._by_button_was_pressed = {'left': False, 'right': False}

            if is_pressed and not self._by_button_was_pressed[hand]:
                # トリガー+B/Yボタンが同時押しされた瞬間
                print(f"[VR Test UI] [{hand}] トリガー+{'B' if hand == 'right' else 'Y'}同時押し - アイテム取り外し実行")

                # 取り外し対象のパスを保存（リセット前に）
                target_path = grab_data['removal_target_path']

                # item_settingのremove_itemメソッドを呼び出す
                # （内部でproxy属性を自動判定して適切な処理を実行）
                try:
                    import item_setting
                    ext_instance = item_setting.get_extension_instance()
                    if ext_instance:
                        print(f"[VR Test UI] [{hand}] item_setting.remove_item()を呼び出します: {target_path}")
                        ext_instance.remove_item(target_path)
                        print(f"[VR Test UI] [{hand}] アイテム取り外し完了: {target_path}")
                    else:
                        print(f"[VR Test UI] [{hand}] Warning: item_setting拡張機能のインスタンスが取得できません")
                except Exception as e:
                    print(f"[VR Test UI] [{hand}] Error calling item_setting.remove_item(): {e}")
                    import traceback
                    traceback.print_exc()

                # grab属性をFalseに戻す（オブジェクトのgrab属性）
                stage = omni.usd.get_context().get_stage()
                if stage and target_path:
                    obj_prim = stage.GetPrimAtPath(target_path)
                    if obj_prim and obj_prim.IsValid():
                        grab_attr = obj_prim.GetAttribute("custom:grab")
                        if grab_attr:
                            grab_attr.Set(False)
                            print(f"[VR Test UI] [{hand}] custom:grab属性をFalseに戻しました")

                # デバッグラインを削除
                self._delete_detachment_debug_line(hand)

                # 取り外し待機モードをリセット
                grab_data['awaiting_removal'] = False
                grab_data['removal_target_path'] = None

            self._by_button_was_pressed[hand] = is_pressed

        except Exception as e:
            print(f"[VR Test UI] Error in _handle_by_button_remove_item ({hand}): {e}")
            import traceback
            traceback.print_exc()

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
