# coding: utf-8

import omni.ext
import omni.ui as ui
import omni.usd
import omni.kit.commands
import omni.kit.app
from pxr import Gf, UsdGeom, Sdf, Usd, UsdPhysics, PhysxSchema  # PhysX関連を追加
import numpy as np
import asyncio
import sys # エラー出力用にインポート
import traceback # エラーのトレースバック出力用にインポート
from omni.physx import get_physx_interface  # PhysXインターフェース取得用

# デフォルトのプリムパス（実際のUSDファイルに合わせて変更してください）
# 修正: 正しいCarverToolのパスに変更
DEFAULT_CARVER_PRIM_PATH = "/World/New_MillingMachine/Main/Doril/Drill/CarverTool"
# WorkpieceとVoxelMeshを/World直下で生成（親のスケールの影響を回避）
# VoxelMeshは生成時にTableのローカル座標系に変換してからTableの子として配置
DEFAULT_WORKPIECE_PRIM_PATH = "/World/Workpiece"
DEFAULT_VOXEL_MESH_PATH = "/World/New_MillingMachine/Table/VoxelMesh"  # Tableの子として配置
# Tableのパス
DEFAULT_TABLE_PATH = "/World/New_MillingMachine/Table"

# グローバル変数（物理ボタン拡張機能からアクセス用）
_extension_instance = None


class VoxelCarverExtension(omni.ext.IExt):
    """フライス盤加工シミュレーションを行うOmniverse拡張機能"""

    def on_startup(self, ext_id):
        # 拡張機能起動時の処理
        print("[voxel_carver][True] Voxel Carver 拡張機能の起動処理を開始します。")

        # グローバルインスタンス変数（物理ボタンからのアクセス用）
        global _extension_instance
        _extension_instance = self

        self._window = None
        self._update_subscription = None
        self._voxel_grid = None
        self._voxel_size = 0.15  # ボクセル1つの大きさ（単位）※小さいほど精密、500-2000個推奨
        self._workpiece_prim = None
        self._carver_prim = None
        self._voxel_mesh_prim = None
        self._is_simulating = False

        # 衝突検出方式の選択
        self._collision_method = "physx"  # "coordinate" or "physx"

        # PhysX用：ボクセルコライダー辞書 {(x,y,z): prim_path}
        self._voxel_colliders = {}

        # プリムパス設定（実際のUSDファイル構造に合わせて変更可能）
        self._carver_prim_path = DEFAULT_CARVER_PRIM_PATH
        self._workpiece_prim_path = DEFAULT_WORKPIECE_PRIM_PATH
        self._voxel_mesh_path = DEFAULT_VOXEL_MESH_PATH

        # UIウィンドウの構築
        self._window = ui.Window("Voxel Carver", width=300, height=700)
        with self._window.frame:
            with ui.ScrollingFrame():
                with ui.VStack(spacing=10):
                    ui.Label("ボクセル加工シミュレーション", style={"font_size": 18})
                    ui.Separator()

                    with ui.VStack(height=0, spacing=5):
                        ui.Label("1. シーンの準備", style={"font_size": 14})
                        ui.Button("サンプルシーンを作成", clicked_fn=self.create_sample_scene)
                        ui.Label("加工対象(Workpiece)と工具(CarverTool)を生成します。", style={"color": 0xFF888888})

                    ui.Separator()

                    with ui.VStack(height=0, spacing=5):
                        ui.Label("2. シミュレーション初期化", style={"font_size": 14})

                        # 衝突検出方式の選択
                        with ui.HStack(height=0):
                            ui.Label("衝突検出方式:", width=100)
                            self._method_label = ui.Label("PhysX判定", width=100, style={"color": 0xFF00FF00})
                        with ui.HStack(height=0, spacing=5):
                            ui.Button("PhysX判定", clicked_fn=lambda: self._set_collision_method("physx"), width=0)
                            ui.Button("座標判定", clicked_fn=lambda: self._set_collision_method("coordinate"), width=0)
                        ui.Label("PhysX: 親の影響を受けない / 座標: 高速だが影響受ける", style={"color": 0xFF888888, "font_size": 10})

                        ui.Separator(height=5)

                        # ボクセルサイズ調整
                        with ui.HStack(height=0):
                            ui.Label("ボクセルサイズ:", width=100)
                            self._voxel_size_slider = ui.FloatSlider(
                                min=0.05, max=2.0,
                                height=20
                            )
                            self._voxel_size_slider.model.set_value(self._voxel_size)
                            self._voxel_size_label = ui.Label(f"{self._voxel_size:.2f}", width=40)

                        def on_voxel_size_changed(model):
                            self._voxel_size = model.get_value_as_float()
                            self._voxel_size_label.text = f"{self._voxel_size:.2f}"

                        self._voxel_size_slider.model.add_value_changed_fn(on_voxel_size_changed)

                        ui.Label("小さいほど精密（500-2000個推奨）", style={"color": 0xFF888888, "font_size": 10})

                        ui.Button("ボクセルを初期化", clicked_fn=self.on_initialize_voxels)
                        ui.Label("加工対象をボクセルデータに変換します。", style={"color": 0xFF888888})

                    ui.Separator()

                    with ui.VStack(height=0, spacing=5):
                        ui.Label("3. シミュレーション実行", style={"font_size": 14})
                        self._start_button = ui.Button("シミュレーション開始", clicked_fn=self.on_start_simulation)
                        self._stop_button = ui.Button("シミュレーション停止", clicked_fn=self.on_stop_simulation, enabled=False)

                    ui.Separator()

                    with ui.VStack(height=0, spacing=5):
                        ui.Label("4. デバッグ機能", style={"font_size": 14})
                        ui.Button("コライダーを可視化", clicked_fn=self.visualize_colliders)
                        ui.Button("コライダー情報を表示", clicked_fn=self.debug_colliders)
                        ui.Button("CarverTool情報を表示", clicked_fn=self.debug_carver)
                        ui.Label("PhysX判定のデバッグ用機能です。", style={"color": 0xFF888888})

                    ui.Separator()

                    with ui.VStack(height=0, spacing=5):
                        ui.Label("5. オプション機能", style={"font_size": 14})
                        ui.Button("WorkpieceをTableに移動", clicked_fn=self.move_to_table)
                        ui.Label("シミュレーション完了後にWorkpieceを整理します。", style={"color": 0xFF888888})

                    ui.Separator()
                    ui.Button("シミュレーションをリセット", clicked_fn=self.on_reset)

    def _set_collision_method(self, method):
        """衝突検出方式を設定"""
        self._collision_method = method
        if method == "physx":
            self._method_label.text = "PhysX判定"
            self._method_label.style = {"color": 0xFF00FF00}
            print("[voxel_carver][True] 衝突検出方式をPhysX判定に変更しました")
        else:
            self._method_label.text = "座標判定"
            self._method_label.style = {"color": 0xFFFFAA00}
            print("[voxel_carver][True] 衝突検出方式を座標判定に変更しました")

    def visualize_colliders(self):
        """ボクセルコライダーを可視化（デバッグ用）"""
        stage = omni.usd.get_context().get_stage()

        if not self._voxel_colliders:
            print("[voxel_carver][Warning] ボクセルコライダーが存在しません")
            print("[voxel_carver][Info] PhysX判定を選択してボクセル初期化を実行してください")
            return

        print(f"[voxel_carver][Debug] ========== コライダー可視化 ==========")
        print(f"[voxel_carver][Debug] コライダー数: {len(self._voxel_colliders)}")

        visible_count = 0
        for (x, y, z), collider_path in self._voxel_colliders.items():
            prim = stage.GetPrimAtPath(collider_path)
            if prim and prim.IsValid():
                imageable = UsdGeom.Imageable(prim)
                imageable.MakeVisible()
                visible_count += 1

        print(f"[voxel_carver][True] {visible_count}個のコライダーを可視化しました（赤い立方体）")
        print("[voxel_carver][Info] コライダーはボクセル表面にのみ配置されています")

    def debug_colliders(self):
        """ボクセルコライダーの詳細情報を表示"""
        stage = omni.usd.get_context().get_stage()

        print(f"[voxel_carver][Debug] ========== コライダー情報 ==========")
        print(f"[voxel_carver][Debug] 衝突検出方式: {self._collision_method}")
        print(f"[voxel_carver][Debug] コライダー総数: {len(self._voxel_colliders)}")

        if not self._voxel_colliders:
            print("[voxel_carver][Warning] コライダーが存在しません")
            print("[voxel_carver][Info] PhysX判定モードでボクセル初期化してください")
            return

        # 最初の5個のコライダーをサンプル表示
        sample_count = min(5, len(self._voxel_colliders))
        print(f"[voxel_carver][Debug] サンプル表示（最初の{sample_count}個）:")

        for i, ((x, y, z), collider_path) in enumerate(list(self._voxel_colliders.items())[:sample_count]):
            prim = stage.GetPrimAtPath(collider_path)
            if prim and prim.IsValid():
                # 座標情報を取得
                xformable = UsdGeom.Xformable(prim)
                world_transform = xformable.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
                world_pos = world_transform.GetRow3(3)

                # PhysX Collision情報
                has_collision = prim.HasAPI(UsdPhysics.CollisionAPI)

                # ボクセル座標
                vx = prim.GetAttribute("voxel:x").Get() if prim.HasAttribute("voxel:x") else "N/A"
                vy = prim.GetAttribute("voxel:y").Get() if prim.HasAttribute("voxel:y") else "N/A"
                vz = prim.GetAttribute("voxel:z").Get() if prim.HasAttribute("voxel:z") else "N/A"

                print(f"[voxel_carver][Debug] [{i+1}] Path: {collider_path}")
                print(f"[voxel_carver][Debug]     ボクセル座標: ({vx}, {vy}, {vz})")
                print(f"[voxel_carver][Debug]     ワールド座標: {world_pos}")
                print(f"[voxel_carver][Debug]     CollisionAPI: {has_collision}")

        print(f"[voxel_carver][Debug] =========================================")

    def debug_carver(self):
        """CarverToolの詳細情報を表示"""
        stage = omni.usd.get_context().get_stage()

        if not self._carver_prim or not self._carver_prim.IsValid():
            carver_prim = stage.GetPrimAtPath(self._carver_prim_path)
            if carver_prim and carver_prim.IsValid():
                self._carver_prim = carver_prim
            else:
                print(f"[voxel_carver][Warning] CarverToolが見つかりません: {self._carver_prim_path}")
                return

        print(f"[voxel_carver][Debug] ========== CarverTool 情報 ==========")
        print(f"[voxel_carver][Debug] Path: {self._carver_prim_path}")

        # トランスフォーム情報
        carver_xform = UsdGeom.Xformable(self._carver_prim)
        world_transform = carver_xform.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
        world_pos = world_transform.GetRow3(3)

        # ローカル座標
        local_translate = None
        for op in carver_xform.GetOrderedXformOps():
            if op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
                local_translate = op.Get()
                break

        print(f"[voxel_carver][Debug] ローカル座標: {local_translate}")
        print(f"[voxel_carver][Debug] ワールド座標: {world_pos}")

        # サイズとスケール
        carver_size = self._carver_prim.GetAttribute("size").Get()
        x_scale = Gf.Vec3d(world_transform[0][0], world_transform[0][1], world_transform[0][2]).GetLength()
        y_scale = Gf.Vec3d(world_transform[1][0], world_transform[1][1], world_transform[1][2]).GetLength()
        z_scale = Gf.Vec3d(world_transform[2][0], world_transform[2][1], world_transform[2][2]).GetLength()

        print(f"[voxel_carver][Debug] サイズ: {carver_size}")
        print(f"[voxel_carver][Debug] スケール: ({x_scale:.3f}, {y_scale:.3f}, {z_scale:.3f})")

        effective_half_width = (carver_size / 2.0) * x_scale
        effective_half_height = (carver_size / 2.0) * y_scale
        effective_half_depth = (carver_size / 2.0) * z_scale

        print(f"[voxel_carver][Debug] 実効半サイズ: ({effective_half_width:.3f}, {effective_half_height:.3f}, {effective_half_depth:.3f})")

        # PhysX情報
        has_collision = self._carver_prim.HasAPI(UsdPhysics.CollisionAPI)
        has_rigidbody = self._carver_prim.HasAPI(UsdPhysics.RigidBodyAPI)

        print(f"[voxel_carver][Debug] CollisionAPI: {has_collision}")
        print(f"[voxel_carver][Debug] RigidBodyAPI: {has_rigidbody}")

        # 近傍のコライダーをチェック
        if self._voxel_colliders:
            print(f"[voxel_carver][Debug] --- 近傍のコライダーチェック ---")
            close_colliders = []

            for (x, y, z), collider_path in self._voxel_colliders.items():
                voxel_prim = stage.GetPrimAtPath(collider_path)
                if voxel_prim and voxel_prim.IsValid():
                    voxel_xform = UsdGeom.Xformable(voxel_prim)
                    voxel_world_transform = voxel_xform.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
                    voxel_world_pos = voxel_world_transform.GetRow3(3)

                    distance = (voxel_world_pos - world_pos).GetLength()

                    # 距離が近い場合
                    if distance < effective_half_width + effective_half_height + effective_half_depth + self._voxel_size:
                        close_colliders.append((distance, x, y, z, voxel_world_pos))

            # 距離でソート
            close_colliders.sort(key=lambda item: item[0])

            print(f"[voxel_carver][Debug] 検出範囲内のコライダー数: {len(close_colliders)}")

            for i, (distance, x, y, z, voxel_pos) in enumerate(close_colliders[:5]):
                diff = voxel_pos - world_pos
                print(f"[voxel_carver][Debug] [{i+1}] 距離: {distance:.3f}")
                print(f"[voxel_carver][Debug]     ボクセル座標: ({x}, {y}, {z})")
                print(f"[voxel_carver][Debug]     差分ベクトル: ({diff[0]:.3f}, {diff[1]:.3f}, {diff[2]:.3f})")

                # AABB判定結果をシミュレート
                in_x = abs(diff[0]) < effective_half_width + self._voxel_size/2.0
                in_y = abs(diff[1]) < effective_half_height + self._voxel_size/2.0
                in_z = abs(diff[2]) < effective_half_depth + self._voxel_size/2.0
                would_collide = in_x and in_y and in_z

                print(f"[voxel_carver][Debug]     X判定: {in_x} (|{diff[0]:.3f}| < {effective_half_width + self._voxel_size/2.0:.3f})")
                print(f"[voxel_carver][Debug]     Y判定: {in_y} (|{diff[1]:.3f}| < {effective_half_height + self._voxel_size/2.0:.3f})")
                print(f"[voxel_carver][Debug]     Z判定: {in_z} (|{diff[2]:.3f}| < {effective_half_depth + self._voxel_size/2.0:.3f})")
                print(f"[voxel_carver][Debug]     → 衝突判定: {would_collide}")

        print(f"[voxel_carver][Debug] =========================================")


    def on_shutdown(self):
        # 拡張機能終了時の処理
        print("[voxel_carver][True] Voxel Carver 拡張機能の終了処理を実行します。")

        # グローバルインスタンス変数をクリア
        global _extension_instance
        _extension_instance = None

        if self._update_subscription:
            self._update_subscription.unsubscribe()
        if self._window:
            self._window.destroy()
        self._window = None

    def create_sample_scene(self):
        """シミュレーション用のサンプルオブジェクトを作成（USD APIを直接使用）"""
        try:
            stage = omni.usd.get_context().get_stage()

            # 加工対象の立方体を/World直下で作成（縦横高さの比 3:4:1）
            workpiece_prim_path = Sdf.Path(self._workpiece_prim_path)
            if not stage.GetPrimAtPath(workpiece_prim_path):
                omni.kit.commands.execute('CreatePrim',
                    prim_type='Cube',
                    prim_path=self._workpiece_prim_path,
                    attributes={'size': 1.0, 'extent': [(-6, -2, -8), (6, 2, 8)]})
                print(f"[voxel_carver][True] 加工対象プリムをパス '{self._workpiece_prim_path}' に作成しました。")

            # 工具となる四角柱（Cube）を作成（既に存在する場合はスキップ）
            carver_prim_path = Sdf.Path(self._carver_prim_path)
            carver_prim = stage.GetPrimAtPath(carver_prim_path)

            if not carver_prim or not carver_prim.IsValid():
                # 新規作成（四角柱）
                # size=2.0にすることで、円柱のradius=1.0, height=2.0と同等の基本サイズになる
                omni.kit.commands.execute('CreatePrim',
                    prim_type='Cube',
                    prim_path=self._carver_prim_path,
                    attributes={'size': 2.5})
                print(f"[voxel_carver][True] 工具プリム（四角柱）をパス '{self._carver_prim_path}' に作成しました。")

                # 新規作成した場合のみトランスフォームを設定
                carver_prim = stage.GetPrimAtPath(carver_prim_path)
                if carver_prim:
                    xformable = UsdGeom.Xformable(carver_prim)

                    # 既存のxformOpを取得または新規作成
                    xform_ops = xformable.GetOrderedXformOps()
                    translate_op = None
                    scale_op = None
                    rotate_op = None

                    for op in xform_ops:
                        if op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
                            translate_op = op
                        elif op.GetOpType() == UsdGeom.XformOp.TypeScale:
                            scale_op = op
                        elif op.GetOpType() == UsdGeom.XformOp.TypeRotateXYZ:
                            rotate_op = op

                    # 存在しない場合のみ新規作成
                    if translate_op is None:
                        translate_op = xformable.AddTranslateOp(UsdGeom.XformOp.PrecisionDouble)
                    if scale_op is None:
                        scale_op = xformable.AddScaleOp(UsdGeom.XformOp.PrecisionFloat)
                    if rotate_op is None:
                        rotate_op = xformable.AddRotateXYZOp(UsdGeom.XformOp.PrecisionFloat)

                    # 値を設定（円柱と同じスケールと位置を使用）
                    translate_op.Set(Gf.Vec3d(0.22720335689304427, 0.5571431052519529, 4.62035317974437))
                    scale_op.Set(Gf.Vec3f(5, 30, 5))
                    rotate_op.Set(Gf.Vec3f(90.0, 0.0, 0.0))

                    imageable = UsdGeom.Imageable(carver_prim)
                    imageable.MakeInvisible()

                    print("[voxel_carver][True] USD API経由で工具プリム（四角柱）のスケール、回転(XYZ)、位置を設定しました。")
            else:
                # 既存のCarverToolを使用
                print(f"[voxel_carver][True] 既存の工具プリムを使用します: '{self._carver_prim_path}'")

                # 既存のCarverToolの型をチェック
                if carver_prim.IsA(UsdGeom.Cylinder):
                    print(f"[voxel_carver][Warning] 既存のCarverToolは円柱（Cylinder）です")
                    print(f"[voxel_carver][Warning] 四角柱判定を使用するには、「シミュレーションをリセット」後に再作成してください")
                elif carver_prim.IsA(UsdGeom.Cube):
                    print(f"[voxel_carver][True] 既存のCarverToolは四角柱（Cube）です")

                # 既存のCarverToolのローカル座標とワールド座標を表示
                xformable = UsdGeom.Xformable(carver_prim)
                world_transform = xformable.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
                world_pos = world_transform.GetRow3(3)

                # ローカル座標を取得
                local_translate = None
                for op in xformable.GetOrderedXformOps():
                    if op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
                        local_translate = op.Get()
                        break

                print(f"[voxel_carver][Info] CarverTool ローカル座標: {local_translate}")
                print(f"[voxel_carver][Info] CarverTool ワールド座標: {world_pos}")

            print("[voxel_carver][True] サンプルシーンが正常に作成されました。")

        except Exception as e:
            print(f"[voxel_carver][False] サンプルシーンの作成中に予期せぬエラーが発生しました: {e}", file=sys.stderr)
            traceback.print_exc()

    def on_initialize_voxels(self):
        """加工対象オブジェクトをボクセル化する"""
        stage = omni.usd.get_context().get_stage()
        self._workpiece_prim = stage.GetPrimAtPath(self._workpiece_prim_path)

        if not self._workpiece_prim:
            print(f"[voxel_carver][False] エラー: 加工対象のプリムがパス '{self._workpiece_prim_path}' に見つかりません。")
            return

        # ワークピースのワールド座標でのバウンディングボックスを取得
        # Workpieceは/World直下にあるため、計算が簡潔
        workpiece_xformable = UsdGeom.Xformable(self._workpiece_prim)
        workpiece_world_transform = workpiece_xformable.ComputeLocalToWorldTransform(Usd.TimeCode.Default())

        # ローカルextentを取得
        extent_attr = self._workpiece_prim.GetAttribute("extent")
        if not extent_attr:
            print(f"[voxel_carver][False] エラー: '{self._workpiece_prim_path}' に 'extent' アトリビュートが見つかりません。")
            return

        local_bounds = extent_attr.Get()
        local_min = Gf.Vec3d(local_bounds[0])
        local_max = Gf.Vec3d(local_bounds[1])

        # ローカル座標をワールド座標に変換
        world_min = workpiece_world_transform.Transform(local_min)
        world_max = workpiece_world_transform.Transform(local_max)

        # バウンディングボックスの最小・最大を再計算（回転がある場合に備えて）
        world_bbox_min = Gf.Vec3d(
            min(world_min[0], world_max[0]),
            min(world_min[1], world_max[1]),
            min(world_min[2], world_max[2])
        )
        world_bbox_max = Gf.Vec3d(
            max(world_min[0], world_max[0]),
            max(world_min[1], world_max[1]),
            max(world_min[2], world_max[2])
        )

        print(f"[voxel_carver][Info] Workpieceワールド座標: min={world_bbox_min}, max={world_bbox_max}")

        # VoxelMeshのスケール調整（さらに半分に縮小、XYZ比率5:1:3）
        base_scale = 0.03  # 全体を1/20に縮小（元の1/10のさらに半分）

        # XYZ比率を5:1:3に設定
        # 基準をY軸（最小）とし、X軸を5倍、Z軸を3倍
        x_ratio = 1.0
        y_ratio = 10.0
        z_ratio = 1.0

        # グリッドサイズを計算（スケールと比率を適用）
        original_grid_size = world_bbox_max - world_bbox_min
        grid_size = Gf.Vec3d(
            original_grid_size[0] * base_scale * x_ratio,
            original_grid_size[1] * base_scale * y_ratio,
            original_grid_size[2] * base_scale * z_ratio
        )

        # グリッドの解像度を計算
        self._grid_dims = np.ceil(np.array([grid_size[0], grid_size[1], grid_size[2]]) / self._voxel_size).astype(int)

        # Workpieceのワールド座標を記録（削り取り判定用）
        self._workpiece_world_min = world_bbox_min
        self._workpiece_world_max = world_bbox_max

        # グリッド原点を(0,0,0)に設定（VoxelMeshを原点に生成）
        # グリッド座標系: グリッド中心を原点とした相対座標
        self._grid_origin = Gf.Vec3d(0, 0, 0) - grid_size / 2.0

        # Workpiece中心からのオフセット（削り取り時に使用）
        self._workpiece_center = (world_bbox_min + world_bbox_max) / 2.0

        # ボクセル数をチェック
        total_voxels = int(self._grid_dims[0] * self._grid_dims[1] * self._grid_dims[2])
        print(f"[voxel_carver][True] ボクセルグリッドを初期化中...")
        print(f"[voxel_carver][Info] ベーススケール: {base_scale} (1/20)")
        print(f"[voxel_carver][Info] XYZ比率: {x_ratio}:{y_ratio}:{z_ratio}")
        print(f"[voxel_carver][Info] 元のサイズ: {original_grid_size}")
        print(f"[voxel_carver][Info] 調整後サイズ: {grid_size}")
        print(f"[voxel_carver][Info] グリッド解像度 (X×Y×Z): {self._grid_dims[0]}×{self._grid_dims[1]}×{self._grid_dims[2]}")
        print(f"[voxel_carver][Info] 合計ボクセル数: {total_voxels:,} ボクセル")
        print(f"[voxel_carver][Info] ボクセルサイズ: {self._voxel_size} 単位")
        print(f"[voxel_carver][Info] グリッド原点（VoxelMesh基準）: {self._grid_origin}")
        print(f"[voxel_carver][Info] Workpiece中心（ワールド座標）: {self._workpiece_center}")

        # パフォーマンス警告
        if total_voxels > 1000000:
            print(f"[voxel_carver][Warning] ボクセル数が100万を超えています（{total_voxels:,}）！")
            print(f"[voxel_carver][Warning] 初期化とシミュレーションが非常に重くなる可能性があります。")
            print(f"[voxel_carver][Warning] ボクセルサイズを大きくすることを推奨します（現在: {self._voxel_size}）")

        # ボクセルグリッドを初期化（1が物質、0が空間）
        import time
        start_time = time.time()
        self._voxel_grid = np.ones(self._grid_dims, dtype=np.uint8)
        elapsed = time.time() - start_time

        print(f"[voxel_carver][True] ボクセルグリッド初期化完了（{elapsed:.2f}秒）")
        print(f"[voxel_carver][Debug] グリッド原点（ワールド）: {self._grid_origin}")

        # 元のワークピースメッシュを非表示にする
        workpiece_geom = UsdGeom.Imageable(self._workpiece_prim)
        workpiece_geom.MakeInvisible()

        # ボクセルからメッシュを生成して表示
        self.update_voxel_mesh()
        print("[voxel_carver][True] ボクセルからメッシュが生成されました。")

        # PhysX判定の場合、コライダーを作成
        if self._collision_method == "physx":
            self._create_voxel_colliders()
            print("[voxel_carver][True] PhysX判定用のコライダーを作成しました。")

        prim_path = DEFAULT_VOXEL_MESH_PATH
        voxel_prim = stage.GetPrimAtPath(prim_path)
        xformable = UsdGeom.Xformable(voxel_prim)

        # TranslateOp
        translate_op = None
        for xform_op in xformable.GetOrderedXformOps():
             if xform_op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
                translate_op = xform_op
                break

        if not translate_op:
            translate_op = xformable.AddTranslateOp()

        translate_op.Set(Gf.Vec3d((-0.8508053237818682, 1.006013237532796, -2.708781343569189)))
        print(f"[item_setting] ✓ プロキシ位置設定: (-0.8508053237818682, 1.006013237532796, -2.708781343569189)")

        imageable = UsdGeom.Imageable(voxel_prim)
        imageable.MakeInvisible()

        # ========== VoxelMeshプリムにVR検出用の物理APIとカスタム属性を追加 ==========
        voxel_mesh_prim = stage.GetPrimAtPath(self._voxel_mesh_path)
        if voxel_mesh_prim and voxel_mesh_prim.IsValid():
            print(f"[voxel_carver][Info] VoxelMeshにVR検出用属性を追加中...")

            # 1. CollisionAPI を適用 (collision enabled = True)
            if not voxel_mesh_prim.HasAPI(UsdPhysics.CollisionAPI):
                collision_api = UsdPhysics.CollisionAPI.Apply(voxel_mesh_prim)
                print(f"[voxel_carver][True] CollisionAPI を適用しました")
            else:
                collision_api = UsdPhysics.CollisionAPI(voxel_mesh_prim)
                print(f"[voxel_carver][Info] CollisionAPI は既に適用されています")

            # collision enabled = True を設定
            collision_enabled_attr = collision_api.GetCollisionEnabledAttr()
            if not collision_enabled_attr:
                collision_enabled_attr = collision_api.CreateCollisionEnabledAttr()
            collision_enabled_attr.Set(True)
            print(f"[voxel_carver][True] collisionEnabled = True を設定しました")

            # 2. RigidBodyAPI を適用 (rigid body enabled = False)
            if not voxel_mesh_prim.HasAPI(UsdPhysics.RigidBodyAPI):
                rigid_body_api = UsdPhysics.RigidBodyAPI.Apply(voxel_mesh_prim)
                print(f"[voxel_carver][True] RigidBodyAPI を適用しました")
            else:
                rigid_body_api = UsdPhysics.RigidBodyAPI(voxel_mesh_prim)
                print(f"[voxel_carver][Info] RigidBodyAPI は既に適用されています")

            # rigid body enabled = False を設定
            rb_enabled_attr = rigid_body_api.GetRigidBodyEnabledAttr()
            if not rb_enabled_attr:
                rb_enabled_attr = rigid_body_api.CreateRigidBodyEnabledAttr()
            rb_enabled_attr.Set(False)
            print(f"[voxel_carver][True] rigidBodyEnabled = False を設定しました")

            # 3. custom:grab 属性を追加 (Bool, デフォルト False)
            grab_attr = voxel_mesh_prim.GetAttribute("custom:grab")
            if not grab_attr:
                grab_attr = voxel_mesh_prim.CreateAttribute("custom:grab", Sdf.ValueTypeNames.Bool)
            grab_attr.Set(False)
            print(f"[voxel_carver][True] custom:grab = False を設定しました")

            # 4. custom:task 属性を追加 (Bool, デフォルト False)
            task_attr = voxel_mesh_prim.GetAttribute("custom:task")
            if not task_attr:
                task_attr = voxel_mesh_prim.CreateAttribute("custom:task", Sdf.ValueTypeNames.Bool)
            task_attr.Set(False)
            print(f"[voxel_carver][True] custom:task = False を設定しました")

            # 5. custom:placed 属性を追加 (Bool, デフォルト False) - 取り外し検出用
            placed_attr = voxel_mesh_prim.GetAttribute("custom:placed")
            if not placed_attr:
                placed_attr = voxel_mesh_prim.CreateAttribute("custom:placed", Sdf.ValueTypeNames.Bool)
            placed_attr.Set(False)
            print(f"[voxel_carver][True] custom:placed = False を設定しました")

            # 6. custom:proxy 属性を追加 (Bool, デフォルト True) - Proxyシステム使用フラグ
            proxy_attr = voxel_mesh_prim.GetAttribute("custom:proxy")
            if not proxy_attr:
                proxy_attr = voxel_mesh_prim.CreateAttribute("custom:proxy", Sdf.ValueTypeNames.Bool)
            proxy_attr.Set(True)
            print(f"[voxel_carver][True] custom:proxy = True を設定しました")

            # 7. custom:proxy_path 属性を追加 (String) - Proxyオブジェクトのパス
            proxy_path_attr = voxel_mesh_prim.GetAttribute("custom:proxy_path")
            if not proxy_path_attr:
                proxy_path_attr = voxel_mesh_prim.CreateAttribute("custom:proxy_path", Sdf.ValueTypeNames.String)
            proxy_path_attr.Set("/World/ItemTray/Metal_proxy/Metal_proxy")
            print(f"[voxel_carver][True] custom:proxy_path = '/World/ItemTray/Metal_proxy/Metal_proxy' を設定しました")

            print(f"[voxel_carver][True] VoxelMesh ({self._voxel_mesh_path}) にVR検出用属性の追加完了")
            print(f"[voxel_carver][Info] - CollisionAPI: enabled=True")
            print(f"[voxel_carver][Info] - RigidBodyAPI: enabled=False")
            print(f"[voxel_carver][Info] - custom:grab: False")
            print(f"[voxel_carver][Info] - custom:task: False")
            print(f"[voxel_carver][Info] - custom:placed: False")
            print(f"[voxel_carver][Info] - custom:proxy: True")
            print(f"[voxel_carver][Info] - custom:proxy_path: /World/ItemTray/Metal_proxy/Metal_proxy")
        else:
            print(f"[voxel_carver][Warning] VoxelMeshプリムが見つかりません: {self._voxel_mesh_path}")

    def on_start_simulation(self):
        """シミュレーションを開始する"""
        if not hasattr(self, '_voxel_grid') or self._voxel_grid is None:
            print("[voxel_carver][False] エラー: ボクセルが初期化されていません。「ボクセルを初期化」を先に実行してください。")
            return

        print("[voxel_carver][True] シミュレーションを開始します。")
        self._is_simulating = True
        self._start_button.enabled = False
        self._stop_button.enabled = True

        # 更新ループのサブスクリプションを開始
        if not self._update_subscription:
            # アプリケーションの更新イベントストリームを取得
            update_stream = omni.kit.app.get_app().get_update_event_stream()
            # 取得したストリームに対して、更新処理(_on_update)の購読を作成する
            self._update_subscription = update_stream.create_subscription_to_pop(self._on_update, name="voxel_carver_update")

        # 工具プリムを取得
        stage = omni.usd.get_context().get_stage()
        self._carver_prim = stage.GetPrimAtPath(self._carver_prim_path)

        # プリムの存在確認とデバッグ情報
        if not self._carver_prim or not self._carver_prim.IsValid():
            print(f"[voxel_carver][Warning] CarverToolが指定パスに見つかりません: {self._carver_prim_path}")
            print("[voxel_carver][Debug] CarverToolを自動検索します...")

            # CarverToolを自動検索
            found_carver_paths = []
            for prim in stage.Traverse():
                prim_name_lower = prim.GetName().lower()
                if "carvertool" in prim_name_lower or prim.GetName() == "CarverTool":
                    found_carver_paths.append(str(prim.GetPath()))
                    print(f"[voxel_carver][Debug] - CarverTool候補: {prim.GetPath()}")
                elif "drill" in prim_name_lower and (prim.IsA(UsdGeom.Sphere) or prim.IsA(UsdGeom.Cylinder) or prim.IsA(UsdGeom.Cube)):
                    # Sphere, Cylinder, Cubeタイプで"drill"を含む名前のPrimもCarverTool候補
                    prim_type = "Cylinder" if prim.IsA(UsdGeom.Cylinder) else ("Sphere" if prim.IsA(UsdGeom.Sphere) else "Cube")
                    found_carver_paths.append(str(prim.GetPath()))
                    print(f"[voxel_carver][Debug] - Drill候補 ({prim_type}): {prim.GetPath()}")

            if found_carver_paths:
                # 最初に見つかったパスを使用
                self._carver_prim_path = found_carver_paths[0]
                self._carver_prim = stage.GetPrimAtPath(self._carver_prim_path)
                print(f"[voxel_carver][True] CarverToolを自動検出しました: {self._carver_prim_path}")
            else:
                print(f"[voxel_carver][False] エラー: CarverToolが見つかりません")
                print("[voxel_carver][Info] シーン内のDrill関連Prim:")
                for prim in stage.Traverse():
                    if "drill" in prim.GetName().lower():
                        prim_type = prim.GetTypeName() if prim.GetTypeName() else "Unknown"
                        print(f"[voxel_carver][Debug] - {prim.GetPath()} (Type: {prim_type})")
                return
        else:
            print(f"[voxel_carver][True] CarverToolプリムが見つかりました: {self._carver_prim_path}")

        # VoxelMeshプリムを取得または作成
        self._voxel_mesh_prim = stage.GetPrimAtPath(self._voxel_mesh_path)
        if not self._voxel_mesh_prim or not self._voxel_mesh_prim.IsValid():
            print(f"[voxel_carver][Info] VoxelMeshプリムを作成します: {self._voxel_mesh_path}")
            self._create_voxel_mesh()
        else:
            print(f"[voxel_carver][True] VoxelMeshプリムが見つかりました: {self._voxel_mesh_path}")

    def on_stop_simulation(self):
        """シミュレーションを停止する"""
        print("[voxel_carver][True] シミュレーションを停止します。")
        self._is_simulating = False
        self._start_button.enabled = True
        self._stop_button.enabled = False

        if self._update_subscription:
            self._update_subscription = None

    def _create_voxel_colliders(self):
        """ボクセル表面にPhysXコライダーを作成（PhysX判定用）"""
        stage = omni.usd.get_context().get_stage()
        self._voxel_colliders = {}

        # VoxelMeshの子としてVoxelCollidersを作成
        voxel_mesh_prim = stage.GetPrimAtPath(self._voxel_mesh_path)
        if not voxel_mesh_prim or not voxel_mesh_prim.IsValid():
            print(f"[voxel_carver][Info] VoxelMeshが存在しないため作成します")
            self.update_voxel_mesh()
            voxel_mesh_prim = stage.GetPrimAtPath(self._voxel_mesh_path)

        # VoxelCollidersをVoxelMeshの子として作成
        colliders_root_path = f"{self._voxel_mesh_path}/VoxelColliders"
        if not stage.GetPrimAtPath(colliders_root_path):
            UsdGeom.Xform.Define(stage, colliders_root_path)
            print(f"[voxel_carver][Info] VoxelCollidersをVoxelMeshの子として作成: {colliders_root_path}")

        print(f"[voxel_carver][Info] コライダー親プリム: {colliders_root_path}")
        print(f"[voxel_carver][Info] コライダーはVoxelMeshの子として配置され、ローカル座標系を使用します")

        print("[voxel_carver][Info] ボクセル表面にPhysXコライダーを作成中...")
        print(f"[voxel_carver][Debug] グリッドサイズ: {self._grid_dims}")

        # グリッド境界の診断
        print(f"[voxel_carver][Debug] === グリッド境界診断 ===")
        print(f"[voxel_carver][Debug] 境界ボクセルサンプル:")
        print(f"[voxel_carver][Debug]   (0,0,0) = {self._voxel_grid[0,0,0]}")
        print(f"[voxel_carver][Debug]   (1,1,1) = {self._voxel_grid[1,1,1]}")
        print(f"[voxel_carver][Debug]   (0,1,1) = {self._voxel_grid[0,1,1]}")
        print(f"[voxel_carver][Debug]   (1,0,1) = {self._voxel_grid[1,0,1]}")
        print(f"[voxel_carver][Debug]   (1,1,0) = {self._voxel_grid[1,1,0]}")

        collider_count = 0

        # すべてのボクセルにコライダーを作成（シンプルで安定）
        # 注: 表面のみに最適化すると削り取り時の動的追加が複雑になるため、
        #     最初から全ボクセルにコライダーを作成する方が実用的
        for x in range(self._grid_dims[0]):
            for y in range(self._grid_dims[1]):
                for z in range(self._grid_dims[2]):
                    if self._voxel_grid[x, y, z] == 1:
                        # すべての固体ボクセルにコライダーを作成
                        # grid_origin基準のローカル座標（VoxelMeshのローカル座標系）
                        voxel_local_pos = self._grid_origin + Gf.Vec3d(x + 0.5, y + 0.5, z + 0.5) * self._voxel_size
                        collider_path = f"{colliders_root_path}/Voxel_{x}_{y}_{z}"

                        # Cubeプリムを作成
                        cube_prim = UsdGeom.Cube.Define(stage, collider_path)
                        cube_prim.GetSizeAttr().Set(self._voxel_size)

                        # Transform設定（既存のOpを取得または新規作成）
                        xformable = UsdGeom.Xformable(cube_prim)
                        translate_op = None

                        # 既存のTransformOpを検索
                        for op in xformable.GetOrderedXformOps():
                            if op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
                                translate_op = op

                        # 存在しない場合のみ新規作成
                        if translate_op is None:
                            translate_op = xformable.AddTranslateOp(UsdGeom.XformOp.PrecisionDouble)

                        # VoxelMeshのローカル座標系で設定（grid_origin基準）
                        # VoxelCollidersはVoxelMeshの子なので、VoxelMeshと同じローカル座標系を使用
                        translate_op.Set(voxel_local_pos)

                        # デバッグ出力（最初の1つだけ）
                        if collider_count == 0:
                            print(f"[voxel_carver][Debug] ボクセル座標（VoxelMeshローカル座標）:")
                            print(f"[voxel_carver][Debug]   ローカル座標: {voxel_local_pos}")
                            print(f"[voxel_carver][Debug]   グリッド原点: {self._grid_origin}")
                            print(f"[voxel_carver][Debug]   ボクセルサイズ: {self._voxel_size}")

                        # PhysX Collider設定（Triggerモード）
                        prim = cube_prim.GetPrim()
                        collision_api = UsdPhysics.CollisionAPI.Apply(prim)

                        # カスタム属性でボクセル座標を保存
                        prim.CreateAttribute("voxel:x", Sdf.ValueTypeNames.Int).Set(int(x))
                        prim.CreateAttribute("voxel:y", Sdf.ValueTypeNames.Int).Set(int(y))
                        prim.CreateAttribute("voxel:z", Sdf.ValueTypeNames.Int).Set(int(z))

                        # 非表示（視覚的には不要）
                        UsdGeom.Imageable(prim).MakeInvisible()

                        self._voxel_colliders[(x, y, z)] = collider_path
                        collider_count += 1

        print(f"[voxel_carver][Info] ========== コライダー生成統計 ==========")
        print(f"[voxel_carver][Info] 総コライダー数: {collider_count}個（全ボクセル）")
        print(f"[voxel_carver][Info] ==========================================")

    def _check_physx_collision(self):
        """PhysXを使った衝突判定"""
        stage = omni.usd.get_context().get_stage()

        # デバッグ出力（初回のみ）
        if not hasattr(self, '_physx_debug_printed'):
            print("[voxel_carver][Debug] ========== PhysX衝突判定開始 ==========")
            print(f"[voxel_carver][Debug] コライダー数: {len(self._voxel_colliders)}")
            self._physx_debug_printed = True

        if not self._voxel_colliders:
            if not hasattr(self, '_no_colliders_warning'):
                print("[voxel_carver][Warning] ボクセルコライダーが存在しません")
                print("[voxel_carver][Info] PhysX判定モードでボクセル初期化してください")
                self._no_colliders_warning = True
            return

        # CarverToolのバウンディングボックスを取得
        carver_xform = UsdGeom.Xformable(self._carver_prim)
        carver_world_transform = carver_xform.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
        carver_world_pos = carver_world_transform.GetRow3(3)

        # CarverToolのサイズとスケールを取得
        carver_size = self._carver_prim.GetAttribute("size").Get()
        if not carver_size:
            return

        # スケール取得
        x_scale = Gf.Vec3d(carver_world_transform[0][0], carver_world_transform[0][1], carver_world_transform[0][2]).GetLength()
        y_scale = Gf.Vec3d(carver_world_transform[1][0], carver_world_transform[1][1], carver_world_transform[1][2]).GetLength()
        z_scale = Gf.Vec3d(carver_world_transform[2][0], carver_world_transform[2][1], carver_world_transform[2][2]).GetLength()

        effective_half_extents = Gf.Vec3f(
            (carver_size / 2.0) * x_scale,
            (carver_size / 2.0) * y_scale,
            (carver_size / 2.0) * z_scale
        )

        # デバッグ出力（初回のみ）
        if not hasattr(self, '_physx_carver_debug_printed'):
            print(f"[voxel_carver][Debug] CarverTool ワールド座標: {carver_world_pos}")
            print(f"[voxel_carver][Debug] CarverTool 実効半サイズ: {effective_half_extents}")
            self._physx_carver_debug_printed = True

        # PhysX Overlap Query実行
        needs_update = False
        voxels_to_remove = []
        check_count = 0

        # 各ボクセルコライダーとの距離チェック（簡易版）
        for (x, y, z), collider_path in list(self._voxel_colliders.items()):
            voxel_prim = stage.GetPrimAtPath(collider_path)
            if not voxel_prim or not voxel_prim.IsValid():
                continue

            check_count += 1

            # ボクセルの位置を取得
            voxel_xform = UsdGeom.Xformable(voxel_prim)
            voxel_world_transform = voxel_xform.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
            voxel_world_pos = voxel_world_transform.GetRow3(3)

            # AABB判定（PhysXトランスフォーム適用済み座標を使用）
            diff = voxel_world_pos - carver_world_pos

            # デバッグ出力（最初の衝突候補のみ）
            if check_count <= 3 and not hasattr(self, f'_physx_voxel_check_{x}_{y}_{z}'):
                distance = diff.GetLength()
                print(f"[voxel_carver][Debug] ボクセル({x},{y},{z}) チェック:")
                print(f"[voxel_carver][Debug]   位置: {voxel_world_pos}, 距離: {distance:.3f}")
                print(f"[voxel_carver][Debug]   差分: ({diff[0]:.3f}, {diff[1]:.3f}, {diff[2]:.3f})")
                setattr(self, f'_physx_voxel_check_{x}_{y}_{z}', True)

            if (abs(diff[0]) < effective_half_extents[0] + self._voxel_size/2.0 and
                abs(diff[1]) < effective_half_extents[1] + self._voxel_size/2.0 and
                abs(diff[2]) < effective_half_extents[2] + self._voxel_size/2.0):

                # 衝突検出 - ボクセルを削除
                voxels_to_remove.append((x, y, z))
                print(f"[voxel_carver][Debug] ★ 衝突検出! ボクセル({x},{y},{z})")

        # 削除処理（全ボクセルにコライダーがあるため、削除のみでOK）
        if voxels_to_remove:
            for (x, y, z) in voxels_to_remove:
                self._voxel_grid[x, y, z] = 0

                # コライダーを削除
                if (x, y, z) in self._voxel_colliders:
                    collider_path = self._voxel_colliders[(x, y, z)]
                    omni.kit.commands.execute('DeletePrims', paths=[collider_path])
                    del self._voxel_colliders[(x, y, z)]

                needs_update = True

            print(f"[voxel_carver][True] PhysX判定で{len(voxels_to_remove)}個のボクセルを削除しました")

        # メッシュ更新
        if needs_update:
            self.update_voxel_mesh()

    def _on_update(self, e):
        """フレーム毎に呼び出される更新処理"""
        if not self._is_simulating or not self._carver_prim or not self._voxel_mesh_prim:
            return

        # プリムの有効性を確認
        if not self._carver_prim.IsValid() or not self._voxel_mesh_prim.IsValid():
            print("[voxel_carver][Warning] CarverPrimまたはVoxelMeshPrimが無効です")
            return

        # 衝突検出方式に応じて処理を分岐
        if self._collision_method == "physx":
            self._check_physx_collision()
            return

        # 工具のワールド座標位置、半径、高さ、スケールを取得
        carver_xform = UsdGeom.Xformable(self._carver_prim)
        # 【重要】ワールド座標を取得（ローカル座標ではない）
        carver_world_transform = carver_xform.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
        carver_world_translation = carver_world_transform.GetRow3(3)

        # 四角柱（Cube）の基本パラメータを取得
        carver_size = self._carver_prim.GetAttribute("size").Get()
        if not carver_size:
            print(f"[voxel_carver][False] エラー: CarverToolのサイズが取得できません")
            return

        # ワールドトランスフォーム行列からスケールを取得
        # 各軸ベクトルの長さがスケール値
        x_vector_length = Gf.Vec3d(
            carver_world_transform[0][0],
            carver_world_transform[0][1],
            carver_world_transform[0][2]
        ).GetLength()

        y_vector_length = Gf.Vec3d(
            carver_world_transform[1][0],
            carver_world_transform[1][1],
            carver_world_transform[1][2]
        ).GetLength()

        z_vector_length = Gf.Vec3d(
            carver_world_transform[2][0],
            carver_world_transform[2][1],
            carver_world_transform[2][2]
        ).GetLength()

        # 四角柱の実効サイズを計算
        # Cubeのsizeは1辺の長さなので、半分のサイズにスケールを適用
        effective_half_width = (carver_size / 2.0) * x_vector_length
        effective_half_height = (carver_size / 2.0) * y_vector_length
        effective_half_depth = (carver_size / 2.0) * z_vector_length

        # ワールド→ローカル変換行列（四角柱のローカル座標系への変換用）
        carver_world_to_local = carver_world_transform.GetInverse()

        # デバッグ出力（初回のみ）
        if not hasattr(self, '_debug_printed'):
            # CarverToolのローカル座標を取得
            local_translate = None
            for op in carver_xform.GetOrderedXformOps():
                if op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
                    local_translate = op.Get()
                    break

            print(f"[voxel_carver][Debug] ========== CarverTool 座標情報 ==========")
            print(f"[voxel_carver][Debug] CarverTool ローカル座標（Property表示）: {local_translate}")
            print(f"[voxel_carver][Debug] CarverTool ワールド座標（計算使用）: {carver_world_translation}")
            print(f"[voxel_carver][Debug] ========== CarverTool 形状情報（四角柱判定）==========")
            print(f"[voxel_carver][Debug] CarverTool 基本サイズ: {carver_size}")
            print(f"[voxel_carver][Debug] CarverTool 実効半幅: {effective_half_width}, 実効半高: {effective_half_height}, 実効半奥行: {effective_half_depth}")
            print(f"[voxel_carver][Debug] CarverTool スケール（X/Y/Z軸長）: {x_vector_length:.3f}, {y_vector_length:.3f}, {z_vector_length:.3f}")
            print(f"[voxel_carver][Debug] ========== ボクセルグリッド情報 ==========")
            print(f"[voxel_carver][Debug] グリッド原点（ワールド）: {self._grid_origin}")
            print(f"[voxel_carver][Debug] グリッド解像度: {self._grid_dims}")
            print(f"[voxel_carver][Debug] ボクセルサイズ: {self._voxel_size}")
            print(f"[voxel_carver][Debug] ==========================================")
            self._debug_printed = True

        # CarverToolのワールド座標をVoxelMeshのローカル座標系に変換
        # VoxelMeshはTableのローカル座標原点に配置されているため、Tableのローカル座標に変換
        stage = omni.usd.get_context().get_stage()
        voxel_mesh_prim = stage.GetPrimAtPath(self._voxel_mesh_path)
        if voxel_mesh_prim and voxel_mesh_prim.IsValid():
            parent_prim = voxel_mesh_prim.GetParent()
            if parent_prim and parent_prim.IsValid():
                parent_xformable = UsdGeom.Xformable(parent_prim)
                parent_world_transform = parent_xformable.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
                parent_world_to_local = parent_world_transform.GetInverse()

                # CarverToolのワールド座標をTableのローカル座標に変換
                carver_local_pos = parent_world_to_local.Transform(carver_world_translation)
            else:
                carver_local_pos = carver_world_translation
        else:
            carver_local_pos = carver_world_translation

        # CarverToolの位置をボクセルグリッド座標系に変換
        carver_grid_pos = (np.array(carver_local_pos) - self._grid_origin) / self._voxel_size

        # 影響を受ける可能性のあるボクセルの範囲を計算（四角柱のバウンディングボックス）
        max_extent = max(effective_half_width, effective_half_height, effective_half_depth)
        max_extent_voxels = max_extent / self._voxel_size

        min_idx = np.floor(carver_grid_pos - max_extent_voxels).astype(int)
        max_idx = np.ceil(carver_grid_pos + max_extent_voxels).astype(int)

        # グリッドの範囲内に収める
        min_idx = np.maximum(min_idx, 0)
        max_idx = np.minimum(max_idx, self._grid_dims - 1)

        needs_update = False
        # 範囲内のボクセルを走査
        for x in range(min_idx[0], max_idx[0] + 1):
            for y in range(min_idx[1], max_idx[1] + 1):
                for z in range(min_idx[2], max_idx[2] + 1):
                    if self._voxel_grid[x, y, z] == 1:
                        # ボクセル中心のグリッドローカル座標（= Tableローカル座標）
                        voxel_center_table_local = self._grid_origin + Gf.Vec3d(x + 0.5, y + 0.5, z + 0.5) * self._voxel_size

                        # Tableローカル座標をワールド座標に変換
                        voxel_center_world = parent_world_transform.Transform(voxel_center_table_local)

                        # ボクセル中心を四角柱のローカル座標系に変換
                        voxel_local = carver_world_to_local.Transform(voxel_center_world)

                        # 四角柱判定：各軸で範囲内かチェック（AABB判定）
                        # ローカル座標系でX, Y, Z軸それぞれが範囲内なら削除
                        if (abs(voxel_local[0]) <= effective_half_width and
                            abs(voxel_local[1]) <= effective_half_height and
                            abs(voxel_local[2]) <= effective_half_depth):
                            self._voxel_grid[x, y, z] = 0

                            # 座標ベース判定モードではコライダーは使用しないが、
                            # PhysXモードから切り替えた場合のためにコライダーも削除
                            if (x, y, z) in self._voxel_colliders:
                                collider_path = self._voxel_colliders[(x, y, z)]
                                omni.kit.commands.execute('DeletePrims', paths=[collider_path])
                                del self._voxel_colliders[(x, y, z)]

                            needs_update = True

        # 変更があった場合のみメッシュを更新
        if needs_update:
            self.update_voxel_mesh()

    def update_voxel_mesh(self):
        """現在のボクセルグリッドからメッシュを生成・更新する"""
        stage = omni.usd.get_context().get_stage()

        # ボクセルの位置から頂点と面を計算
        # この実装は非常にシンプルで低速です。実用には最適化が必要です。

        vertices = []
        faces = []
        face_vertex_counts = []

        # 各ボクセルについて6つの面をチェック
        for x in range(self._grid_dims[0]):
            for y in range(self._grid_dims[1]):
                for z in range(self._grid_dims[2]):
                    if self._voxel_grid[x, y, z] == 1:
                        # 6方向の隣接ボクセルをチェックし、空間(0)と接している面にポリゴンを生成
                        pos = self._grid_origin + Gf.Vec3d(x, y, z) * self._voxel_size
                        s = self._voxel_size

                        # -X方向
                        if x == 0 or self._voxel_grid[x-1, y, z] == 0:
                            v_idx = len(vertices)
                            vertices.extend([pos + Gf.Vec3d(0, 0, 0), pos + Gf.Vec3d(0, s, 0), pos + Gf.Vec3d(0, s, s), pos + Gf.Vec3d(0, 0, s)])
                            faces.extend([v_idx, v_idx+1, v_idx+2, v_idx+3])
                            face_vertex_counts.append(4)
                        # +X方向
                        if x == self._grid_dims[0]-1 or self._voxel_grid[x+1, y, z] == 0:
                            v_idx = len(vertices)
                            vertices.extend([pos + Gf.Vec3d(s, 0, 0), pos + Gf.Vec3d(s, 0, s), pos + Gf.Vec3d(s, s, s), pos + Gf.Vec3d(s, s, 0)])
                            faces.extend([v_idx, v_idx+1, v_idx+2, v_idx+3])
                            face_vertex_counts.append(4)
                        # -Y方向
                        if y == 0 or self._voxel_grid[x, y-1, z] == 0:
                            v_idx = len(vertices)
                            vertices.extend([pos + Gf.Vec3d(0, 0, 0), pos + Gf.Vec3d(0, 0, s), pos + Gf.Vec3d(s, 0, s), pos + Gf.Vec3d(s, 0, 0)])
                            faces.extend([v_idx, v_idx+1, v_idx+2, v_idx+3])
                            face_vertex_counts.append(4)
                        # +Y方向
                        if y == self._grid_dims[1]-1 or self._voxel_grid[x, y+1, z] == 0:
                            v_idx = len(vertices)
                            vertices.extend([pos + Gf.Vec3d(0, s, 0), pos + Gf.Vec3d(s, s, 0), pos + Gf.Vec3d(s, s, s), pos + Gf.Vec3d(0, s, s)])
                            faces.extend([v_idx, v_idx+1, v_idx+2, v_idx+3])
                            face_vertex_counts.append(4)
                        # -Z方向
                        if z == 0 or self._voxel_grid[x, y, z-1] == 0:
                            v_idx = len(vertices)
                            vertices.extend([pos + Gf.Vec3d(0, 0, 0), pos + Gf.Vec3d(s, 0, 0), pos + Gf.Vec3d(s, s, 0), pos + Gf.Vec3d(0, s, 0)])
                            faces.extend([v_idx, v_idx+1, v_idx+2, v_idx+3])
                            face_vertex_counts.append(4)
                        # +Z方向
                        if z == self._grid_dims[2]-1 or self._voxel_grid[x, y, z+1] == 0:
                            v_idx = len(vertices)
                            vertices.extend([pos + Gf.Vec3d(0, 0, s), pos + Gf.Vec3d(0, s, s), pos + Gf.Vec3d(s, s, s), pos + Gf.Vec3d(s, 0, s)])
                            faces.extend([v_idx, v_idx+1, v_idx+2, v_idx+3])
                            face_vertex_counts.append(4)


        # メッシュプリムを作成または更新（Tableの子として配置）
        self._voxel_mesh_prim = stage.GetPrimAtPath(self._voxel_mesh_path)
        newly_created = False
        if not self._voxel_mesh_prim:
            self._voxel_mesh_prim = UsdGeom.Mesh.Define(stage, self._voxel_mesh_path)
            newly_created = True

        # VoxelMeshの頂点座標を親（Table）のローカル座標系に変換
        voxel_mesh_prim = self._voxel_mesh_prim.GetPrim()
        parent_prim = voxel_mesh_prim.GetParent()

        if parent_prim and parent_prim.IsValid():
            # 親（Table）のワールド→ローカル変換行列を取得
            parent_xformable = UsdGeom.Xformable(parent_prim)
            parent_world_transform = parent_xformable.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
            parent_world_to_local = parent_world_transform.GetInverse()

            # 親（Table）のワールド座標を取得
            parent_world_pos = parent_world_transform.GetRow3(3)

            # VoxelMeshをTableのローカル座標原点に配置するため、
            # 頂点座標はgrid_origin基準のまま使用（Workpiece中心オフセット不要）
            # これによりVoxelMeshはTableの原点付近に表示される
            vertices_local = vertices  # grid_origin基準のまま

            if newly_created:
                print(f"[voxel_carver][True] VoxelMeshを'{self._voxel_mesh_path}'に作成しました")
                print(f"[voxel_carver][Info] 親（Table）ワールド座標: {parent_world_pos}")
                print(f"[voxel_carver][Info] VoxelMeshはTableのローカル座標原点付近に配置")
                print(f"[voxel_carver][Info] グリッド原点: {self._grid_origin}")
                print(f"[voxel_carver][Info] Workpiece中心（ワールド座標）: {self._workpiece_center}")
        else:
            # 親がない場合はワールド座標そのまま（グリッド座標+Workpiece中心）
            vertices_world = []
            for vertex_grid in vertices:
                vertex_world = vertex_grid + self._workpiece_center
                vertices_world.append(vertex_world)
            vertices = vertices_world

            if newly_created:
                print(f"[voxel_carver][True] VoxelMeshを'{self._voxel_mesh_path}'に作成しました（ワールド座標系）")

        mesh = UsdGeom.Mesh(self._voxel_mesh_prim)
        mesh.GetPointsAttr().Set(vertices)
        mesh.GetFaceVertexCountsAttr().Set(face_vertex_counts)
        mesh.GetFaceVertexIndicesAttr().Set(faces)
        mesh.GetSubdivisionSchemeAttr().Set(UsdGeom.Tokens.none)

    def move_to_table(self):
        """WorkpieceをTableの下に移動（VoxelMeshは既にTableの子として配置済み）"""
        try:
            stage = omni.usd.get_context().get_stage()
            table_prim = stage.GetPrimAtPath(DEFAULT_TABLE_PATH)

            if not table_prim or not table_prim.IsValid():
                print(f"[voxel_carver][False] エラー: Tableが見つかりません: {DEFAULT_TABLE_PATH}")
                return

            # Workpieceのみを移動
            source_path = self._workpiece_prim_path
            target_path = f"{DEFAULT_TABLE_PATH}/Workpiece"

            source_prim = stage.GetPrimAtPath(source_path)
            if source_prim and source_prim.IsValid():
                # Workpieceのワールド座標を取得
                workpiece_xformable = UsdGeom.Xformable(source_prim)
                world_transform = workpiece_xformable.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
                world_pos = world_transform.GetRow3(3)

                # USDコマンドで移動（親子関係を変更）
                omni.kit.commands.execute('MovePrim',
                    path_from=source_path,
                    path_to=target_path)
                print(f"[voxel_carver][True] '{source_path}' を '{target_path}' に移動しました。")

                # パスを更新
                self._workpiece_prim_path = target_path

                print("[voxel_carver][True] WorkpieceをTableの下に移動しました。")
                print("[voxel_carver][Info] VoxelMeshは既にTableの子として配置されています。")
            else:
                print(f"[voxel_carver][Warning] Workpieceが見つかりません: {source_path}")

        except Exception as e:
            print(f"[voxel_carver][False] 移動中にエラーが発生しました: {e}", file=sys.stderr)
            traceback.print_exc()

    def on_reset(self):
        """シミュレーションの状態をリセットする"""
        self.on_stop_simulation()

        # プリムを削除
        paths_to_delete = [self._voxel_mesh_path, self._workpiece_prim_path, self._carver_prim_path]

        # PhysXコライダーも削除（VoxelMeshの子として配置）
        # VoxelMesh削除時に自動的に削除されるが、念のため記録
        if self._voxel_colliders:
            print(f"[voxel_carver][Info] VoxelCollidersはVoxelMeshと共に削除されます")
            self._voxel_colliders = {}

        omni.kit.commands.execute('DeletePrims', paths=paths_to_delete)

        self._voxel_grid = None
        self._workpiece_prim = None
        self._carver_prim = None
        self._voxel_mesh_prim = None

        # デバッグフラグもリセット
        debug_attrs = [attr for attr in dir(self) if attr.startswith('_debug_') or attr.startswith('_physx_')]
        for attr in debug_attrs:
            if hasattr(self, attr):
                delattr(self, attr)

        print("[voxel_carver][True] シミュレーションをリセットしました。")