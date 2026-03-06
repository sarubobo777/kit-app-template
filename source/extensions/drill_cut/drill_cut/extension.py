# 必要なインポート
import omni.ext
import omni.usd
import carb
import asyncio
import numpy as np
import trimesh
import trimesh.repair
import omni.ui as ui
import omni.kit.commands
from pxr import Usd, Gf, UsdGeom, Sdf

EXT_PREFIX = "[my_ext][Boolean]"

# --- Helper Functions (変更なし) ---

def delete_prim(path: str):
    stage = omni.usd.get_context().get_stage()
    prim = stage.GetPrimAtPath(Sdf.Path(path))
    if prim.IsValid():
        stage.RemovePrim(Sdf.Path(path))

def make_mesh_from_prim(prim):
    prim_type = prim.GetTypeName()
    xform = UsdGeom.Xformable(prim)
    translate = Gf.Vec3d(0,0,0)
    scale = Gf.Vec3f(1,1,1)
    rot_xyz = Gf.Vec3f(0,0,0)

    for op in xform.GetOrderedXformOps():
        if op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
            translate = op.Get()
        elif op.GetOpType() == UsdGeom.XformOp.TypeScale:
            scale = op.Get()
        elif op.GetOpType() == UsdGeom.XformOp.TypeRotateXYZ:
            rot_xyz = op.Get()

    rx, ry, rz = np.deg2rad([rot_xyz[0], rot_xyz[1], rot_xyz[2]])
    Rx = np.array([[1,0,0],[0,np.cos(rx),-np.sin(rx)],[0,np.sin(rx),np.cos(rx)]])
    Ry = np.array([[np.cos(ry),0,np.sin(ry)],[0,1,0],[-np.sin(ry),0,np.cos(ry)]])
    Rz = np.array([[np.cos(rz),-np.sin(rz),0],[np.sin(rz),np.cos(rz),0],[0,0,1]])
    R = Rz @ Ry @ Rx

    T = np.eye(4)
    T[:3, :3] = R @ np.diag(scale)
    T[:3, 3] = translate

    if prim_type == "Cube":
        size = UsdGeom.Cube(prim).GetSizeAttr().Get()
        mesh = trimesh.creation.box(extents=[size*scale[0], size*scale[1], size*scale[2]])
        mesh.apply_transform(T)
        return mesh

    elif prim_type == "Mesh":
        geom = UsdGeom.Mesh(prim)
        points = geom.GetPointsAttr().Get()
        indices = geom.GetFaceVertexIndicesAttr().Get()
        counts = geom.GetFaceVertexCountsAttr().Get()

        if not points or not indices or not counts:
            return None

        faces = []
        idx = 0
        for c in counts:
            if c == 3:
                faces.append([indices[idx], indices[idx+1], indices[idx+2]])
            idx += c

        if not faces:
            return None

        vertices = np.array([[v[0], v[1], v[2]] for v in points])
        mesh = trimesh.Trimesh(vertices=vertices, faces=faces)
        mesh.apply_transform(T)
        return mesh

    else:
        raise NotImplementedError(f"未対応のプリムタイプ: {prim_type}")

def build_mesh_prim_from_trimesh(stage, path, mesh: trimesh.Trimesh):
    delete_prim(path)
    prim = UsdGeom.Mesh.Define(stage, Sdf.Path(path))
    prim.CreatePointsAttr([Gf.Vec3f(*v) for v in mesh.vertices])
    prim.CreateFaceVertexCountsAttr([3] * len(mesh.faces))
    prim.CreateFaceVertexIndicesAttr([int(i) for f in mesh.faces for i in f])

    UsdGeom.XformCommonAPI(prim).SetTranslate(Gf.Vec3d(0, 0, 0))
    UsdGeom.XformCommonAPI(prim).SetScale(Gf.Vec3f(1, 1, 1))
    carb.log_info(f"{EXT_PREFIX} New mesh has {len(mesh.vertices)} vertices and {len(mesh.faces)} faces.")
    carb.log_info(f"{EXT_PREFIX} New mesh bbox: {mesh.bounds}")
    print_translate(stage, path)
    return prim

def print_translate(stage, prim_path):
    prim = stage.GetPrimAtPath(prim_path)
    xform = UsdGeom.Xformable(prim)
    translate = Gf.Vec3d(0, 0, 0)
    for op in xform.GetOrderedXformOps():
            if op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
                translate = op.Get()
                break

    translate = Gf.Vec3d(translate[0], translate[1], translate[2])
    print(f"{EXT_PREFIX} {prim_path} translate is ,{translate[0]},{translate[1]},{translate[2]}")

def get_boundary_edges(mesh: trimesh.Trimesh):
    all_edges = mesh.edges_sorted
    boundary = trimesh.grouping.group_rows(all_edges, require_count=1)
    return all_edges[boundary]

def pymeshfix_repair(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    try:
        import pymeshfix
    except ImportError as e:
        carb.log_warn(f"{EXT_PREFIX} pymeshfix がインポートできません: {e}")
        return mesh
    try:
        v = mesh.vertices.copy()
        f = mesh.faces.copy()
        meshfix = pymeshfix.MeshFix(v, f)
        meshfix.repair()
        v2 = meshfix.v
        f2 = meshfix.f
        mesh2 = trimesh.Trimesh(vertices=v2, faces=f2, process=True)
        carb.log_info(f"{EXT_PREFIX} pymeshfix による修復を適用しました。")
        return mesh2
    except Exception as e:
        carb.log_warn(f"{EXT_PREFIX} pymeshfix 修復中に例外発生: {e}")
        return mesh

def robust_repair(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    mesh.remove_degenerate_faces()
    mesh.remove_duplicate_faces()
    mesh.remove_infinite_values()
    mesh.remove_unreferenced_vertices()
    trimesh.repair.fill_holes(mesh)

    boundary_edges = get_boundary_edges(mesh)
    if len(boundary_edges) > 0:
        carb.log_warn(f"{EXT_PREFIX} 境界エッジを検出しました: {len(boundary_edges)}本")
        mesh.fix_normals()

    # pymeshfix修復（使わない場合は削除してもよい）
    mesh = pymeshfix_repair(mesh)

    # 修復後の情報をログ出力
    if not mesh.is_watertight:
        b2 = get_boundary_edges(mesh)
        carb.log_warn(f"{EXT_PREFIX} 修復後も watertight ではありません。境界エッジ数: {len(b2)}本")
    else:
        carb.log_info(f"{EXT_PREFIX} 修復後、メッシュは watertight です。")

    # volume チェックと反転の試行
    carb.log_info(f"{EXT_PREFIX} メッシュのvolume: {mesh.volume}")
    if mesh.volume < 0:
        carb.log_warn(f"{EXT_PREFIX} メッシュのvolumeがゼロまたは負です。修復に失敗した可能性があります。反転を試みます。")
        mesh.invert()
        carb.log_info(f"{EXT_PREFIX} 反転後のvolume: {mesh.volume}, is_volume: {mesh.is_volume}")

    try:
        trimesh.repair.fix_inversion(mesh)
        carb.log_info(f"{EXT_PREFIX} fix_inversion を適用しました。volume = {mesh.volume}")
    except Exception as e:
        carb.log_warn(f"{EXT_PREFIX} fix_inversion 実行中に例外: {e}")

    return mesh

# --- ここから下の boolean_loop が修正された部分 ---

async def boolean_loop():
    stage = omni.usd.get_context().get_stage()
    while not stage or not stage.GetPrimAtPath("/World"):
        await asyncio.sleep(0.1)
        stage = omni.usd.get_context().get_stage()

    # シーンのセットアップ
    delete_prim("/World/Metal")
    metal = UsdGeom.Cube.Define(stage, Sdf.Path("/World/Metal"))
    metal.CreateSizeAttr(50.0)
    UsdGeom.XformCommonAPI(metal).SetTranslate(Gf.Vec3d(0, 70, 0))
    UsdGeom.XformCommonAPI(metal).SetRotate(Gf.Vec3f(0, 0, 0))
    carb.log_info(f"{EXT_PREFIX} Metalを生成しました。")

    delete_prim("/World/Drill")
    drill = UsdGeom.Cube.Define(stage, Sdf.Path("/World/Drill"))
    drill.CreateSizeAttr(15.0)
    UsdGeom.XformCommonAPI(drill).SetTranslate(Gf.Vec3d(-25, 90, 0))
    UsdGeom.XformCommonAPI(drill).SetRotate(Gf.Vec3f(0, 0, 0))
    carb.log_info(f"{EXT_PREFIX} Drillを生成しました。")

    metal_backup = None

    while True:
        await asyncio.sleep(2.0)

        # 1. ワールド座標のメッシュを取得
        mesh1 = make_mesh_from_prim(stage.GetPrimAtPath("/World/Metal"))
        mesh2 = make_mesh_from_prim(stage.GetPrimAtPath("/World/Drill"))

        if not mesh1 or not mesh2:
            carb.log_warn(f"{EXT_PREFIX} Meshの生成に失敗しました。")
            continue

        # 2. 入力メッシュがwatertightであることを確認
        if not mesh1.is_watertight:
            carb.log_warn(f"{EXT_PREFIX} Metalがwatertightではありません。スキップします。")
            if metal_backup:
                build_mesh_prim_from_trimesh(stage, "/World/Metal", metal_backup.copy())
            continue

        if not mesh2.is_watertight:
            carb.log_warn(f"{EXT_PREFIX} Drillがwatertightではありません。スキップします。")
            continue

        # 3. ブール演算を実行する
        try:
            # === ここからが重要な修正点 ===

            # 3-1. 正しいブール演算の呼び出し
            #      - mesh1.rezero() は削除
            #      - mesh1.difference(mesh2, ...) の形に修正
            carb.log_info(f"{EXT_PREFIX} ブール演算を実行します。")
            result = mesh1.difference(mesh2, engine='blender')

            # 3-2. 結果の検証
            if result.is_empty:
                carb.log_warn(f"{EXT_PREFIX} ブール演算の結果が空になりました。何も変化はありません。")
                continue # 次のループへ

            if len(result.faces) == len(mesh1.faces):
                carb.log_warn(f"{EXT_PREFIX} ブール演算後も面の数が変わりません。交差していない可能性があります。")
                continue # 次のループへ

            carb.log_info(f"{EXT_PREFIX} ブール演算が完了し、新しいジオメトリが生成されました。")

            # 3-3. 演算後の結果に対してのみ、修復処理を適用
            carb.log_info(f"{EXT_PREFIX} 演算結果の修復を試みます...")
            repaired_result = robust_repair(result)

            # 3-4. 修復後の最終チェック
            if not repaired_result.is_watertight:
                carb.log_warn(f"{EXT_PREFIX} 結果のメッシュを修復しましたが、watertightになりませんでした。更新をスキップします。")
                # 失敗した場合は、前回の状態に戻す
                if metal_backup:
                    build_mesh_prim_from_trimesh(stage, "/World/Metal", metal_backup.copy())
                continue

            # 3-5. 成功した場合のみ、メッシュを更新し、バックアップを保存
            carb.log_info(f"{EXT_PREFIX} 修復に成功。Metalメッシュを更新します。")
            build_mesh_prim_from_trimesh(stage, "/World/Metal", repaired_result)
            metal_backup = repaired_result.copy()

        except Exception as e:
            carb.log_error(f"{EXT_PREFIX} Boolean演算中にエラーが発生しました: {e}")
            if metal_backup:
                build_mesh_prim_from_trimesh(stage, "/World/Metal", metal_backup.copy())

# --- Extensionクラス (変更なし) ---
class Extension(omni.ext.IExt):
    def on_startup(self, ext_id):
        carb.log_info(f"{EXT_PREFIX} Extension startup")
        self._window = ui.Window("remake", width=300, height=200)
        with self._window.frame:
            with ui.VStack():
                    self._button = ui.Button("Remake", clicked_fn=self.on_button_click)
        asyncio.ensure_future(boolean_loop())

    def on_button_click(self):
        stage = omni.usd.get_context().get_stage()
        delete_prim("/World/Metal")
        metal = UsdGeom.Cube.Define(stage, Sdf.Path("/World/Metal"))
        metal.CreateSizeAttr(50.0)
        UsdGeom.XformCommonAPI(metal).SetTranslate(Gf.Vec3d(0, 70, 0))
        UsdGeom.XformCommonAPI(metal).SetRotate(Gf.Vec3f(0, 0, 0))
        print_translate(stage, "/World/Metal")
        carb.log_info(f"{EXT_PREFIX} Metalをリメイクしました。")

    def on_shutdown(self):
        carb.log_info(f"{EXT_PREFIX} Extension shutdown")
        if self._window:
            self._window.destroy()
            self._window = None