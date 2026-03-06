"""
Surface Deformableとして明示的に適用するスクリプト
Triangle MeshをSurface Deformableとして設定（ケーブルに最適）
"""

import omni.usd
from pxr import Usd, UsdGeom, UsdPhysics, UsdShade, PhysxSchema, Sdf, Gf

def apply_surface_deformable():
    """Surface DeformableをCableに適用"""

    stage = omni.usd.get_context().get_stage()

    if not stage:
        print("❌ Stage not loaded!")
        return False

    cable_path = "/World/New_MillingMachine/Pulag/Cable"

    print("=" * 70)
    print("Surface Deformable 適用スクリプト")
    print("=" * 70)
    print("\nSurface Deformable: Triangle Meshを使用する薄い変形体")
    print("用途: ケーブル、布、紙など\n")

    cable_prim = stage.GetPrimAtPath(cable_path)

    if not cable_prim or not cable_prim.IsValid():
        print(f"❌ Prim not found: {cable_path}")
        return False

    # メッシュプリムを探す
    target_mesh_prim = None

    if cable_prim.IsA(UsdGeom.Mesh):
        target_mesh_prim = cable_prim
    else:
        def find_first_mesh(prim):
            if prim.IsA(UsdGeom.Mesh):
                return prim
            for child in prim.GetChildren():
                result = find_first_mesh(child)
                if result:
                    return result
            return None

        target_mesh_prim = find_first_mesh(cable_prim)

    if not target_mesh_prim:
        print(f"❌ Mesh not found")
        return False

    print(f"✅ Target: {target_mesh_prim.GetPath()}")

    # メッシュの検証
    mesh_geom = UsdGeom.Mesh(target_mesh_prim)
    points = mesh_geom.GetPointsAttr().Get()

    if not points or len(points) == 0:
        print(f"❌ メッシュに頂点データがありません")
        return False

    print(f"  頂点数: {len(points)}")

    face_counts = mesh_geom.GetFaceVertexCountsAttr().Get()
    if face_counts:
        is_triangle = all(count == 3 for count in face_counts)
        print(f"  面数: {len(face_counts)}")
        print(f"  Triangle Mesh: {is_triangle}")

        if not is_triangle:
            print("\n⚠️  警告: Triangle Meshではありません")
            print("   Surface Deformableは Triangle Mesh を推奨します")
            print("   ⚠️  メッシュをTriangle化する必要があります")
            print("   triangulate_cable_mesh.py を先に実行してください")
            return False

    # 既存のAPIを確認・削除
    print("\n【既存API確認】")

    if target_mesh_prim.HasAPI(UsdPhysics.RigidBodyAPI):
        print("  RigidBodyAPI を削除中...")
        target_mesh_prim.RemoveAPI(UsdPhysics.RigidBodyAPI)
        print("  ✅ 削除完了")

    if target_mesh_prim.HasAPI(PhysxSchema.PhysxDeformableBodyAPI):
        print("  ⚠️  既存のPhysxDeformableBodyAPIを検出")
        print("  再適用します...")

    # 適用開始
    print("\n【Surface Deformable 適用】")

    # ステップ1: PhysxDeformableBodyAPI
    print("\n[1] PhysxDeformableBodyAPI 適用中...")
    try:
        deformable_api = PhysxSchema.PhysxDeformableBodyAPI.Apply(target_mesh_prim)
        print("  ✅ API適用完了")
    except Exception as e:
        print(f"  ❌ API適用エラー: {e}")
        return False

    # ステップ2: Surface Deformable用の設定
    print("\n[2] Surface Deformable 設定中...")

    # 重要: simulation mesh を triangle に設定
    try:
        # Simulation Mesh は元のTriangle Meshを使用（Tetmeshに変換しない）
        if hasattr(deformable_api, 'CreateSimulationMeshResolutionAttr'):
            # 0 = Triangle Mesh をそのまま使用（Tetmesh変換なし）
            deformable_api.CreateSimulationMeshResolutionAttr().Set(0)
            print("  ✅ SimulationMeshResolution: 0 (Triangle Mesh)")
        else:
            print("  ⚠️  SimulationMeshResolution属性なし（バージョンにより非対応）")
    except Exception as e:
        print(f"  ⚠️  SimulationMeshResolution設定エラー: {e}")

    # Collision Simplification を無効化（正確な衝突検知）
    try:
        if hasattr(deformable_api, 'CreateCollisionSimplificationAttr'):
            deformable_api.CreateCollisionSimplificationAttr().Set(False)
            print("  ✅ CollisionSimplification: False")
    except Exception as e:
        print(f"  ⚠️  CollisionSimplification設定スキップ: {e}")

    # Solver iterations（安定性向上）
    try:
        if hasattr(deformable_api, 'CreateSolverPositionIterationCountAttr'):
            deformable_api.CreateSolverPositionIterationCountAttr().Set(20)
            print("  ✅ SolverPositionIterationCount: 20")
    except Exception as e:
        pass

    # ステップ3: CollisionAPI
    print("\n[3] CollisionAPI 適用中...")
    if not target_mesh_prim.HasAPI(UsdPhysics.CollisionAPI):
        UsdPhysics.CollisionAPI.Apply(target_mesh_prim)
        print("  ✅ CollisionAPI適用完了")
    else:
        print("  既に適用済み")

    # ステップ4: Deformable Material
    print("\n[4] Deformable Material 作成中...")

    material_path = target_mesh_prim.GetPath().AppendChild("SurfaceDeformableMaterial")

    # 既存のMaterialを削除
    if stage.GetPrimAtPath(material_path).IsValid():
        stage.RemovePrim(material_path)
        print("  既存のMaterialを削除")

    material_prim = stage.DefinePrim(material_path, "Material")
    material_api = PhysxSchema.PhysxDeformableBodyMaterialAPI.Apply(material_prim)

    # Surface Deformable（ケーブル）用のマテリアル設定
    print("  Material設定中...")

    # Young's Modulus (剛性)
    try:
        material_api.CreateYoungsModulusAttr().Set(5e6)
        print("    ✅ Young's Modulus: 5e6")
    except Exception as e:
        print(f"    ⚠️  Young's Modulus設定エラー: {e}")

    # Poisson's Ratio (体積保存)
    try:
        material_api.CreatePoissonsRatioAttr().Set(0.4)
        print("    ✅ Poisson's Ratio: 0.4")
    except Exception as e:
        print(f"    ⚠️  Poisson's Ratio設定エラー: {e}")

    # Dynamic Friction (摩擦)
    try:
        material_api.CreateDynamicFrictionAttr().Set(0.6)
        print("    ✅ Dynamic Friction: 0.6")
    except Exception as e:
        print(f"    ⚠️  Dynamic Friction設定エラー: {e}")

    # Damping (減衰) - バージョンによっては非対応
    try:
        if hasattr(material_api, 'CreateDampingAttr'):
            material_api.CreateDampingAttr().Set(0.15)
            print("    ✅ Damping: 0.15")
        else:
            print("    ⚠️  Damping属性なし（バージョンにより非対応）")
    except Exception as e:
        print(f"    ⚠️  Damping設定エラー: {e}")

    # Density (密度) - バージョンによっては必要
    try:
        if hasattr(material_api, 'CreateDensityAttr'):
            material_api.CreateDensityAttr().Set(1000.0)
            print("    ✅ Density: 1000.0")
    except Exception as e:
        pass

    print("  ✅ Material作成完了")

    # ステップ5: Materialバインド
    print("\n[5] Material バインド中...")
    try:
        # UsdShade.MaterialBindingAPI を使用
        binding_api = UsdShade.MaterialBindingAPI.Apply(target_mesh_prim)

        # Physics Materialとしてバインド
        binding_api.Bind(UsdShade.Material(material_prim), UsdShade.Tokens.physics)
        print("  ✅ Material バインド完了")
    except Exception as e:
        print(f"  ⚠️  Material バインドエラー: {e}")
        print("  代替方法を試します...")

        # 代替: 直接リレーションシップを作成
        try:
            material_rel = target_mesh_prim.CreateRelationship("physics:material", False)
            material_rel.SetTargets([material_path])
            print("  ✅ Material バインド完了 (代替方法)")
        except Exception as e2:
            print(f"  ⚠️  代替バインドもエラー: {e2}")

    # 完了
    print("\n" + "=" * 70)
    print("🎉 Surface Deformable 適用完了！")
    print("=" * 70)

    print(f"\n設定内容:")
    print(f"  対象: {target_mesh_prim.GetPath()}")
    print(f"  タイプ: Surface Deformable (Triangle Mesh)")
    print(f"  Material: {material_path}")

    print(f"\n次のステップ:")
    print(f"  1. Playボタンを押してシミュレーション開始")
    print(f"  2. ケーブルが柔軟に動くか確認")
    print(f"\n⚠️  重要な注意:")
    print(f"  - Surface Deformableは重力の影響を受けます")
    print(f"  - 端点を固定したい場合は Attachment を追加")
    print(f"  - 動かない場合はマテリアルパラメータを調整")

    print(f"\nパラメータ調整のヒント:")
    print(f"  - 柔らかくする: Young's Modulus を下げる (1e6など)")
    print(f"  - 硬くする: Young's Modulus を上げる (1e7など)")
    print(f"  - 早く静止: Damping を上げる (0.3など)")

    return True

if __name__ == "__main__":
    apply_surface_deformable()
