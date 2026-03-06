"""
CableメッシュをTriangle Meshに変換するスクリプト
Quad MeshからTriangle Meshへの変換
"""

import omni.usd
from pxr import Usd, UsdGeom, Vt

def triangulate_mesh():
    """CableメッシュをTriangle化"""

    stage = omni.usd.get_context().get_stage()

    if not stage:
        print("❌ Stage not loaded!")
        return False

    cable_path = "/World/New_MillingMachine/Pulag/Cable"

    print("=" * 70)
    print("メッシュTriangle化スクリプト")
    print("=" * 70)

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

    # メッシュデータを取得
    mesh_geom = UsdGeom.Mesh(target_mesh_prim)

    points = mesh_geom.GetPointsAttr().Get()
    face_vertex_counts = mesh_geom.GetFaceVertexCountsAttr().Get()
    face_vertex_indices = mesh_geom.GetFaceVertexIndicesAttr().Get()

    if not points or not face_vertex_counts or not face_vertex_indices:
        print("❌ メッシュデータが不完全です")
        return False

    print(f"\n【変換前】")
    print(f"  頂点数: {len(points)}")
    print(f"  面数: {len(face_vertex_counts)}")

    # 面の種類を分析
    triangle_count = sum(1 for c in face_vertex_counts if c == 3)
    quad_count = sum(1 for c in face_vertex_counts if c == 4)
    other_count = len(face_vertex_counts) - triangle_count - quad_count

    print(f"  Triangle面: {triangle_count}")
    print(f"  Quad面: {quad_count}")
    print(f"  その他: {other_count}")

    # すでにTriangle Meshかチェック
    if quad_count == 0 and other_count == 0:
        print("\n✅ すでにTriangle Meshです！変換不要")
        return True

    # Triangle化処理
    print(f"\n【Triangle化処理開始】")

    new_face_vertex_counts = []
    new_face_vertex_indices = []

    current_index = 0

    for face_count in face_vertex_counts:
        face_indices = [face_vertex_indices[current_index + i] for i in range(face_count)]

        if face_count == 3:
            # すでにTriangle - そのまま追加
            new_face_vertex_counts.append(3)
            new_face_vertex_indices.extend(face_indices)

        elif face_count == 4:
            # Quad → 2つのTriangleに分割
            # v0, v1, v2, v3 → (v0, v1, v2) + (v0, v2, v3)
            new_face_vertex_counts.append(3)
            new_face_vertex_counts.append(3)
            new_face_vertex_indices.extend([face_indices[0], face_indices[1], face_indices[2]])
            new_face_vertex_indices.extend([face_indices[0], face_indices[2], face_indices[3]])

        else:
            # N角形 → Fan Triangulation (扇形分割)
            # v0を中心として、v1-v2, v2-v3, v3-v4... とTriangle化
            for i in range(1, face_count - 1):
                new_face_vertex_counts.append(3)
                new_face_vertex_indices.extend([face_indices[0], face_indices[i], face_indices[i + 1]])

        current_index += face_count

    # 変換結果を設定
    mesh_geom.GetFaceVertexCountsAttr().Set(Vt.IntArray(new_face_vertex_counts))
    mesh_geom.GetFaceVertexIndicesAttr().Set(Vt.IntArray(new_face_vertex_indices))

    print(f"\n【変換後】")
    print(f"  頂点数: {len(points)} (変更なし)")
    print(f"  面数: {len(new_face_vertex_counts)}")
    print(f"  すべてTriangle面: {all(c == 3 for c in new_face_vertex_counts)}")

    print("\n" + "=" * 70)
    print("🎉 Triangle化完了！")
    print("=" * 70)

    print("\n次のステップ:")
    print("  1. Stageを保存")
    print("  2. apply_deformable_surface.py を実行")
    print("     (Surface Deformableを適用)")

    return True

if __name__ == "__main__":
    triangulate_mesh()
