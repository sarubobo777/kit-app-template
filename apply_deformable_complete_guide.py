"""
Deformable Bodies (Beta) 完全適用ガイド
全ステップを順番に実行して、Cableに変形可能なボディを適用
"""

import omni.usd
from pxr import Usd, UsdGeom, UsdPhysics, UsdShade, PhysxSchema, Sdf, Vt
import carb.settings

def check_prerequisites():
    """前提条件チェック"""
    print("=" * 70)
    print("ステップ1: 前提条件チェック")
    print("=" * 70)

    stage = omni.usd.get_context().get_stage()
    if not stage:
        print("❌ Stage not loaded!")
        return False

    cable_path = "/World/New_MillingMachine/Pulag/Cable"
    cable_prim = stage.GetPrimAtPath(cable_path)

    if not cable_prim or not cable_prim.IsValid():
        print(f"❌ Cable not found: {cable_path}")
        return False

    print(f"✅ Cable found: {cable_path}")
    return True

def check_beta_features():
    """Beta機能の確認と有効化"""
    print("\n" + "=" * 70)
    print("ステップ2: Physics Beta機能確認")
    print("=" * 70)

    settings = carb.settings.get_settings()

    beta_settings_paths = [
        "/physics/developmentMode",
        "/physics/enableBetaFeatures",
        "/app/physics/enableBetaFeatures",
        "/persistent/physics/betaFeaturesEnabled",
    ]

    beta_enabled = False
    for path in beta_settings_paths:
        value = settings.get(path)
        if value is not None:
            print(f"  {path}: {value}")
            if value:
                beta_enabled = True

    if not beta_enabled:
        print("\n⚠️  Beta機能が有効になっていません")
        print("   enable_beta_physics.py を実行して、アプリを再起動してください")
        return False

    print("\n✅ Beta機能が有効です")
    return True

def remove_existing_deformable():
    """既存のDeformable Body設定を削除"""
    print("\n" + "=" * 70)
    print("ステップ3: 既存のDeformable Body設定削除")
    print("=" * 70)

    stage = omni.usd.get_context().get_stage()
    cable_path = "/World/New_MillingMachine/Pulag/Cable"
    cable_prim = stage.GetPrimAtPath(cable_path)

    # メッシュを探す
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
        print("❌ Mesh not found")
        return False

    print(f"✅ Target: {target_mesh_prim.GetPath()}")

    # PhysxDeformableBodyAPIを削除
    if target_mesh_prim.HasAPI(PhysxSchema.PhysxDeformableBodyAPI):
        try:
            target_mesh_prim.RemoveAPI(PhysxSchema.PhysxDeformableBodyAPI)
            print("  ✅ PhysxDeformableBodyAPI 削除")
        except Exception as e:
            print(f"  ⚠️  削除エラー: {e}")
    else:
        print("  既存のPhysxDeformableBodyAPIなし")

    # RigidBodyAPIを削除
    if target_mesh_prim.HasAPI(UsdPhysics.RigidBodyAPI):
        target_mesh_prim.RemoveAPI(UsdPhysics.RigidBodyAPI)
        print("  ✅ RigidBodyAPI 削除")

    # Deformable Material削除
    material_path = target_mesh_prim.GetPath().AppendChild("DeformableMaterial")
    if stage.GetPrimAtPath(material_path).IsValid():
        stage.RemovePrim(material_path)
        print("  ✅ DeformableMaterial 削除")

    return True

def triangulate_mesh():
    """メッシュをTriangle化"""
    print("\n" + "=" * 70)
    print("ステップ4: メッシュTriangle化")
    print("=" * 70)

    stage = omni.usd.get_context().get_stage()
    cable_path = "/World/New_MillingMachine/Pulag/Cable"
    cable_prim = stage.GetPrimAtPath(cable_path)

    # メッシュを探す
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
        print("❌ Mesh not found")
        return False

    mesh_geom = UsdGeom.Mesh(target_mesh_prim)
    points = mesh_geom.GetPointsAttr().Get()
    face_vertex_counts = mesh_geom.GetFaceVertexCountsAttr().Get()
    face_vertex_indices = mesh_geom.GetFaceVertexIndicesAttr().Get()

    if not points or not face_vertex_counts or not face_vertex_indices:
        print("❌ メッシュデータが不完全です")
        return False

    print(f"  頂点数: {len(points)}")
    print(f"  面数: {len(face_vertex_counts)}")

    # Triangle化チェック
    is_triangle = all(count == 3 for count in face_vertex_counts)
    if is_triangle:
        print("\n✅ すでにTriangle Meshです")
        return True

    # Triangle化処理
    print("\n  Quad → Triangle 変換中...")

    new_face_vertex_counts = []
    new_face_vertex_indices = []
    current_index = 0

    for face_count in face_vertex_counts:
        face_indices = [face_vertex_indices[current_index + i] for i in range(face_count)]

        if face_count == 3:
            new_face_vertex_counts.append(3)
            new_face_vertex_indices.extend(face_indices)
        elif face_count == 4:
            # Quad → 2 Triangles
            new_face_vertex_counts.append(3)
            new_face_vertex_counts.append(3)
            new_face_vertex_indices.extend([face_indices[0], face_indices[1], face_indices[2]])
            new_face_vertex_indices.extend([face_indices[0], face_indices[2], face_indices[3]])
        else:
            # N-gon → Fan triangulation
            for i in range(1, face_count - 1):
                new_face_vertex_counts.append(3)
                new_face_vertex_indices.extend([face_indices[0], face_indices[i], face_indices[i + 1]])

        current_index += face_count

    # 設定
    mesh_geom.GetFaceVertexCountsAttr().Set(Vt.IntArray(new_face_vertex_counts))
    mesh_geom.GetFaceVertexIndicesAttr().Set(Vt.IntArray(new_face_vertex_indices))

    print(f"  ✅ Triangle化完了: {len(new_face_vertex_counts)} 面")
    return True

def apply_surface_deformable():
    """Surface Deformableを適用"""
    print("\n" + "=" * 70)
    print("ステップ5: Surface Deformable適用")
    print("=" * 70)

    stage = omni.usd.get_context().get_stage()
    cable_path = "/World/New_MillingMachine/Pulag/Cable"
    cable_prim = stage.GetPrimAtPath(cable_path)

    # メッシュを探す
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
        print("❌ Mesh not found")
        return False

    print(f"✅ Target: {target_mesh_prim.GetPath()}")

    # PhysxDeformableBodyAPI適用
    print("\n[1] PhysxDeformableBodyAPI 適用中...")
    try:
        deformable_api = PhysxSchema.PhysxDeformableBodyAPI.Apply(target_mesh_prim)
        print("  ✅ API適用完了")
    except Exception as e:
        print(f"  ❌ API適用エラー: {e}")
        return False

    # Surface Deformable設定
    print("\n[2] Surface Deformable 設定中...")

    # SimulationMeshResolution = 0 (Triangle Mesh使用)
    try:
        if hasattr(deformable_api, 'CreateSimulationMeshResolutionAttr'):
            deformable_api.CreateSimulationMeshResolutionAttr().Set(0)
            print("  ✅ SimulationMeshResolution: 0 (Triangle Mesh)")
        else:
            print("  ⚠️  SimulationMeshResolution属性なし")
    except Exception as e:
        print(f"  ⚠️  設定エラー: {e}")

    # CollisionAPI適用
    print("\n[3] CollisionAPI 適用中...")
    if not target_mesh_prim.HasAPI(UsdPhysics.CollisionAPI):
        UsdPhysics.CollisionAPI.Apply(target_mesh_prim)
        print("  ✅ CollisionAPI適用完了")
    else:
        print("  既に適用済み")

    # Deformable Material作成
    print("\n[4] Deformable Material 作成中...")
    material_path = target_mesh_prim.GetPath().AppendChild("SurfaceDeformableMaterial")

    # 既存削除
    if stage.GetPrimAtPath(material_path).IsValid():
        stage.RemovePrim(material_path)

    material_prim = stage.DefinePrim(material_path, "Material")
    material_api = PhysxSchema.PhysxDeformableBodyMaterialAPI.Apply(material_prim)

    # 基本的な属性を設定（バージョン互換性を考慮）
    try:
        material_api.CreateYoungsModulusAttr().Set(5e6)
        print("    Young's Modulus: 5e6")
    except Exception as e:
        print(f"    ⚠️  Young's Modulus設定スキップ: {e}")

    try:
        material_api.CreatePoissonsRatioAttr().Set(0.4)
        print("    Poisson's Ratio: 0.4")
    except Exception as e:
        print(f"    ⚠️  Poisson's Ratio設定スキップ: {e}")

    try:
        material_api.CreateDynamicFrictionAttr().Set(0.6)
        print("    Dynamic Friction: 0.6")
    except Exception as e:
        print(f"    ⚠️  Dynamic Friction設定スキップ: {e}")

    # Dampingは一部バージョンで非対応
    try:
        if hasattr(material_api, 'CreateDampingAttr'):
            material_api.CreateDampingAttr().Set(0.15)
            print("    Damping: 0.15")
    except Exception as e:
        print(f"    ⚠️  Damping設定スキップ: {e}")

    # Densityは一部バージョンで必要
    try:
        if hasattr(material_api, 'CreateDensityAttr'):
            material_api.CreateDensityAttr().Set(1000.0)
            print("    Density: 1000.0")
    except Exception as e:
        pass

    print("  ✅ Material作成完了")

    # Materialバインド
    print("\n[5] Material バインド中...")
    try:
        # UsdShade.MaterialBindingAPI を使用
        binding_api = UsdShade.MaterialBindingAPI.Apply(target_mesh_prim)

        # Physics Materialとしてバインド
        # PhysicsMaterialPurpose を使用
        binding_api.Bind(UsdShade.Material(material_prim), UsdShade.Tokens.physics)
        print("  ✅ Material バインド完了")
    except Exception as e:
        print(f"  ⚠️  Material バインドエラー: {e}")
        print("  代替方法を試します...")

        # 代替: 直接リレーションシップを作成
        try:
            if target_mesh_prim.HasAPI(UsdPhysics.CollisionAPI):
                collision_api = UsdPhysics.CollisionAPI(target_mesh_prim)
                # physics:material リレーションシップを作成
                material_rel = target_mesh_prim.CreateRelationship("physics:material", False)
                material_rel.SetTargets([material_path])
                print("  ✅ Material バインド完了 (代替方法)")
        except Exception as e2:
            print(f"  ⚠️  代替バインドもエラー: {e2}")

    return True

def main():
    """メイン処理 - 全ステップを実行"""
    print("\n" + "=" * 70)
    print("Deformable Bodies (Beta) 完全適用ガイド")
    print("=" * 70)
    print("\nCableに変形可能なボディを適用します\n")

    # ステップ1: 前提条件チェック
    if not check_prerequisites():
        print("\n❌ 前提条件チェック失敗")
        return False

    # ステップ2: Beta機能確認
    if not check_beta_features():
        print("\n⚠️  Beta機能が無効です")
        print("\n【解決方法】")
        print("  1. enable_beta_physics.py を実行")
        print("  2. アプリケーションを再起動")
        print("  3. 再度このスクリプトを実行")
        return False

    # ステップ3: 既存設定削除
    if not remove_existing_deformable():
        print("\n❌ 既存設定削除失敗")
        return False

    # ステップ4: Triangle化
    if not triangulate_mesh():
        print("\n❌ Triangle化失敗")
        return False

    # ステップ5: Surface Deformable適用
    if not apply_surface_deformable():
        print("\n❌ Surface Deformable適用失敗")
        return False

    # 完了
    print("\n\n" + "=" * 70)
    print("🎉 すべての処理が完了しました！")
    print("=" * 70)

    print("\n【最終ステップ】")
    print("  1. Stageを保存 (Ctrl+S)")
    print("  2. Playボタンを押してシミュレーション開始")
    print("  3. Cableが柔軟に動くか確認")

    print("\n【パラメータ調整】")
    print("  Material: /World/New_MillingMachine/Pulag/Cable/.../SurfaceDeformableMaterial")
    print("  - 柔らかくする: Young's Modulus を下げる (1e6など)")
    print("  - 硬くする: Young's Modulus を上げる (1e7など)")
    print("  - 早く静止: Damping を上げる (0.3など)")

    print("\n【重要】")
    print("  - Surface Deformableは重力の影響を受けます")
    print("  - 端点を固定したい場合は Attachment を追加")

    return True

if __name__ == "__main__":
    main()
