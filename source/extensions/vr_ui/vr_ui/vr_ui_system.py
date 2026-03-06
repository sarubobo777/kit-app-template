# coding: utf-8
"""
VR UI System - HMD前方に固定表示する3D UIシステム

Aボタンで表示切り替え、HMD前方150cmに固定配置（ビルボードなし）
"""

import omni.ext
import omni.ui as ui
import omni.usd
import omni.kit.app
from omni.kit.xr.scene_view.utils import (
    UiContainer,
    WidgetComponent,
)
from omni.kit.xr.scene_view.utils.spatial_source import SpatialSource
from omni.kit.xr.scene_view.core import XRSceneView
from pxr import Usd, UsdGeom, Gf
import carb
import os
import math
from pathlib import Path


class ImageViewerWidget(ui.Frame):
    """画像ビューアーウィジェット

    機能:
    - タスク表示（上部）
    - 画像表示（中央）
    - 進む/戻るボタン（下部）
    """

    def __init__(self, image_folder: str = None, **kwargs):
        super().__init__(**kwargs)

        self._image_folder = image_folder or ""
        self._image_files = []
        self._current_index = 0
        self._task_text = "テストメッセージ"

        # UI要素への参照
        self._image_widget = None
        self._image_label = None

        # 画像ファイルをロード
        self._load_image_files()

        self._build_ui()

    def _load_image_files(self):
        """指定フォルダからjpg画像をロード"""
        if not self._image_folder or not os.path.exists(self._image_folder):
            print(f"[VR UI System] Warning: Image folder not found: {self._image_folder}")
            self._image_files = []
            return

        try:
            folder_path = Path(self._image_folder)
            # jpg, jpeg, png画像を検索
            image_extensions = ['.jpg', '.jpeg', '.png']
            self._image_files = sorted([
                str(f) for f in folder_path.iterdir()
                if f.is_file() and f.suffix.lower() in image_extensions
            ])

            print(f"[VR UI System] Loaded {len(self._image_files)} images from {self._image_folder}")
            if self._image_files:
                for i, img in enumerate(self._image_files[:5]):  # 最初の5個を表示
                    print(f"  [{i}] {Path(img).name}")
                if len(self._image_files) > 5:
                    print(f"  ... and {len(self._image_files) - 5} more")

        except Exception as e:
            print(f"[VR UI System] Error loading images: {e}")
            self._image_files = []

    def _build_ui(self):
        """UIの構築"""
        with self:
            # ZStack + Rectangleパターンで背景色を表示
            with ui.ZStack():
                ui.Rectangle(style={"background_color": 0xFF808080})  # ABGR形式：グレー
                with ui.VStack(spacing=5):
                    # タスク表示エリア (1割相当 - 約15px高さ)
                    with ui.VStack(height=ui.Pixel(15)):
                        ui.Label(
                            f"学習スライド",
                            alignment=ui.Alignment.CENTER,
                            style={
                                "font_size": 12,
                                "color": 0xFFFFDD00,  # ABGR形式：黄色
                                "word_wrap": True
                            }
                        )

                    # 画像表示エリア (5割相当 - 約75px高さ) - 左右分割: 画像(7):テキスト(3)
                    with ui.HStack(height=ui.Pixel(75), spacing=5):
                        # 左側余白（左詰めだが完全ではない）
                        ui.Spacer(width=ui.Pixel(5))

                        # 左側：画像表示エリア (7割)
                        with ui.VStack(): #width=ui.Fraction(0.7)
                            # 画像ウィジェット
                            if self._image_files:
                                self._image_widget = ui.Image(
                                    self._image_files[self._current_index],
                                    fill_policy=ui.FillPolicy.PRESERVE_ASPECT_FIT,
                                    alignment=ui.Alignment.LEFT_CENTER
                                )
                            else:
                                self._image_widget = ui.Label(
                                    "画像が見つかりません",
                                    alignment=ui.Alignment.LEFT_CENTER,
                                    style={
                                        "font_size": 10,
                                        "color": 0xFFFFFFFF
                                    }
                                )

                        # 右側：テキスト表示エリア (3割)
                        """with ui.VStack(width=ui.Fraction(0.3)):
                            ui.Label(
                                "テスト",
                                alignment=ui.Alignment.CENTER,
                                style={
                                    "font_size": 10,
                                    "color": 0xFFFFFFFF,
                                    "word_wrap": True
                                }
                            )"""

                        # 画像インデックス表示
                        """if self._image_files:
                            self._image_label = ui.Label(
                                f"{self._current_index + 1} / {len(self._image_files)}",
                                alignment=ui.Alignment.CENTER,
                                style={
                                    "font_size": 2,
                                    "color": 0xFFFFFFFF
                                }
                            )
                        else:
                            self._image_label = ui.Label(
                                "",
                                alignment=ui.Alignment.CENTER
                            )"""

                    # ボタンエリア (2割相当 - 約30px高さ)
                    with ui.HStack(height=5, spacing=10):
                        ui.Spacer(width=ui.Pixel(10))

                        # 戻るボタン
                        ui.Button(
                            "戻る",
                            clicked_fn=self._on_previous_clicked,
                            style={
                                "font_size": 7,
                                "background_color": 0xFF404040,
                                "color": 0xFFFFFFFF
                            }
                        )

                        # 進むボタン
                        ui.Button(
                            "進む",
                            clicked_fn=self._on_next_clicked,
                            style={
                                "font_size": 7,
                                "background_color": 0xFF404040,
                                "color": 0xFFFFFFFF
                            }
                        )

                        ui.Spacer(width=ui.Pixel(10))


    def _on_previous_clicked(self):
        """戻るボタンクリック"""
        if not self._image_files:
            return

        self._current_index = (self._current_index - 1) % len(self._image_files)
        self._update_image()
        print(f"[VR UI System] Previous: {self._current_index + 1}/{len(self._image_files)}")

    def _on_next_clicked(self):
        """進むボタンクリック"""
        if not self._image_files:
            return

        self._current_index = (self._current_index + 1) % len(self._image_files)
        self._update_image()
        print(f"[VR UI System] Next: {self._current_index + 1}/{len(self._image_files)}")

    def _update_image(self):
        """画像を更新"""
        if not self._image_files or not self._image_widget:
            return

        try:
            current_image = self._image_files[self._current_index]
            # 画像ソースを更新
            self._image_widget.source_url = current_image

            # ラベル更新
            if self._image_label:
                self._image_label.text = f"{self._current_index + 1} / {len(self._image_files)}"

        except Exception as e:
            print(f"[VR UI System] Error updating image: {e}")

    def set_task_text(self, text: str):
        """タスクテキストを設定（将来の拡張用）"""
        self._task_text = text
        # UIの再構築が必要な場合はここで実装


class VRUISystem:
    """
    VR UI System - HMD前方に固定表示する3D UI

    機能:
    - Aボタンで表示切り替え
    - HMD前方150cmに固定配置（位置・回転固定、ビルボードなし）
    - 画像ビューアー
    """

    def __init__(self, ext_id: str, xr_core, image_folder: str = None):
        """
        初期化

        Args:
            ext_id: 拡張機能ID
            xr_core: XRCore インスタンス
            image_folder: 画像フォルダパス
        """
        self._ext_id = ext_id
        self._xr_core = xr_core
        self._image_folder = image_folder

        # UI表示状態
        self._ui_visible = False
        self._ui_container = None

        # HMD位置追従用
        self._hmd_device = None
        self._update_subscription = None

        print("[VR UI System] Initialized")

    def startup(self):
        """起動処理"""
        # HMDデバイス取得
        if self._xr_core:
            try:
                self._hmd_device = self._xr_core.get_input_device("displayDevice")
                if self._hmd_device:
                    print("[VR UI System] HMD device acquired")
                else:
                    print("[VR UI System] Warning: HMD device not found")
            except Exception as e:
                print(f"[VR UI System] Warning: Could not get HMD device: {e}")

        # 更新ループ開始（HMD位置更新用）
        update_stream = omni.kit.app.get_app().get_update_event_stream()
        self._update_subscription = update_stream.create_subscription_to_pop(
            self._on_update,
            name="VRUISystem Update"
        )

        print("[VR UI System] Started")

    def shutdown(self):
        """終了処理"""
        # 更新ループ停止
        if self._update_subscription:
            self._update_subscription.unsubscribe()
            self._update_subscription = None

        # UI削除
        self._hide_ui()

        print("[VR UI System] Shutdown")

    def toggle_ui(self):
        """UIの表示切り替え"""
        if self._ui_visible:
            self._hide_ui()
        else:
            self._show_ui()

    def _show_ui(self):
        """UIを表示（HMD前方150cm、Y軸回転のみでHMDを向く、水平維持）"""
        if self._ui_visible:
            return

        try:
            # HMD位置と向きを取得
            hmd_pose = self._get_hmd_pose()
            if hmd_pose is None:
                print("[VR UI System] Warning: Cannot get HMD pose")
                # デフォルト位置（左前方）
                ui_position = Gf.Vec3d(-50, 150, 50)
            else:
                hmd_position, hmd_rotation, left_vector = hmd_pose

                # HMDのTransform行列から軸ベクトルを取得
                device_pose = self._hmd_device.get_virtual_world_pose()

                # VR座標系: 第2行は後方向を指すので、符号を反転して前方向を取得
                backward_vector = Gf.Vec3d(device_pose[2][0], device_pose[2][1], device_pose[2][2])
                forward_vector = -backward_vector

                # 前方150cm先にUI配置
                distance = 100.0  # cm
                ui_position = hmd_position + forward_vector * distance

                # UIをHMDの方向に向ける（水平方向のみ、Z軸回転なし）
                # UIからHMDへの方向ベクトル
                direction_to_hmd = (hmd_position - ui_position).GetNormalized()

                # Y軸周りの回転のみを計算（左右の向き）
                # XZ平面での方向でHMDを向く
                y_rotation = math.atan2(direction_to_hmd[0], direction_to_hmd[2])

                # X軸とZ軸回転は0（UIを常に水平に保つ）
                euler_rotation = Gf.Vec3d(0.0, y_rotation, 0.0)

                print(f"[VR UI System] UI配置計算:")
                print(f"  HMD位置: {hmd_position}")
                print(f"  HMD前方向: {forward_vector}")
                print(f"  UI位置（前方150cm）: {ui_position}")
                print(f"  HMDへの方向: {direction_to_hmd}")
                print(f"  回転（Y軸のみ）: {math.degrees(y_rotation):.1f}°")

            # WidgetComponentを作成（縦横比2:3）
            widget_component = WidgetComponent(
                widget_type=ImageViewerWidget,
                width=150,  # cm（縦横比2:3の幅）
                height=120,  # cm（縦横比2:3の高さ）
                resolution_scale=4.0,
                update_policy=ui.scene.Widget.UpdatePolicy.ALWAYS,
                widget_kwargs={"image_folder": self._image_folder}
            )

            # SpatialSourceスタック構築（位置と回転、両方固定）
            space_stack = [
                SpatialSource.new_translation_source(ui_position),     # 位置（固定）
                SpatialSource.new_rotation_source(euler_rotation)      # 回転（固定）
            ]

            # UiContainerを作成
            self._ui_container = UiContainer(
                initial_component=widget_component,
                space_stack=space_stack,
                scene_view_type=XRSceneView
            )

            self._ui_visible = True
            print(f"[VR UI System] UI表示完了")
            print(f"  位置: HMD前方150cm（固定）")
            print(f"  向き: HMDを向く（Y軸回転のみ、水平維持、Z軸回転なし）")

        except Exception as e:
            print(f"[VR UI System] Error showing UI: {e}")
            import traceback
            traceback.print_exc()

    def _hide_ui(self):
        """UIを非表示"""
        if not self._ui_visible:
            return

        try:
            if self._ui_container and hasattr(self._ui_container, 'root'):
                self._ui_container.root.clear()

            self._ui_container = None
            self._ui_visible = False
            print("[VR UI System] UI hidden")

        except Exception as e:
            print(f"[VR UI System] Error hiding UI: {e}")

    def _get_hmd_pose(self):
        """HMD位置と向きを取得

        Returns:
            tuple: (position: Gf.Vec3d, rotation_quat: Gf.Quatd, left_vector: Gf.Vec3d) または None
        """
        if not self._hmd_device:
            return None

        try:
            # HMDのワールド座標変換行列を取得
            device_pose = self._hmd_device.get_virtual_world_pose()

            # Transform行列から位置を抽出
            position = device_pose.ExtractTranslation()
            position_vec = Gf.Vec3d(position[0], position[1], position[2])

            # Transform行列から回転を抽出
            rotation_quat = device_pose.ExtractRotation()

            # Transform行列から左方向ベクトルを抽出
            # 右手座標系: X軸=右、Y軸=上、Z軸=前
            # 左方向 = -X軸
            right_vector = Gf.Vec3d(device_pose[0][0], device_pose[1][0], device_pose[2][0])
            left_vector = -right_vector

            return (position_vec, rotation_quat, left_vector)

        except Exception as e:
            print(f"[VR UI System] Error getting HMD pose: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _on_update(self, event):
        """
        更新ループ

        Note: 現在はHMD位置の動的更新は実装していません。
        UIは表示時のHMD位置に固定されます。
        将来的にHMD追従が必要な場合はここで実装します。
        """
        pass


def get_vr_ui_system_instance():
    """グローバルインスタンスを取得"""
    return _vr_ui_system_instance if '_vr_ui_system_instance' in globals() else None


# グローバルインスタンス
_vr_ui_system_instance = None
