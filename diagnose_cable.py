"""
Cable Deformable Body 診断スクリプト
/World/New_MillingMachine/Pulag/Cable の構造を確認
"""

import omni.usd
from pxr import Usd, UsdGeom, Sdf, PhysxSchema, UsdPhysics

def diagnose_cable():
    """Cableの構造を診断"""
    stage = omni.usd.get_context().get_stage()

    if not stage:
        print("❌ Stage not loaded!")
        return

    cable_path = "/World/New_MillingMachine/Pulag/Cable"

    print("=" * 70)
    print("Cable Deformable Body 診断レポート")
    print("=" * 70)
    print(f"\n対象パス: {cable_path}\n")

    cable_prim = stage.GetPrimAtPath(cable_path)

    if not cable_prim or not cable_prim.IsValid():
        print(f"❌ Prim not found: {cable_path}")
        print("\n利用可能なPulag配下のプリムを検索中...")

        pulag_prim = stage.GetPrimAtPath("/World/New_MillingMachine/Pulag")
        if pulag_prim.IsValid():
            print("\nPulag配下のプリム:")
            for child in pulag_prim.GetAllChildren():
                print(f"  - {child.GetPath()} (Type: {child.GetTypeName()})")
        return

    # 基本情報
    print("【基本情報】")
    print(f"  Prim Type: {cable_prim.GetTypeName()}")
    print(f"  Valid: {cable_prim.IsValid()}")
    print(f"  Active: {cable_prim.IsActive()}")

    # メッシュかどうか
    is_mesh = cable_prim.IsA(UsdGeom.Mesh)
    print(f"  Is Mesh: {is_mesh}")

    if is_mesh:
        print("\n  ✅ これはMeshプリムです！")
        mesh = UsdGeom.Mesh(cable_prim)

        # メッシュ詳細
        points_attr = mesh.GetPointsAttr()
        points = points_attr.Get() if points_attr else None

        face_vertex_counts_attr = mesh.GetFaceVertexCountsAttr()
        face_vertex_counts = face_vertex_counts_attr.Get() if face_vertex_counts_attr else None

        if points:
            print(f"  頂点数: {len(points)}")
        else:
            print("  ⚠️  頂点データなし")

        if face_vertex_counts:
            print(f"  面数: {len(face_vertex_counts)}")
            # 三角形メッシュか確認
            is_triangle = all(count == 3 for count in face_vertex_counts)
            is_quad = all(count == 4 for count in face_vertex_counts)

            if is_triangle:
                print("  メッシュタイプ: Triangle Mesh ✅ (Deformable Body対応)")
            elif is_quad:
                print("  メッシュタイプ: Quad Mesh ⚠️ (Triangle変換が必要)")
            else:
                print("  メッシュタイプ: Mixed")
        else:
            print("  ⚠️  面データなし")

    else:
        print("\n  ⚠️  これはMeshプリムではありません（Xformなど）")
        print("  → 子要素を探してメッシュを見つける必要があります")

    # 子要素を確認
    print("\n【子要素】")
    children = list(cable_prim.GetChildren())
    if children:
        print(f"  子要素数: {len(children)}")
        for child in children:
            child_type = child.GetTypeName()
            is_child_mesh = child.IsA(UsdGeom.Mesh)

            marker = "🎯" if is_child_mesh else "  "
            print(f"  {marker} {child.GetPath()}")
            print(f"     Type: {child_type}")

            if is_child_mesh:
                print(f"     ✅ これがメッシュです！Deformable Bodyはこれに適用してください")

                # 子メッシュの詳細
                child_mesh = UsdGeom.Mesh(child)
                child_points = child_mesh.GetPointsAttr().Get()
                if child_points:
                    print(f"     頂点数: {len(child_points)}")
    else:
        print("  子要素なし")

    # 全子孫を再帰的に探す
    print("\n【全子孫プリム（メッシュのみ）】")
    mesh_descendants = []

    def find_meshes(prim):
        if prim.IsA(UsdGeom.Mesh):
            mesh_descendants.append(prim)
        for child in prim.GetChildren():
            find_meshes(child)

    find_meshes(cable_prim)

    if mesh_descendants:
        print(f"  メッシュ発見: {len(mesh_descendants)}個")
        for i, mesh_prim in enumerate(mesh_descendants, 1):
            print(f"  [{i}] {mesh_prim.GetPath()}")
            mesh_geom = UsdGeom.Mesh(mesh_prim)
            points = mesh_geom.GetPointsAttr().Get()
            if points:
                print(f"      頂点数: {len(points)}")
    else:
        print("  ❌ メッシュが見つかりません")

    # 既存のPhysics設定確認
    print("\n【既存のPhysics設定】")
    has_collision = cable_prim.HasAPI(UsdPhysics.CollisionAPI)
    has_rigidbody = cable_prim.HasAPI(UsdPhysics.RigidBodyAPI)
    has_deformable = cable_prim.HasAPI(PhysxSchema.PhysxDeformableBodyAPI)

    print(f"  CollisionAPI: {has_collision}")
    print(f"  RigidBodyAPI: {has_rigidbody}")
    print(f"  PhysxDeformableBodyAPI: {has_deformable}")

    if has_deformable:
        print("  ✅ すでにDeformable Body APIが適用されています")

    # 結論と推奨
    print("\n" + "=" * 70)
    print("【結論と推奨アクション】")
    print("=" * 70)

    if is_mesh and points and len(points) > 0:
        print("✅ このプリムはDeformable Body適用可能です")
        print(f"\n推奨アクション:")
        print(f"  1. Stageパネルで {cable_path} を選択")
        print(f"  2. 右クリック → Add → Physics → Deformable Body (Beta)")
        print(f"  3. Surface を選択（ケーブルに適している）")

        if not has_deformable:
            print(f"\n代替方法（Pythonスクリプトで適用）:")
            print(f"  スクリプト 'apply_deformable_to_cable.py' を実行")

    elif not is_mesh and mesh_descendants:
        target_mesh = mesh_descendants[0]
        print(f"⚠️  {cable_path} 自体はメッシュではありません")
        print(f"\n推奨アクション:")
        print(f"  1. Stageパネルで {target_mesh.GetPath()} を選択")
        print(f"  2. 右クリック → Add → Physics → Deformable Body (Beta)")
        print(f"  3. Surface を選択")

        print(f"\n代替方法（Pythonスクリプトで適用）:")
        print(f"  スクリプト 'apply_deformable_to_cable.py' を実行")
        print(f"  （自動的に正しいメッシュに適用します）")

    else:
        print("❌ メッシュが見つからない、または頂点データがありません")
        print("\n考えられる原因:")
        print("  - USDファイルのインポートが不完全")
        print("  - 参照（Reference）されているメッシュが読み込まれていない")
        print("  - メッシュが別のレイヤーにある")

        print("\n解決策:")
        print("  1. USD Composerでファイルを開き直す")
        print("  2. 外部参照を 'Flatten' する")
        print("  3. メッシュを再エクスポート")

if __name__ == "__main__":
    diagnose_cable()
