# coding: utf-8

import omni.ext
import omni.ui as ui
import omni.usd
import omni.kit.commands
import omni.kit.app
from pxr import Gf, UsdGeom, Sdf, Usd, UsdPhysics, UsdShade
import weakref
import time
import carb.audio
import os

# デバッグモードフラグ
DEBUG_MODE = True  # Trueで詳細ログを出力、Falseで最小限のログのみ

# ボタンパス定義
START_BUTTON_PATH = "/World/New_MillingMachine/Main/Switch2"
STOP_BUTTON_PATH = "/World/New_MillingMachine/Main/Switch1"

# Drill Colliderパス定義
DRILL_COLLIDER_PATH = "/World/New_MillingMachine/Main/Doril/Drill/Drill/_______001"

# Cable Meshパス定義（custom:placed属性チェック用）
CABLE_MESH_PATH = "/World/ケーブル_固定ver/Cable/Mesh"

def debug_log(message: str):
    """デバッグモード時のみログを出力"""
    if DEBUG_MODE:
        print(f"[PhysicalButton DEBUG] {message}")


class PhysicalButton:
    """物理ボタンクラス - PrismaticJointを使用した押下検知と視覚的フィードバック"""

    def __init__(self, button_path: str, button_type: str, pressed_callback=None, axis_direction: str = "X"):
        """
        Args:
            button_path: ボタンのUSDパス
            button_type: "start" or "stop"
            pressed_callback: ボタンが押されたときのコールバック関数
            axis_direction: PrismaticJointの軸方向 ("X", "Y", "Z")
        """
        self.button_path = button_path
        self.button_type = button_type
        self.pressed_callback = pressed_callback
        self.axis_direction = axis_direction.upper()

        # 軸方向に応じたインデックス (X=0, Y=1, Z=2)
        self.axis_index = {"X": 0, "Y": 1, "Z": 2}.get(self.axis_direction, 0)

        # ボタン状態
        self.is_pressed = False
        self.is_active = False  # トグル状態（押されたままの状態）
        self.initial_position = None
        self.button_prim = None
        self.joint_prim = None
        self.base_prim = None

        # 視覚的フィードバック用
        self.original_material = None
        self.pressed_material_path = None

        # デバッグ用
        self.last_position = None
        self.press_count = 0  # 押下検出回数
        self.last_displacement = 0.0

        debug_log(f"PhysicalButton作成: type={button_type}, path={button_path}, axis={self.axis_direction}")

    def setup_button(self, stage):
        """ボタンの物理セットアップと視覚的フィードバックの準備"""
        debug_log(f"setup_button開始: {self.button_type}")

        self.button_prim = stage.GetPrimAtPath(self.button_path)
        if not self.button_prim.IsValid():
            print(f"[PhysicalButton] エラー: ボタンが見つかりません: {self.button_path}")
            debug_log(f"Primが無効: {self.button_path}")
            return False

        debug_log(f"Prim有効確認完了: {self.button_path}")

        # 初期位置を記録
        xformable = UsdGeom.Xformable(self.button_prim)
        xform_ops = xformable.GetOrderedXformOps()
        debug_log(f"XformOp数: {len(xform_ops)}")

        for i, op in enumerate(xform_ops):
            debug_log(f"  XformOp[{i}]: type={op.GetOpType()}, name={op.GetOpName()}")
            if op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
                self.initial_position = Gf.Vec3d(op.Get())
                debug_log(f"  → TranslateOp検出: {self.initial_position}")
                break

        if self.initial_position is None:
            self.initial_position = Gf.Vec3d(0, 0, 0)
            debug_log("初期位置が見つからないため(0,0,0)に設定")

        print(f"[PhysicalButton] {self.button_type} 初期位置: {self.initial_position}")
        self.last_position = self.initial_position

        # 固定ベースを作成（ボタンと同じ親階層）
        parent_path = str(Sdf.Path(self.button_path).GetParentPath())
        base_path = f"{parent_path}/{self.button_type}_FixedBase"

        # 既存のベースを削除（再初期化の場合）
        if stage.GetPrimAtPath(base_path):
            debug_log(f"既存のベースを削除: {base_path}")
            stage.RemovePrim(base_path)

        # 見えない小さなCylinderを作成
        base_prim = stage.DefinePrim(base_path, "Cylinder")
        self.base_prim = base_prim

        base_geom = UsdGeom.Cylinder(base_prim)
        base_geom.CreateRadiusAttr(0.01)
        base_geom.CreateHeightAttr(0.01)

        # ボタンと同じ位置に配置
        base_xform = UsdGeom.Xformable(base_prim)
        translate_op = base_xform.AddTranslateOp()
        translate_op.Set(self.initial_position)

        # 物理設定: Kinematic（固定）
        UsdPhysics.RigidBodyAPI.Apply(base_prim)
        rb_api = UsdPhysics.RigidBodyAPI(base_prim)
        rb_api.CreateKinematicEnabledAttr().Set(True)

        # 見えないようにする
        imageable = UsdGeom.Imageable(base_prim)
        imageable.MakeInvisible()

        debug_log(f"ベース作成完了: {base_path}")
        print(f"[PhysicalButton] ベース作成: {base_path}")

        # PrismaticJointを作成
        joint_path = f"{parent_path}/{self.button_type}_PrismaticJoint"

        # 既存のJointを削除（再初期化の場合）
        if stage.GetPrimAtPath(joint_path):
            debug_log(f"既存のJointを削除: {joint_path}")
            stage.RemovePrim(joint_path)

        # ボタンにRigidBodyAPIが適用されているか確認
        if not self.button_prim.HasAPI(UsdPhysics.RigidBodyAPI):
            debug_log("ボタンにRigidBodyAPIを適用")
            UsdPhysics.RigidBodyAPI.Apply(self.button_prim)

        joint = UsdPhysics.PrismaticJoint.Define(stage, joint_path)
        self.joint_prim = joint.GetPrim()

        # ジョイント設定（軸方向を動的に設定）
        joint.CreateAxisAttr(self.axis_direction)  # 選択された軸方向に動く
        joint.CreateBody0Rel().SetTargets([Sdf.Path(base_path)])  # 固定側
        joint.CreateBody1Rel().SetTargets([Sdf.Path(self.button_path)])  # 動く側

        # 可動範囲: 0（初期位置）〜 1.0（押し込まれた位置）
        joint.CreateLowerLimitAttr(0.0)
        joint.CreateUpperLimitAttr(1.0)

        # ドライブ設定（元の位置に戻ろうとする力）
        drive = UsdPhysics.DriveAPI.Apply(self.joint_prim, "linear")
        drive.CreateTypeAttr("force")
        drive.CreateTargetPositionAttr(0.0)  # 初期位置
        drive.CreateStiffnessAttr(5000.0)  # バネの強さ
        drive.CreateDampingAttr(500.0)  # ダンピング
        drive.CreateMaxForceAttr(10000.0)  # 最大力

        debug_log(f"Joint作成完了: {joint_path}")
        debug_log(f"  軸方向: {self.axis_direction}")
        debug_log(f"  Body0: {base_path}")
        debug_log(f"  Body1: {self.button_path}")
        print(f"[PhysicalButton] PrismaticJoint作成: {joint_path} (軸: {self.axis_direction})")

        # 視覚的フィードバック用マテリアルの準備
        self._setup_visual_feedback(stage)

        # ボタン専用のマテリアルコピーを作成
        self._create_button_material_copy(stage)

        return True

    def _setup_visual_feedback(self, stage):
        """視覚的フィードバック用のマテリアル設定"""
        # 押下時の発光マテリアルを作成
        material_path = f"/World/Materials/{self.button_type}_PressedMaterial"
        self.pressed_material_path = material_path

        if not stage.GetPrimAtPath(material_path):
            # マテリアル作成
            material = UsdShade.Material.Define(stage, material_path)

            # Shader作成（発光）
            shader_path = f"{material_path}/Shader"
            shader = UsdShade.Shader.Define(stage, shader_path)
            shader.CreateIdAttr("UsdPreviewSurface")

            # 発光色設定（STARTは緑、STOPは赤）- 強度を大幅に上げる
            if self.button_type == "start":
                shader.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).Set((0.0, 50.0, 0.0))  # 強度10倍
            else:
                shader.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).Set((50.0, 0.0, 0.0))  # 強度10倍

            shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set((0.1, 0.1, 0.1))
            shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)
            shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.2)

            # シェーダーをマテリアルに接続
            material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")

            print(f"[PhysicalButton] マテリアル作成: {material_path}")

    def _create_default_material(self, stage, mesh_prim, material_path):
        """デフォルトマテリアルを作成してボタンにバインド（button_typeに応じた色）"""
        try:
            # 新しいマテリアルを作成
            new_material = UsdShade.Material.Define(stage, material_path)

            # UsdPreviewSurfaceシェーダーを作成
            shader_path = f"{material_path}/Shader"
            shader = UsdShade.Shader.Define(stage, shader_path)
            shader.CreateIdAttr("UsdPreviewSurface")

            # button_typeに応じて色を設定
            if self.button_type == "start":
                # STARTボタン: 暗めの緑
                diffuse_color = Gf.Vec3f(0.0, 0.2, 0.0)
                emissive_color = Gf.Vec3f(0.0, 0.0, 0.0)
            else:  # stop
                # STOPボタン: 暗めの赤
                diffuse_color = Gf.Vec3f(0.2, 0.0, 0.0)
                emissive_color = Gf.Vec3f(0.0, 0.0, 0.0)

            # 基本的なプロパティを設定
            shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(diffuse_color)
            shader.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).Set(emissive_color)
            shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.5)
            shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.2)

            # Surface outputを接続
            new_material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")

            # メッシュにバインド
            binding_api = UsdShade.MaterialBindingAPI.Apply(mesh_prim)
            binding_api.Bind(new_material)

        except Exception as e:
            print(f"[PhysicalButton] デフォルトマテリアル作成失敗: {e}")
            import traceback
            traceback.print_exc()

    def _create_button_material_copy(self, stage):
        """ボタン専用のマテリアルコピーを作成して割り当て"""
        debug_log(f"_create_button_material_copy開始: {self.button_type}")

        # ボタン専用のマテリアルパスを先に定義
        button_material_path = Sdf.Path(f"/World/Materials/{self.button_type}_ButtonMaterial")
        self.button_material_path = str(button_material_path)

        # メッシュを取得
        mesh_prim = self._find_mesh_in_prim(self.button_prim)
        if not mesh_prim:
            debug_log("メッシュが見つかりません")
            return

        debug_log(f"メッシュ発見: {mesh_prim.GetPath()}")

        # 現在のマテリアルを先に取得（削除前に）
        binding_api = UsdShade.MaterialBindingAPI(mesh_prim)
        original_material, _ = binding_api.ComputeBoundMaterial()

        # 元のマテリアル情報を保存
        original_mat_prim = None
        if original_material:
            original_mat_prim = original_material.GetPrim()
            if not original_mat_prim.IsValid():
                debug_log("元のマテリアルが無効")
                original_mat_prim = None
            else:
                debug_log(f"元のマテリアル: {original_mat_prim.GetPath()}")

        # すでに存在する場合は削除してから作成
        if stage.GetPrimAtPath(button_material_path):
            debug_log(f"既存のボタンマテリアルを削除: {button_material_path}")
            stage.RemovePrim(button_material_path)

        # マテリアルがない場合はデフォルトマテリアルを作成
        if not original_mat_prim:
            debug_log("デフォルトマテリアルを作成")
            self._create_default_material(stage, mesh_prim, button_material_path)
            return

        try:
            # 新しいマテリアルを作成
            new_material = UsdShade.Material.Define(stage, button_material_path)

            # 元のマテリアルからシェーダーをコピー
            for child_prim in original_mat_prim.GetChildren():
                if child_prim.IsA(UsdShade.Shader):
                    original_shader = UsdShade.Shader(child_prim)

                    # 新しいシェーダーを作成
                    shader_name = child_prim.GetName()
                    new_shader_path = f"{button_material_path}/{shader_name}"
                    new_shader = UsdShade.Shader.Define(stage, new_shader_path)

                    # Shader IDをコピー
                    shader_id = original_shader.GetIdAttr().Get()
                    if shader_id:
                        new_shader.CreateIdAttr(shader_id)

                    # 全てのInputをコピー
                    for input in original_shader.GetInputs():
                        input_name = input.GetBaseName()
                        input_value = input.Get()
                        input_type = input.GetTypeName()

                        new_input = new_shader.CreateInput(input_name, input_type)
                        if input_value is not None:
                            new_input.Set(input_value)

                    # Surface outputを接続
                    new_material.CreateSurfaceOutput().ConnectToSource(new_shader.ConnectableAPI(), "surface")

            # コピーしたマテリアルをボタンのメッシュにバインド
            binding_api = UsdShade.MaterialBindingAPI.Apply(mesh_prim)
            binding_api.Bind(new_material)

        except Exception as e:
            print(f"[PhysicalButton][Error] マテリアルコピー失敗: {e}")
            import traceback
            traceback.print_exc()

    def check_button_state(self, stage):
        """ボタンの押下状態をチェック（物理的押下のみ検出、視覚効果はアクティブ状態で管理）"""
        if not self.button_prim:
            debug_log(f"{self.button_type}: button_primが無効")
            return False

        # 現在の位置を取得
        xformable = UsdGeom.Xformable(self.button_prim)
        current_position = None

        for op in xformable.GetOrderedXformOps():
            if op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
                current_position = op.Get()
                break

        if current_position is None:
            debug_log(f"{self.button_type}: current_positionが取得できません")
            return False

        # 選択された軸方向の変位をチェック（正方向に0.07以上移動で押下）
        axis_displacement = current_position[self.axis_index] - self.initial_position[self.axis_index]

        # 位置が変化した場合のみログ出力
        if abs(axis_displacement - self.last_displacement) > 0.001:
            axis_name = self.axis_direction
            debug_log(
                f"{self.button_type}: "
                f"axis={axis_name}, "
                f"init={self.initial_position[self.axis_index]:.4f}, "
                f"current={current_position[self.axis_index]:.4f}, "
                f"displacement={axis_displacement:.4f}, "
                f"threshold=0.07, "
                f"pressed={axis_displacement >= 0.07}"
            )
            self.last_displacement = axis_displacement

        was_pressed = self.is_pressed
        self.is_pressed = axis_displacement >= 0.07

        # 物理的にボタンが押された瞬間のみコールバック実行
        if not was_pressed and self.is_pressed:
            # 押された
            self.press_count += 1
            print(f"[PhysicalButton] {self.button_type}ボタンが物理的に押されました（押下回数: {self.press_count}）")
            debug_log(
                f"押下検出詳細: "
                f"axis={self.axis_direction}, "
                f"was_pressed={was_pressed}, "
                f"is_pressed={self.is_pressed}, "
                f"displacement={axis_displacement:.4f}, "
                f"is_active={self.is_active}"
            )

            if self.pressed_callback:
                debug_log(f"コールバック実行: {self.button_type}")
                self.pressed_callback(self.button_type)
            else:
                debug_log("コールバックが設定されていません")
            return True

        return False

    def _apply_pressed_visual(self, stage):
        """押下時の視覚効果を適用（既存マテリアルのemissiveを変更）"""
        # ボタンのメッシュを探す
        mesh_prim = self._find_mesh_in_prim(self.button_prim)
        if not mesh_prim:
            return

        # 既存のマテリアルを取得
        binding_api = UsdShade.MaterialBindingAPI(mesh_prim)
        bound_material, _ = binding_api.ComputeBoundMaterial()

        if not bound_material:
            return

        material_prim = bound_material.GetPrim()

        # マテリアル内のシェーダーを探す
        shader = None
        for prim in material_prim.GetChildren():
            if prim.IsA(UsdShade.Shader):
                shader = UsdShade.Shader(prim)
                break

        if not shader:
            return

        # 元の値を保存（最初の1回のみ）
        if not hasattr(self, 'original_emissive'):
            emissive_input = shader.GetInput("emissiveColor")
            self.original_emissive = emissive_input.Get() if emissive_input and emissive_input.Get() else Gf.Vec3f(0, 0, 0)

        if not hasattr(self, 'original_diffuse'):
            diffuse_input = shader.GetInput("diffuseColor")
            self.original_diffuse = diffuse_input.Get() if diffuse_input and diffuse_input.Get() else Gf.Vec3f(0.5, 0.5, 0.5)

        if not hasattr(self, 'original_roughness'):
            roughness_input = shader.GetInput("roughness")
            self.original_roughness = roughness_input.Get() if roughness_input and roughness_input.Get() else 0.5

        if not hasattr(self, 'original_metallic'):
            metallic_input = shader.GetInput("metallic")
            self.original_metallic = metallic_input.Get() if metallic_input and metallic_input.Get() else 0.0

        # emissiveColorを変更（押下時はより明るく発光）
        emissive_input = shader.GetInput("emissiveColor")
        if not emissive_input:
            emissive_input = shader.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f)

        if self.button_type == "start":
            emissive_color = Gf.Vec3f(0.0, 15.0, 0.0)  # 緑の強い発光（強度15）
        else:
            emissive_color = Gf.Vec3f(15.0, 0.0, 0.0)  # 赤の強い発光（強度15）

        emissive_input.Set(emissive_color)

        # diffuseColorを非常に明るくして視認性を最大化
        diffuse_input = shader.GetInput("diffuseColor")
        if not diffuse_input:
            diffuse_input = shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f)

        if self.button_type == "start":
            diffuse_input.Set(Gf.Vec3f(0.0, 1.0, 0.0))  # 最大輝度の緑
        else:
            diffuse_input.Set(Gf.Vec3f(1.0, 0.0, 0.0))  # 最大輝度の赤

        # roughnessを最小にして鏡面反射を最大化
        roughness_input = shader.GetInput("roughness")
        if not roughness_input:
            roughness_input = shader.CreateInput("roughness", Sdf.ValueTypeNames.Float)
        roughness_input.Set(0.05)  # 非常に滑らか（鏡面的）

        # metallicを上げて金属的な輝きを強調
        metallic_input = shader.GetInput("metallic")
        if not metallic_input:
            metallic_input = shader.CreateInput("metallic", Sdf.ValueTypeNames.Float)
        metallic_input.Set(0.5)  # より金属的

        # opacityThresholdを設定して透過を防ぐ
        opacity_input = shader.GetInput("opacity")
        if not opacity_input:
            opacity_input = shader.CreateInput("opacity", Sdf.ValueTypeNames.Float)
        opacity_input.Set(1.0)

    def _remove_pressed_visual(self, stage):
        """押下時の視覚効果を解除（全プロパティを元に戻す）"""
        mesh_prim = self._find_mesh_in_prim(self.button_prim)
        if not mesh_prim:
            return

        # 既存のマテリアルを取得
        binding_api = UsdShade.MaterialBindingAPI(mesh_prim)
        bound_material, _ = binding_api.ComputeBoundMaterial()

        if not bound_material:
            return

        material_prim = bound_material.GetPrim()

        # マテリアル内のシェーダーを探す
        shader = None
        for prim in material_prim.GetChildren():
            if prim.IsA(UsdShade.Shader):
                shader = UsdShade.Shader(prim)
                break

        if not shader:
            return

        # emissiveColorを元に戻す
        emissive_input = shader.GetInput("emissiveColor")
        if emissive_input and hasattr(self, 'original_emissive'):
            emissive_input.Set(self.original_emissive)

        # diffuseColorを元に戻す
        diffuse_input = shader.GetInput("diffuseColor")
        if diffuse_input and hasattr(self, 'original_diffuse'):
            diffuse_input.Set(self.original_diffuse)

        # roughnessを元に戻す
        roughness_input = shader.GetInput("roughness")
        if roughness_input and hasattr(self, 'original_roughness'):
            roughness_input.Set(self.original_roughness)

        # metallicを元に戻す
        metallic_input = shader.GetInput("metallic")
        if metallic_input and hasattr(self, 'original_metallic'):
            metallic_input.Set(self.original_metallic)

    def _find_mesh_in_prim(self, prim):
        """Prim階層内からメッシュを検索"""
        if prim.IsA(UsdGeom.Mesh):
            return prim

        for child in prim.GetChildren():
            mesh = self._find_mesh_in_prim(child)
            if mesh:
                return mesh

        return None

    def set_active(self, stage, active: bool):
        """ボタンのアクティブ状態を設定（トグル用）"""
        self.is_active = active
        if active:
            self._apply_pressed_visual(stage)
            print(f"[PhysicalButton] {self.button_type}ボタンをアクティブ化（発光維持）")
        else:
            self._remove_pressed_visual(stage)
            print(f"[PhysicalButton] {self.button_type}ボタンを非アクティブ化（発光解除）")

    def cleanup(self, stage):
        """クリーンアップ"""
        debug_log(f"cleanup開始: {self.button_type}")

        # ジョイントを削除
        if self.joint_prim:
            joint_path = self.joint_prim.GetPath()
            if self.joint_prim.IsValid() and stage.GetPrimAtPath(joint_path):
                debug_log(f"Jointを削除: {joint_path}")
                stage.RemovePrim(joint_path)
                self.joint_prim = None
            else:
                debug_log(f"Joint既に無効または存在しません: {joint_path}")

        # ベースを削除
        if self.base_prim:
            base_path = self.base_prim.GetPath()
            if self.base_prim.IsValid() and stage.GetPrimAtPath(base_path):
                debug_log(f"ベースを削除: {base_path}")
                stage.RemovePrim(base_path)
                self.base_prim = None
            else:
                debug_log(f"ベース既に無効または存在しません: {base_path}")

        debug_log(f"cleanup完了: {self.button_type}")


class PhysicalButtonExtension(omni.ext.IExt):
    """物理ボタンシステム拡張機能"""

    def on_startup(self, ext_id):
        print("[PhysicalButton] 物理ボタンシステムを起動")
        debug_log("on_startup開始")

        self._window = None
        self._buttons = {}
        self._update_subscription = None
        self._system_initialized = False
        self._active_button = None  # 現在アクティブなボタン（"start" or "stop"）
        self._last_physical_press_time = {}  # 物理ボタン押下の最終時刻

        # オーディオ初期化
        self._playback_interface = None
        self._data_interface = None
        self._audio_context = None
        self._machine_sound = None
        self._machine_voice = None
        self._audio_available = False
        self._init_audio()

        # UIの作成
        debug_log("UI作成開始")
        self._create_ui()
        debug_log("on_startup完了")

    def _init_audio(self):
        """オーディオシステムの初期化"""
        try:
            # オーディオインターフェースを取得（正しいAPI）
            self._playback_interface = carb.audio.acquire_playback_interface()
            self._data_interface = carb.audio.acquire_data_interface()

            if not self._playback_interface or not self._data_interface:
                print("[PhysicalButton] オーディオインターフェース取得失敗 - 音声機能は無効")
                return

            # オーディオコンテキストを作成
            self._audio_context = self._playback_interface.create_context()
            if not self._audio_context:
                print("[PhysicalButton] オーディオコンテキスト作成失敗 - 音声機能は無効")
                return

            # 音源ファイルのパスを取得
            import omni.kit.app
            extension_path = omni.kit.app.get_app().get_extension_manager().get_extension_path_by_module(__name__)
            sound_file_path = os.path.join(extension_path, "data", "sounds", "電気ドリル・ループ01.mp3")

            # ファイルの存在チェック
            if not os.path.exists(sound_file_path):
                print(f"[PhysicalButton] 音源ファイルが見つかりません: {sound_file_path}")
                print("[PhysicalButton] 音声機能は無効化されます（エラーではありません）")
                return

            # サウンドデータを読み込み
            self._machine_sound = self._data_interface.create_sound_from_file(sound_file_path)

            if not self._machine_sound:
                print(f"[PhysicalButton] サウンド読み込み失敗: {sound_file_path}")
                print("[PhysicalButton] 音声機能は無効化されます（エラーではありません）")
                return

            # 初期化成功（Voiceは再生時に作成）
            self._audio_available = True
            print(f"[PhysicalButton] オーディオ初期化成功: {sound_file_path}")

        except Exception as e:
            print(f"[PhysicalButton] オーディオ初期化エラー: {e}")
            print("[PhysicalButton] 音声機能は無効化されます（エラーではありません）")
            import traceback
            traceback.print_exc()
            self._audio_available = False

    def on_shutdown(self):
        print("[PhysicalButton] 物理ボタンシステムを終了")
        debug_log("on_shutdown開始")

        try:
            # オーディオクリーンアップ
            self._cleanup_audio()

            # クリーンアップ
            if self._update_subscription:
                debug_log("更新ループを停止")
                self._update_subscription.unsubscribe()
                self._update_subscription = None

            if self._system_initialized:
                debug_log("システムをクリーンアップ")
                stage = omni.usd.get_context().get_stage()
                if stage:
                    for button_type, button in self._buttons.items():
                        debug_log(f"ボタンをクリーンアップ: {button_type}")
                        try:
                            button.cleanup(stage)
                        except Exception as e:
                            print(f"[PhysicalButton] ボタンクリーンアップエラー ({button_type}): {e}")
                            debug_log(f"ボタンクリーンアップ例外: {e}")
                else:
                    debug_log("ステージが取得できません")

            self._buttons.clear()

            if self._window:
                debug_log("UIウィンドウを破棄")
                self._window.destroy()
                self._window = None

            debug_log("on_shutdown完了")

        except Exception as e:
            print(f"[PhysicalButton] シャットダウンエラー: {e}")
            debug_log(f"シャットダウン例外: {e}")
            import traceback
            traceback.print_exc()

    def _cleanup_audio(self):
        """オーディオリソースのクリーンアップ"""
        try:
            # 再生中のサウンドを停止
            if self._machine_voice and self._machine_voice.is_playing():
                self._machine_voice.stop()
            self._machine_voice = None

            # サウンドリソースを解放
            if self._machine_sound and self._data_interface:
                self._data_interface.destroy_sound(self._machine_sound)
                self._machine_sound = None

            # オーディオコンテキストを破棄
            if self._audio_context and self._playback_interface:
                self._playback_interface.destroy_context(self._audio_context)
                self._audio_context = None

            if self._audio_available:
                print("[PhysicalButton] オーディオクリーンアップ完了")

        except Exception as e:
            print(f"[PhysicalButton] オーディオクリーンアップエラー: {e}")

    def _start_audio(self):
        """機械音の再生を開始（ループ）"""
        if not self._audio_available:
            return

        try:
            # 既に再生中の場合は何もしない
            if self._machine_voice and self._machine_voice.is_playing():
                debug_log("既にオーディオ再生中")
                return

            # EventPointを使用して無限ループを設定
            loop_point = carb.audio.EventPoint()
            loop_point.loop_count = carb.audio.EVENT_POINT_LOOP_INFINITE
            loop_point.frame = 0  # 開始フレーム
            loop_point.length = 0  # 0 = 残り全体をループ

            # サウンドを再生（Voiceハンドルを取得）
            if self._machine_sound and self._audio_context:
                # シンプルな呼び出し：サウンドとループポイントのみ指定
                self._machine_voice = self._audio_context.play_sound(
                    self._machine_sound,
                    0,  # flags (デフォルト)
                    0,  # valid_params (パラメータ指定なし)
                    None,  # params
                    loop_point  # EventPointを渡す
                )

                if self._machine_voice:
                    print("[PhysicalButton] 機械音の再生を開始（ループ）")
                    debug_log("オーディオ再生開始")
                else:
                    print("[PhysicalButton] Voice作成失敗")

        except Exception as e:
            print(f"[PhysicalButton] オーディオ再生エラー: {e}")
            import traceback
            traceback.print_exc()

    def _stop_audio(self):
        """機械音の再生を停止"""
        if not self._audio_available:
            return

        try:
            # 再生中のサウンドを停止
            if self._machine_voice and self._machine_voice.is_playing():
                self._machine_voice.stop()
                print("[PhysicalButton] 機械音の再生を停止")
                debug_log("オーディオ再生停止")
                self._machine_voice = None

        except Exception as e:
            print(f"[PhysicalButton] オーディオ停止エラー: {e}")

    def _create_ui(self):
        """UIウィンドウの作成"""
        self._window = ui.Window("Physical Button System", width=400, height=450)

        with self._window.frame:
            with ui.VStack(spacing=10, style={"margin": 5}):
                ui.Label("物理ボタンシステム", style={"font_size": 18})
                ui.Separator()

                # デバッグモード切替
                with ui.HStack(height=0):
                    ui.Label("デバッグモード:")
                    self._debug_mode_label = ui.Label("ON" if DEBUG_MODE else "OFF",
                                                       style={"color": 0xFF00FF00 if DEBUG_MODE else 0xFF888888})
                    ui.Button("切替", clicked_fn=self._toggle_debug_mode, width=50)

                ui.Separator()

                # 軸方向設定
                ui.Label("PrismaticJoint 軸方向設定:", style={"font_size": 14})
                with ui.HStack(height=0):
                    ui.Label("※ボタンが動く方向を選択", style={"color": 0xFFAAAAAA, "font_size": 12})

                # STARTボタンの軸設定
                with ui.HStack(height=0):
                    ui.Label("START軸:", width=80)
                    self._start_axis_combo = ui.ComboBox(0, "X", "Y", "Z", width=60)
                    ui.Spacer(width=10)
                    ui.Label("現在:", width=50)
                    self._start_current_axis_label = ui.Label("未設定", style={"color": 0xFF888888})

                # STOPボタンの軸設定
                with ui.HStack(height=0):
                    ui.Label("STOP軸:", width=80)
                    self._stop_axis_combo = ui.ComboBox(0, "X", "Y", "Z", width=60)
                    ui.Spacer(width=10)
                    ui.Label("現在:", width=50)
                    self._stop_current_axis_label = ui.Label("未設定", style={"color": 0xFF888888})

                ui.Separator()

                # セットアップボタン
                with ui.HStack(height=0):
                    ui.Button("ボタンシステムを初期化", clicked_fn=self._initialize_buttons)
                    ui.Button("クリーンアップ", clicked_fn=self._cleanup_system)

                ui.Separator()

                # ステータス表示
                ui.Label("ステータス:", style={"font_size": 14})
                self._status_label = ui.Label("未初期化", style={"color": 0xFF888888})

                with ui.HStack(height=0):
                    ui.Label("START:")
                    self._start_status = ui.Label("未検知", style={"color": 0xFF888888})

                with ui.HStack(height=0):
                    ui.Label("STOP:")
                    self._stop_status = ui.Label("未検知", style={"color": 0xFF888888})

                ui.Separator()

                # 手動テスト
                ui.Label("手動テスト:", style={"font_size": 14})
                with ui.HStack(height=0):
                    ui.Button("START押下をシミュレート", clicked_fn=lambda: self._on_button_pressed("start"))
                    ui.Button("STOP押下をシミュレート", clicked_fn=lambda: self._on_button_pressed("stop"))

    def _toggle_debug_mode(self):
        """デバッグモードの切替"""
        global DEBUG_MODE
        DEBUG_MODE = not DEBUG_MODE
        self._debug_mode_label.text = "ON" if DEBUG_MODE else "OFF"
        self._debug_mode_label.style = {"color": 0xFF00FF00 if DEBUG_MODE else 0xFF888888}
        print(f"[PhysicalButton] デバッグモード: {'ON' if DEBUG_MODE else 'OFF'}")

    def _initialize_buttons(self):
        """ボタンシステムの初期化"""
        print("[PhysicalButton] ボタンシステムを初期化中...")
        debug_log("_initialize_buttons開始")

        stage = omni.usd.get_context().get_stage()
        if not stage:
            print("[PhysicalButton] エラー: ステージが開かれていません")
            debug_log("ステージ取得失敗")
            self._status_label.text = "エラー: ステージ未ロード"
            return

        debug_log(f"ステージ取得成功: {stage}")

        # ボタンをクリア
        if self._system_initialized:
            debug_log("既存ボタンをクリーンアップ")
            for button in self._buttons.values():
                button.cleanup(stage)
        self._buttons.clear()

        # UIから選択された軸を取得
        axis_options = ["X", "Y", "Z"]
        start_axis = axis_options[self._start_axis_combo.model.get_item_value_model().as_int]
        stop_axis = axis_options[self._stop_axis_combo.model.get_item_value_model().as_int]

        debug_log(f"選択された軸: START={start_axis}, STOP={stop_axis}")

        # STARTボタンのセットアップ
        debug_log(f"STARTボタンセットアップ開始: {START_BUTTON_PATH}, 軸={start_axis}")
        start_button = PhysicalButton(START_BUTTON_PATH, "start", self._on_button_pressed, start_axis)
        if start_button.setup_button(stage):
            self._buttons["start"] = start_button
            self._start_current_axis_label.text = start_axis
            self._start_current_axis_label.style = {"color": 0xFF00FF00}  # 緑色で表示
            print(f"[PhysicalButton] STARTボタン初期化完了 (軸: {start_axis})")
            debug_log("STARTボタン初期化成功")
        else:
            print("[PhysicalButton] エラー: STARTボタン初期化失敗")
            self._start_current_axis_label.text = "初期化失敗"
            self._start_current_axis_label.style = {"color": 0xFFFF0000}  # 赤色で表示
            debug_log("STARTボタン初期化失敗")

        # STOPボタンのセットアップ
        debug_log(f"STOPボタンセットアップ開始: {STOP_BUTTON_PATH}, 軸={stop_axis}")
        stop_button = PhysicalButton(STOP_BUTTON_PATH, "stop", self._on_button_pressed, stop_axis)
        if stop_button.setup_button(stage):
            self._buttons["stop"] = stop_button
            self._stop_current_axis_label.text = stop_axis
            self._stop_current_axis_label.style = {"color": 0xFF00FF00}  # 緑色で表示
            print(f"[PhysicalButton] STOPボタン初期化完了 (軸: {stop_axis})")
            debug_log("STOPボタン初期化成功")
        else:
            print("[PhysicalButton] エラー: STOPボタン初期化失敗")
            self._stop_current_axis_label.text = "初期化失敗"
            self._stop_current_axis_label.style = {"color": 0xFFFF0000}  # 赤色で表示
            debug_log("STOPボタン初期化失敗")

        # 更新ループを開始
        if not self._update_subscription:
            debug_log("更新ループ登録")
            update_stream = omni.kit.app.get_app().get_update_event_stream()
            self._update_subscription = update_stream.create_subscription_to_pop(
                self._on_update, name="physical_button_update"
            )
            debug_log("更新ループ登録完了")

        self._system_initialized = True

        # デフォルトでSTOPボタンをアクティブに設定
        debug_log("STOPボタンをデフォルトアクティブ化")
        self._activate_button("stop", stage)

        self._status_label.text = f"初期化完了（START:{start_axis}, STOP:{stop_axis}）"
        self._status_label.style = {"color": 0xFF00FF00}
        debug_log("_initialize_buttons完了")

    def _cleanup_system(self):
        """システムのクリーンアップ"""
        debug_log("_cleanup_system開始")

        if not self._system_initialized:
            debug_log("システムが初期化されていません")
            return

        stage = omni.usd.get_context().get_stage()
        if stage:
            debug_log(f"ボタン数: {len(self._buttons)}")
            for button_type, button in self._buttons.items():
                debug_log(f"ボタンをクリーンアップ: {button_type}")
                button.cleanup(stage)
        else:
            debug_log("ステージが取得できません")

        self._buttons.clear()
        self._system_initialized = False
        self._active_button = None

        # 現在の軸表示をリセット
        self._start_current_axis_label.text = "未設定"
        self._start_current_axis_label.style = {"color": 0xFF888888}
        self._stop_current_axis_label.text = "未設定"
        self._stop_current_axis_label.style = {"color": 0xFF888888}

        self._status_label.text = "クリーンアップ完了"
        self._status_label.style = {"color": 0xFF888888}
        debug_log("_cleanup_system完了")

    def _on_update(self, e):
        """フレーム毎の更新"""
        if not self._system_initialized:
            return

        stage = omni.usd.get_context().get_stage()
        if not stage:
            return

        # 各ボタンの物理的押下をチェック
        for button_type, button in self._buttons.items():
            button.check_button_state(stage)

        # UI更新（アクティブ状態に基づく）
        if "start" in self._buttons:
            button = self._buttons["start"]
            if button.is_active:
                self._start_status.text = "有効（発光中）"
                self._start_status.style = {"color": 0xFF00FF00}
            else:
                self._start_status.text = "無効"
                self._start_status.style = {"color": 0xFF888888}

        if "stop" in self._buttons:
            button = self._buttons["stop"]
            if button.is_active:
                self._stop_status.text = "有効（発光中）"
                self._stop_status.style = {"color": 0xFFFF0000}
            else:
                self._stop_status.text = "無効"
                self._stop_status.style = {"color": 0xFF888888}

    def _on_button_pressed(self, button_type: str):
        """ボタンが押されたときの処理（トグル動作）"""
        print(f"[PhysicalButton] {button_type}ボタンのコールバック実行（トグル）")
        debug_log(f"_on_button_pressed開始: button_type={button_type}, current_active={self._active_button}")

        stage = omni.usd.get_context().get_stage()
        if not stage:
            debug_log("ステージが取得できません")
            return

        # 既にこのボタンがアクティブな場合は何もしない
        if self._active_button == button_type:
            print(f"[PhysicalButton] {button_type}は既にアクティブです")
            debug_log("同じボタンが既にアクティブのため処理をスキップ")
            return

        # StartButtonの場合は、発光前にcustom:placedをチェック
        if button_type == "start":
            debug_log(f"STARTボタン: custom:placed属性チェック開始 ({CABLE_MESH_PATH})")
            cable_mesh_prim = stage.GetPrimAtPath(CABLE_MESH_PATH)

            if cable_mesh_prim.IsValid():
                debug_log("Cable Mesh prim有効")
                placed_attr = cable_mesh_prim.GetAttribute("custom:placed")

                if placed_attr:
                    placed_value = placed_attr.Get()
                    debug_log(f"custom:placed属性値: {placed_value} (type: {type(placed_value)})")

                    if placed_value == False:
                        print(f"[PhysicalButton] custom:placed=False のため処理をスキップ（STOPボタン有効のまま）")
                        debug_log("StartButton処理中止: custom:placed=False")
                        return  # STOPボタンのまま、StartButtonは発光しない
                    else:
                        print(f"[PhysicalButton] custom:placed={placed_value} - StartButton処理を続行")
                        debug_log("StartButton処理続行")
                else:
                    print(f"[PhysicalButton] custom:placed属性が存在しません - StartButton処理を続行")
                    debug_log("custom:placed属性なし - 処理続行")
            else:
                print(f"[PhysicalButton] Cable Meshが見つかりません: {CABLE_MESH_PATH} - StartButton処理を続行")
                debug_log(f"Cable Mesh prim無効: {CABLE_MESH_PATH}")

        # 押されたボタンをアクティブ化
        debug_log(f"_activate_button呼び出し: {button_type}")
        self._activate_button(button_type, stage)

    def _activate_button(self, button_type: str, stage):
        """指定されたボタンをアクティブ化し、他のボタンを非アクティブ化"""
        print(f"[PhysicalButton] {button_type}ボタンをアクティブ化")
        debug_log(f"_activate_button開始: button_type={button_type}")

        # 全てのボタンを非アクティブ化
        for btn_type, button in self._buttons.items():
            if btn_type != button_type:
                debug_log(f"ボタン非アクティブ化: {btn_type}")
                button.set_active(stage, False)

        # 指定されたボタンをアクティブ化
        if button_type in self._buttons:
            debug_log(f"ボタンアクティブ化: {button_type}")
            self._buttons[button_type].set_active(stage, True)
            self._active_button = button_type

            # ボタンタイプに応じた処理
            if button_type == "start":
                print("[PhysicalButton] → voxel_carverシミュレーションを開始")
                debug_log("voxel_carver開始処理を実行")
                self._start_voxel_carver()
                # Drillコライダーを無効化
                debug_log("Drillコライダー無効化")
                self._set_drill_collider_enabled(False)
                # 音声再生開始
                self._start_audio()
            elif button_type == "stop":
                print("[PhysicalButton] → voxel_carverシミュレーションを停止")
                debug_log("voxel_carver停止処理を実行")
                self._stop_voxel_carver()
                # Drillコライダーを有効化
                debug_log("Drillコライダー有効化")
                self._set_drill_collider_enabled(True)
                # 音声再生停止
                self._stop_audio()
        else:
            debug_log(f"エラー: ボタンが見つかりません: {button_type}")

    def _start_voxel_carver(self):
        """voxel_carverのシミュレーション開始"""
        debug_log("_start_voxel_carver開始")
        try:
            # voxel_carverのグローバルインスタンスにアクセス
            import sys
            debug_log(f"sys.modules内のvoxel_carver関連: {[k for k in sys.modules.keys() if 'voxel' in k.lower()]}")

            if 'voxel_carver.extension' in sys.modules:
                debug_log("voxel_carver.extensionモジュール発見")
                voxel_carver_module = sys.modules['voxel_carver.extension']

                if hasattr(voxel_carver_module, '_extension_instance'):
                    voxel_carver = voxel_carver_module._extension_instance
                    debug_log(f"_extension_instance取得: {voxel_carver}")

                    if voxel_carver and hasattr(voxel_carver, 'on_start_simulation'):
                        debug_log("on_start_simulationメソッド呼び出し")
                        voxel_carver.on_start_simulation()
                        print("[PhysicalButton] ✓ voxel_carverシミュレーション開始成功")
                        debug_log("voxel_carver開始成功")
                    else:
                        print("[PhysicalButton] ✗ voxel_carverインスタンスが無効またはメソッドがありません")
                        debug_log(f"インスタンス有効性: {voxel_carver is not None}, メソッド存在: {hasattr(voxel_carver, 'on_start_simulation') if voxel_carver else False}")
                else:
                    print("[PhysicalButton] ✗ voxel_carverインスタンスが見つかりません")
                    debug_log("_extension_instance属性なし")
            else:
                print("[PhysicalButton] ✗ voxel_carverモジュールがロードされていません")
                debug_log("voxel_carver.extensionモジュール未ロード")

        except Exception as e:
            print(f"[PhysicalButton] ✗ voxel_carver起動エラー: {e}")
            debug_log(f"例外発生: {e}")
            import traceback
            traceback.print_exc()

    def _stop_voxel_carver(self):
        """voxel_carverのシミュレーション停止"""
        debug_log("_stop_voxel_carver開始")
        try:
            # voxel_carverのグローバルインスタンスにアクセス
            import sys
            debug_log(f"sys.modules内のvoxel_carver関連: {[k for k in sys.modules.keys() if 'voxel' in k.lower()]}")

            if 'voxel_carver.extension' in sys.modules:
                debug_log("voxel_carver.extensionモジュール発見")
                voxel_carver_module = sys.modules['voxel_carver.extension']

                if hasattr(voxel_carver_module, '_extension_instance'):
                    voxel_carver = voxel_carver_module._extension_instance
                    debug_log(f"_extension_instance取得: {voxel_carver}")

                    if voxel_carver and hasattr(voxel_carver, 'on_stop_simulation'):
                        debug_log("on_stop_simulationメソッド呼び出し")
                        voxel_carver.on_stop_simulation()
                        print("[PhysicalButton] ✓ voxel_carverシミュレーション停止成功")
                        debug_log("voxel_carver停止成功")
                    else:
                        print("[PhysicalButton] ✗ voxel_carverインスタンスが無効またはメソッドがありません")
                        debug_log(f"インスタンス有効性: {voxel_carver is not None}, メソッド存在: {hasattr(voxel_carver, 'on_stop_simulation') if voxel_carver else False}")
                else:
                    print("[PhysicalButton] ✗ voxel_carverインスタンスが見つかりません")
                    debug_log("_extension_instance属性なし")
            else:
                print("[PhysicalButton] ✗ voxel_carverモジュールがロードされていません")
                debug_log("voxel_carver.extensionモジュール未ロード")

        except Exception as e:
            print(f"[PhysicalButton] ✗ voxel_carver停止エラー: {e}")
            debug_log(f"例外発生: {e}")
            import traceback
            traceback.print_exc()

    def _set_drill_collider_enabled(self, enabled: bool):
        """Drillコライダーの有効/無効を設定"""
        debug_log(f"_set_drill_collider_enabled: enabled={enabled}")
        try:
            stage = omni.usd.get_context().get_stage()
            if not stage:
                print("[PhysicalButton] エラー: ステージが取得できません")
                debug_log("ステージ取得失敗")
                return

            # Drillコライダーのprimを取得
            drill_collider_prim = stage.GetPrimAtPath(DRILL_COLLIDER_PATH)
            if not drill_collider_prim.IsValid():
                print(f"[PhysicalButton] エラー: Drillコライダーが見つかりません: {DRILL_COLLIDER_PATH}")
                debug_log(f"Drillコライダーprim無効: {DRILL_COLLIDER_PATH}")
                return

            debug_log("Drillコライダーprim取得成功")

            # CollisionAPIを取得
            collision_api = UsdPhysics.CollisionAPI(drill_collider_prim)
            if not collision_api:
                debug_log("CollisionAPI適用")
                collision_api = UsdPhysics.CollisionAPI.Apply(drill_collider_prim)

            # collisionEnabledを設定
            collision_enabled_attr = collision_api.GetCollisionEnabledAttr()
            if not collision_enabled_attr:
                debug_log("collisionEnabled属性作成")
                collision_enabled_attr = collision_api.CreateCollisionEnabledAttr()

            collision_enabled_attr.Set(enabled)

            status = "有効" if enabled else "無効"
            print(f"[PhysicalButton] Drillコライダーを{status}化: {DRILL_COLLIDER_PATH}")
            debug_log(f"Drillコライダー設定完了: {status}")

        except Exception as e:
            print(f"[PhysicalButton] Drillコライダー設定エラー: {e}")
            debug_log(f"例外発生: {e}")
            import traceback
            traceback.print_exc()
