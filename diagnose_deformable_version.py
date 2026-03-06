"""
Deformable Body のバージョンとAPI状態を診断
Beta版とDeprecated版のどちらが適用されているか確認
"""

import omni.usd
from pxr import Usd, UsdGeom, PhysxSchema, Sdf
import carb.settings

def diagnose_deformable_version():
    """Deformable Bodyのバージョンと状態を診断"""

    print("=" * 70)
    print("Deformable Body バージョン診断")
    print("=" * 70)

    # 1. Beta機能の設定確認
    print("\n【1. Beta機能設定確認】")
    settings = carb.settings.get_settings()

    # 複数の可能性のある設定パスを確認
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

    if beta_enabled:
        print("\n  ✅ Beta機能が有効になっている設定が見つかりました")
    else:
        print("\n  ⚠️  Beta機能の設定が見つからない、または無効です")

    # 2. PhysxSchemaのバージョン確認
    print("\n【2. PhysxSchema API確認】")

    try:
        # Beta版のAPI
        has_new_api = hasattr(PhysxSchema, 'PhysxDeformableBodyAPI')
        print(f"  PhysxDeformableBodyAPI (Beta): {has_new_api}")

        if has_new_api:
            api = PhysxSchema.PhysxDeformableBodyAPI
            # Beta版特有の属性を確認
            has_simulation_mesh = hasattr(api, 'CreateSimulationMeshResolutionAttr')
            has_collision_simplification = hasattr(api, 'CreateCollisionSimplificationAttr')

            print(f"    - SimulationMeshResolution属性: {has_simulation_mesh}")
            print(f"    - CollisionSimplification属性: {has_collision_simplification}")

            if has_simulation_mesh or has_collision_simplification:
                print("    ✅ Beta版のAPIと思われます")
            else:
                print("    ⚠️  Deprecated版のAPIの可能性があります")

    except Exception as e:
        print(f"  ❌ PhysxDeformableBodyAPI確認エラー: {e}")

    # 3. Cableの現在の状態確認
    print("\n【3. Cable の現在の状態確認】")

    stage = omni.usd.get_context().get_stage()
    if not stage:
        print("  ❌ Stage not loaded")
        return

    cable_path = "/World/New_MillingMachine/Pulag/Cable"
    cable_prim = stage.GetPrimAtPath(cable_path)

    if not cable_prim or not cable_prim.IsValid():
        print(f"  ❌ Cable not found: {cable_path}")
        return

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
        print(f"  ❌ Mesh not found in Cable")
        return

    print(f"  Target Mesh: {target_mesh_prim.GetPath()}")

    # 適用されているAPIを確認
    print("\n  【適用されているAPI】")

    # Beta版
    has_deformable_body = target_mesh_prim.HasAPI(PhysxSchema.PhysxDeformableBodyAPI)
    print(f"    PhysxDeformableBodyAPI: {has_deformable_body}")

    # すべての適用されているAPIを表示
    applied_schemas = target_mesh_prim.GetAppliedSchemas()
    print(f"\n  【すべての適用されているスキーマ】")
    for schema in applied_schemas:
        print(f"    - {schema}")

        # Deprecated版を示すスキーマ
        if "PhysxDeformable" in schema and "API" not in schema:
            print(f"      ⚠️  これはDeprecated版の可能性があります")

        # Beta版を示すスキーマ
        if schema == "PhysxDeformableBodyAPI":
            print(f"      ✅ これはBeta版のスキーマです")

    # 属性を確認
    print(f"\n  【Deformable関連の属性】")
    for attr in target_mesh_prim.GetAttributes():
        attr_name = attr.GetName()
        if "deformable" in attr_name.lower() or "physx" in attr_name.lower():
            value = attr.Get()
            print(f"    {attr_name}: {value}")

    # 4. 結論と推奨アクション
    print("\n" + "=" * 70)
    print("【結論と推奨アクション】")
    print("=" * 70)

    if has_deformable_body:
        # APIは適用されているが、Tetmeshエラーが出ている
        print("\n⚠️  PhysxDeformableBodyAPIは適用されていますが、")
        print("   Tetmesh（四面体メッシュ）として処理されています。")
        print("\n考えられる原因:")
        print("  1. Beta版APIが内部的にDeprecated実装を使用している")
        print("  2. メッシュがTriangle Meshではない")
        print("  3. Omniverseバージョンが古く、Beta版が未実装")

        print("\n推奨アクション:")
        print("  A. 既存のDeformable Body APIを削除")
        print("  B. メッシュをTriangle Meshに変換")
        print("  C. Surface Deformableとして明示的に設定")

    else:
        print("\n✅ PhysxDeformableBodyAPIが適用されていません")
        print("\n推奨アクション:")
        print("  スクリプトを再実行してください")

    print("\n次のステップ:")
    print("  1. remove_deformable_from_cable.py を実行")
    print("  2. apply_deformable_surface.py を実行（Surface Deformable専用）")

if __name__ == "__main__":
    diagnose_deformable_version()
