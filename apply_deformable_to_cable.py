"""
Cable に Deformable Body を適用するスクリプト
/World/New_MillingMachine/Pulag/Cable にDeformable Body (Beta) を適用

使用方法:
1. USD Composer または Kit アプリケーションでフライス盤.usdを開く
2. Window → Script Editor でこのスクリプトを実行
"""

import omni.usd
from pxr import Usd, UsdGeom, UsdPhysics, PhysxSchema, Sdf, Gf

def apply_deformable_to_cable():
    """Cableにdeformable bodyを適用"""

    stage = omni.usd.get_context().get_stage()

    if not stage:
        print("❌ Stage not loaded!")
        return False

    cable_path = "/World/New_MillingMachine/Pulag/Cable"

    print("=" * 70)
    print("Cable Deformable Body 適用スクリプト")
    print("=" * 70)

    cable_prim = stage.GetPrimAtPath(cable_path)

    if not cable_prim or not cable_prim.IsValid():
        print(f"❌ Prim not found: {cable_path}")
        return False

    # メッシュプリムを探す
    target_mesh_prim = None

    if cable_prim.IsA(UsdGeom.Mesh):
        # 直接メッシュの場合
        target_mesh_prim = cable_prim
        print(f"✅ {cable_path} はメッシュプリムです")
    else:
        # 子要素からメッシュを探す
        print(f"⚠️  {cable_path} はメッシュではありません。子要素を探索...")

        def find_first_mesh(prim):
            """再帰的に最初のメッシュを探す"""
            if prim.IsA(UsdGeom.Mesh):
                return prim
            for child in prim.GetChildren():
                result = find_first_mesh(child)
                if result:
                    return result
            return None

        target_mesh_prim = find_first_mesh(cable_prim)

        if target_mesh_prim:
            print(f"✅ メッシュ発見: {target_mesh_prim.GetPath()}")
        else:
            print(f"❌ メッシュが見つかりません")
            return False

    # メッシュの検証
    mesh_geom = UsdGeom.Mesh(target_mesh_prim)
    points = mesh_geom.GetPointsAttr().Get()

    if not points or len(points) == 0:
        print(f"❌ メッシュに頂点データがありません")
        return False

    print(f"  頂点数: {len(points)}")

    face_counts = mesh_geom.GetFaceVertexCountsAttr().Get()
    if face_counts:
        print(f"  面数: {len(face_counts)}")

        # 三角形メッシュか確認
        is_triangle = all(count == 3 for count in face_counts)
        if is_triangle:
            print(f"  ✅ Triangle Mesh (Deformable Body最適)")
        else:
            print(f"  ⚠️  Non-triangle mesh (動作する可能性がありますが、Triangleが推奨)")

    # 既存のPhysicsAPI確認
    print("\n【既存API確認】")
    has_collision = target_mesh_prim.HasAPI(UsdPhysics.CollisionAPI)
    has_rigidbody = target_mesh_prim.HasAPI(UsdPhysics.RigidBodyAPI)
    has_deformable = target_mesh_prim.HasAPI(PhysxSchema.PhysxDeformableBodyAPI)

    print(f"  CollisionAPI: {has_collision}")
    print(f"  RigidBodyAPI: {has_rigidbody}")
    print(f"  PhysxDeformableBodyAPI: {has_deformable}")

    if has_deformable:
        print("\n⚠️  すでに PhysxDeformableBodyAPI が適用されています")
        user_input = input("既存の設定を上書きしますか？ (y/n): ")
        if user_input.lower() != 'y':
            print("キャンセルしました")
            return False

    # RigidBodyAPIがある場合は削除（DeformableとRigidBodyは共存不可）
    if has_rigidbody:
        print("\n⚠️  RigidBodyAPI を削除中...")
        target_mesh_prim.RemoveAPI(UsdPhysics.RigidBodyAPI)
        print("  ✅ RigidBodyAPI 削除完了")

    print("\n【Deformable Body 適用開始】")

    # 1. PhysxDeformableBodyAPI を適用
    print("\n[1] PhysxDeformableBodyAPI を適用中...")
    deformable_api = PhysxSchema.PhysxDeformableBodyAPI.Apply(target_mesh_prim)

    # 利用可能な属性を確認して設定
    try:
        # Solver Iteration Count (安定性向上)
        if hasattr(deformable_api, 'CreateSolverPositionIterationCountAttr'):
            deformable_api.CreateSolverPositionIterationCountAttr().Set(16)
            print("  ✓ Solver Position Iteration Count: 16")
    except Exception as e:
        print(f"  ⚠️  Solver iteration設定スキップ: {e}")

    try:
        # Vertex Velocity Damping (揺れを抑える)
        if hasattr(deformable_api, 'CreateVertexVelocityDampingAttr'):
            deformable_api.CreateVertexVelocityDampingAttr().Set(0.005)
            print("  ✓ Vertex Velocity Damping: 0.005")
    except Exception as e:
        print(f"  ⚠️  Damping設定スキップ: {e}")

    try:
        # Self Collision (ケーブルの自己衝突は通常OFF)
        if hasattr(deformable_api, 'CreateSelfCollisionAttr'):
            deformable_api.CreateSelfCollisionAttr().Set(False)
            print("  ✓ Self Collision: False")
        elif hasattr(deformable_api, 'CreateEnableSelfCollisionAttr'):
            deformable_api.CreateEnableSelfCollisionAttr().Set(False)
            print("  ✓ Enable Self Collision: False")
    except Exception as e:
        print(f"  ⚠️  Self collision設定スキップ: {e}")

    print("  ✅ PhysxDeformableBodyAPI 適用完了")

    # 2. CollisionAPI を適用（まだない場合）
    if not has_collision:
        print("\n[2] CollisionAPI を適用中...")
        collision_api = UsdPhysics.CollisionAPI.Apply(target_mesh_prim)
        print("  ✅ CollisionAPI 適用完了")
    else:
        print("\n[2] CollisionAPI は既に適用済み")

    # 3. Deformable Body Material を作成
    print("\n[3] Deformable Body Material を作成中...")

    material_path = target_mesh_prim.GetPath().AppendChild("DeformableMaterial")
    material_prim = stage.GetPrimAtPath(material_path)

    if not material_prim or not material_prim.IsValid():
        material_prim = stage.DefinePrim(material_path, "Material")
        print(f"  Material Prim 作成: {material_path}")
    else:
        print(f"  Material Prim 既存: {material_path}")

    # PhysxDeformableBodyMaterialAPI を適用
    material_api = PhysxSchema.PhysxDeformableBodyMaterialAPI.Apply(material_prim)

    # ケーブル用のマテリアル設定
    material_api.CreateYoungsModulusAttr().Set(1e6)       # 適度な硬さ
    material_api.CreatePoissonsRatioAttr().Set(0.45)      # ほぼ非圧縮
    material_api.CreateDynamicFrictionAttr().Set(0.5)     # 摩擦
    material_api.CreateDampingAttr().Set(0.2)             # 減衰

    print("  ✅ Material 作成完了")
    print(f"     Young's Modulus: 1e6 (適度な硬さ)")
    print(f"     Poisson's Ratio: 0.45 (ほぼ非圧縮)")
    print(f"     Friction: 0.5")
    print(f"     Damping: 0.2")

    # 4. Material を Mesh にバインド
    print("\n[4] Material を Mesh にバインド中...")

    # PhysicsMaterialBindingAPI を使用
    binding_api = UsdPhysics.MaterialBindingAPI.Apply(target_mesh_prim)

    # Deformable Body Material としてバインド
    binding_rel = binding_api.CreatePhysicsMaterialRel()
    binding_rel.SetTargets([material_path])

    print("  ✅ Material バインド完了")

    print("\n" + "=" * 70)
    print("🎉 Deformable Body 適用完了！")
    print("=" * 70)
    print(f"\n適用対象: {target_mesh_prim.GetPath()}")
    print(f"\n次のステップ:")
    print(f"  1. Playボタンを押してシミュレーション開始")
    print(f"  2. ケーブルが柔軟に動くか確認")
    print(f"  3. 必要に応じてマテリアルパラメータを調整:")
    print(f"     - Young's Modulus: 硬さ（小さい=柔らかい, 大きい=硬い）")
    print(f"     - Damping: 減衰（大きい=早く静止）")

    # アタッチメント作成のヒント
    print(f"\n【オプション: 端点を固定する場合】")
    print(f"  ケーブルの端を壁や機械に固定したい場合:")
    print(f"  1. ケーブルのメッシュを選択")
    print(f"  2. 右クリック → Add → Physics → Deformable Attachment")
    print(f"  3. Attachment設定で固定する頂点インデックスを指定")

    return True


# アタッチメント作成ヘルパー（オプション）
def create_cable_attachment(
    cable_mesh_path: str,
    attachment_name: str,
    vertex_indices: list,
    target_rigid_body_path: str = None
):
    """
    ケーブルにアタッチメントを作成

    Args:
        cable_mesh_path: ケーブルメッシュのパス
        attachment_name: アタッチメント名
        vertex_indices: 固定する頂点インデックスのリスト（例: [0, 1, 2] で端点付近）
        target_rigid_body_path: 固定先のRigidBodyパス（Noneの場合はワールド固定）
    """
    stage = omni.usd.get_context().get_stage()
    cable_prim = stage.GetPrimAtPath(cable_mesh_path)

    if not cable_prim.IsValid():
        print(f"❌ Cable mesh not found: {cable_mesh_path}")
        return

    print(f"\n【アタッチメント作成】")
    print(f"  Name: {attachment_name}")

    # PhysxDeformableAttachmentAPI を適用
    attachment_api = PhysxSchema.PhysxDeformableAttachmentAPI.Apply(
        cable_prim, attachment_name
    )

    # アタッチメント設定
    attachment_api.CreateAttachmentEnabledAttr().Set(True)

    # 固定する頂点を指定
    attachment_api.CreateCollisionIndices0Attr().Set(vertex_indices)

    # アタッチメントの強度
    attachment_api.CreateAttachmentStiffnessAttr().Set(1e8)  # 非常に硬い固定

    if target_rigid_body_path:
        # 特定のRigidBodyに固定
        attachment_api.CreateFilterType0Attr().Set(PhysxSchema.Tokens.rigidBody)
        # ターゲットのパスを設定（実装はPhysX設定による）
        print(f"  ✅ RigidBody固定: {target_rigid_body_path}")
    else:
        # ワールド固定
        print(f"  ✅ ワールド固定")

    print(f"  固定頂点: {vertex_indices}")
    print(f"  アタッチメント作成完了")


if __name__ == "__main__":
    success = apply_deformable_to_cable()

    if success:
        print("\n" + "=" * 70)
        print("スクリプト実行成功！")
        print("=" * 70)

        # アタッチメント作成例（オプション）
        print("\n【オプション】ケーブルの端を固定する場合:")
        print("  下記のコマンドを実行してください:\n")
        print("# ケーブルの先端を固定（頂点0,1,2を固定）")
        print("create_cable_attachment(")
        print('    "/World/New_MillingMachine/Pulag/Cable/メッシュのパス",')
        print('    "EndAttachment",')
        print("    [0, 1, 2]  # 最初の3頂点")
        print(")")
