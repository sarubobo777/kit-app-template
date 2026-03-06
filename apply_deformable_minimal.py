"""
最小限のDeformable Body適用スクリプト
属性設定なしで、APIのApplyのみを行う
"""

import omni.usd
from pxr import Usd, UsdGeom, UsdPhysics, UsdShade, PhysxSchema, Sdf

def apply_deformable_minimal():
    """最小限の設定でDeformable Bodyを適用"""

    stage = omni.usd.get_context().get_stage()

    if not stage:
        print("❌ Stage not loaded!")
        return False

    cable_path = "/World/New_MillingMachine/Pulag/Cable"

    print("=" * 70)
    print("最小限 Deformable Body 適用")
    print("=" * 70)

    cable_prim = stage.GetPrimAtPath(cable_path)

    if not cable_prim or not cable_prim.IsValid():
        print(f"❌ Prim not found: {cable_path}")
        return False

    # メッシュプリムを探す
    target_mesh_prim = None

    if cable_prim.IsA(UsdGeom.Mesh):
        target_mesh_prim = cable_prim
        print(f"✅ Mesh found: {cable_path}")
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
            print(f"✅ Mesh found: {target_mesh_prim.GetPath()}")
        else:
            print(f"❌ No mesh found")
            return False

    # RigidBodyAPIがあれば削除
    if target_mesh_prim.HasAPI(UsdPhysics.RigidBodyAPI):
        print("Removing RigidBodyAPI...")
        target_mesh_prim.RemoveAPI(UsdPhysics.RigidBodyAPI)

    # 1. PhysxDeformableBodyAPI を適用（設定なし）
    print("\nApplying PhysxDeformableBodyAPI...")
    try:
        deformable_api = PhysxSchema.PhysxDeformableBodyAPI.Apply(target_mesh_prim)
        print("✅ PhysxDeformableBodyAPI applied")
    except Exception as e:
        print(f"❌ Failed to apply PhysxDeformableBodyAPI: {e}")
        return False

    # 2. CollisionAPI を適用
    if not target_mesh_prim.HasAPI(UsdPhysics.CollisionAPI):
        print("\nApplying CollisionAPI...")
        try:
            UsdPhysics.CollisionAPI.Apply(target_mesh_prim)
            print("✅ CollisionAPI applied")
        except Exception as e:
            print(f"❌ Failed to apply CollisionAPI: {e}")
            return False
    else:
        print("\nCollisionAPI already exists")

    # 3. Deformable Body Material を作成
    print("\nCreating Deformable Material...")
    material_path = target_mesh_prim.GetPath().AppendChild("DeformableMaterial")

    try:
        material_prim = stage.DefinePrim(material_path, "Material")
        material_api = PhysxSchema.PhysxDeformableBodyMaterialAPI.Apply(material_prim)

        # 基本的なマテリアル設定のみ（バージョン互換性考慮）
        try:
            material_api.CreateYoungsModulusAttr().Set(1e6)
        except:
            pass

        try:
            material_api.CreatePoissonsRatioAttr().Set(0.45)
        except:
            pass

        try:
            material_api.CreateDynamicFrictionAttr().Set(0.5)
        except:
            pass

        # Dampingは一部バージョンで非対応
        try:
            if hasattr(material_api, 'CreateDampingAttr'):
                material_api.CreateDampingAttr().Set(0.2)
        except:
            pass

        # Densityは一部バージョンで必要
        try:
            if hasattr(material_api, 'CreateDensityAttr'):
                material_api.CreateDensityAttr().Set(1000.0)
        except:
            pass

        print("✅ Deformable Material created")
        print(f"   Path: {material_path}")

    except Exception as e:
        print(f"⚠️  Material creation warning: {e}")
        print("   (Material may still work)")

    # 4. Material をバインド
    print("\nBinding Material...")
    try:
        # UsdShade.MaterialBindingAPI を使用
        binding_api = UsdShade.MaterialBindingAPI.Apply(target_mesh_prim)
        binding_api.Bind(UsdShade.Material(material_prim), UsdShade.Tokens.physics)
        print("✅ Material bound")
    except Exception as e:
        print(f"⚠️  Material binding warning: {e}")
        # 代替方法
        try:
            material_rel = target_mesh_prim.CreateRelationship("physics:material", False)
            material_rel.SetTargets([material_path])
            print("✅ Material bound (alternative method)")
        except:
            pass

    print("\n" + "=" * 70)
    print("🎉 Complete!")
    print("=" * 70)
    print(f"\nTarget: {target_mesh_prim.GetPath()}")
    print("\nNext steps:")
    print("  1. Press Play to start simulation")
    print("  2. Check if cable deforms")
    print("  3. Adjust material parameters if needed")

    return True

if __name__ == "__main__":
    apply_deformable_minimal()
