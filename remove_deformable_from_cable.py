"""
Cableから既存のDeformable Body設定を完全に削除するスクリプト
Beta版、Deprecated版の両方を削除
"""

import omni.usd
from pxr import Usd, UsdGeom, PhysxSchema, UsdPhysics

def remove_deformable_from_cable():
    """Cableから既存のDeformable Body設定を削除"""

    stage = omni.usd.get_context().get_stage()

    if not stage:
        print("❌ Stage not loaded!")
        return False

    cable_path = "/World/New_MillingMachine/Pulag/Cable"

    print("=" * 70)
    print("Deformable Body 削除スクリプト")
    print("=" * 70)

    cable_prim = stage.GetPrimAtPath(cable_path)

    if not cable_prim or not cable_prim.IsValid():
        print(f"❌ Prim not found: {cable_path}")
        return False

    # メッシュプリムを探す
    target_mesh_prim = None

    if cable_prim.IsA(UsdGeom.Mesh):
        target_mesh_prim = cable_prim
        print(f"✅ Target: {cable_path}")
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

        if target_mesh_prim:
            print(f"✅ Target: {target_mesh_prim.GetPath()}")
        else:
            print(f"❌ Mesh not found")
            return False

    print("\n【削除前の状態】")
    applied_schemas = target_mesh_prim.GetAppliedSchemas()
    print(f"適用されているスキーマ数: {len(applied_schemas)}")
    for schema in applied_schemas:
        if "Deformable" in schema or "Physx" in schema:
            print(f"  - {schema}")

    print("\n【API削除開始】")

    removed_count = 0

    # 1. PhysxDeformableBodyAPI (Beta) を削除
    if target_mesh_prim.HasAPI(PhysxSchema.PhysxDeformableBodyAPI):
        try:
            target_mesh_prim.RemoveAPI(PhysxSchema.PhysxDeformableBodyAPI)
            print("  ✅ PhysxDeformableBodyAPI 削除")
            removed_count += 1
        except Exception as e:
            print(f"  ⚠️  PhysxDeformableBodyAPI削除エラー: {e}")

    # 2. すべてのDeformable関連スキーマを削除
    for schema in applied_schemas:
        if "Deformable" in schema:
            try:
                # スキーマをトークンとして削除
                from pxr import Tf
                schema_token = Tf.Token(schema)
                target_mesh_prim.RemoveAppliedSchema(schema_token)
                print(f"  ✅ {schema} 削除")
                removed_count += 1
            except Exception as e:
                print(f"  ⚠️  {schema} 削除エラー: {e}")

    # 3. Deformable関連の属性を削除
    print("\n【属性削除】")
    attrs_to_remove = []

    for attr in target_mesh_prim.GetAttributes():
        attr_name = attr.GetName()
        # Deformable関連の属性を特定
        if any(keyword in attr_name.lower() for keyword in ["deformable", "physxdeformable"]):
            attrs_to_remove.append(attr_name)

    if attrs_to_remove:
        for attr_name in attrs_to_remove:
            try:
                target_mesh_prim.RemoveProperty(attr_name)
                print(f"  ✅ 属性削除: {attr_name}")
                removed_count += 1
            except Exception as e:
                print(f"  ⚠️  属性削除エラー ({attr_name}): {e}")
    else:
        print("  削除する属性なし")

    # 4. Deformable Material を削除
    print("\n【Material削除】")
    material_path = target_mesh_prim.GetPath().AppendChild("DeformableMaterial")
    material_prim = stage.GetPrimAtPath(material_path)

    if material_prim and material_prim.IsValid():
        try:
            stage.RemovePrim(material_path)
            print(f"  ✅ Material削除: {material_path}")
            removed_count += 1
        except Exception as e:
            print(f"  ⚠️  Material削除エラー: {e}")
    else:
        print("  削除するMaterialなし")

    # 5. 削除後の状態確認
    print("\n【削除後の状態】")
    applied_schemas_after = target_mesh_prim.GetAppliedSchemas()
    print(f"適用されているスキーマ数: {len(applied_schemas_after)}")

    remaining_deformable = [s for s in applied_schemas_after if "Deformable" in s]
    if remaining_deformable:
        print("  ⚠️  まだ残っているDeformable関連スキーマ:")
        for schema in remaining_deformable:
            print(f"    - {schema}")
    else:
        print("  ✅ すべてのDeformable関連スキーマが削除されました")

    print("\n" + "=" * 70)
    if removed_count > 0:
        print(f"🎉 削除完了！ ({removed_count}個の項目を削除)")
    else:
        print("⚠️  削除する項目がありませんでした")
    print("=" * 70)

    print("\n次のステップ:")
    print("  1. Stageを保存")
    print("  2. apply_deformable_surface.py を実行")
    print("     (Surface Deformableとして再適用)")

    return True

if __name__ == "__main__":
    remove_deformable_from_cable()
