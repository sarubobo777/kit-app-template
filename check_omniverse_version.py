"""
Omniverseバージョンと利用可能なDeformable Body機能を確認
"""

import omni.usd
import carb.settings
from pxr import Usd, UsdGeom, PhysxSchema

def check_version_and_features():
    """バージョンと機能確認"""

    print("=" * 70)
    print("Omniverse バージョンと機能確認")
    print("=" * 70)

    # Kit バージョン
    print("\n【Kit情報】")
    settings = carb.settings.get_settings()

    version_info = [
        "/app/version",
        "/app/name",
        "/physics/version",
    ]

    for path in version_info:
        value = settings.get(path)
        if value:
            print(f"  {path}: {value}")

    # PhysxSchema 利用可能API確認
    print("\n【PhysxSchema 利用可能API】")

    apis_to_check = [
        ("PhysxDeformableBodyAPI", "Deformable Body (Beta/Deprecated)"),
        ("PhysxDeformableSurfaceAPI", "Deformable Surface (Beta)"),
        ("PhysxSoftBodyAPI", "Soft Body (新しい実装)"),
        ("PhysxDeformableAPI", "Deformable (旧版)"),
    ]

    available_apis = []

    for api_name, description in apis_to_check:
        if hasattr(PhysxSchema, api_name):
            available_apis.append((api_name, description))
            print(f"  ✅ {api_name:30s} - {description}")

            # APIの属性を確認
            api_class = getattr(PhysxSchema, api_name)

            key_attrs = [
                "CreateSimulationMeshResolutionAttr",
                "CreateCollisionSimplificationAttr",
                "CreateSolverPositionIterationCountAttr",
                "CreateVertexVelocityDampingAttr",
                "CreateSelfCollisionAttr",
            ]

            has_beta_features = False
            for attr in key_attrs:
                if hasattr(api_class, attr):
                    print(f"      - {attr}")
                    has_beta_features = True

            if not has_beta_features:
                print(f"      ⚠️  Beta版の属性が見つかりません (Deprecated版)")

        else:
            print(f"  ❌ {api_name:30s} - {description}")

    # PhysxDeformableBodyMaterialAPI の属性確認
    print("\n【PhysxDeformableBodyMaterialAPI 属性】")

    if hasattr(PhysxSchema, 'PhysxDeformableBodyMaterialAPI'):
        stage = omni.usd.get_context().get_stage()
        if stage:
            from pxr import Sdf

            # 一時Materialを作成
            temp_path = Sdf.Path("/World/TempMaterialCheck")
            if stage.GetPrimAtPath(temp_path).IsValid():
                stage.RemovePrim(temp_path)

            temp_prim = stage.DefinePrim(temp_path, "Material")
            material_api = PhysxSchema.PhysxDeformableBodyMaterialAPI.Apply(temp_prim)

            material_attrs = [
                "CreateYoungsModulusAttr",
                "CreatePoissonsRatioAttr",
                "CreateDynamicFrictionAttr",
                "CreateDampingAttr",
                "CreateDensityAttr",
                "CreateDampingScaleAttr",
            ]

            for attr in material_attrs:
                if hasattr(material_api, attr):
                    print(f"  ✅ {attr}")
                else:
                    print(f"  ❌ {attr}")

            # 後片付け
            stage.RemovePrim(temp_path)

    # 結論
    print("\n" + "=" * 70)
    print("【結論と推奨方法】")
    print("=" * 70)

    print("\nこのOmniverseバージョンでは:")

    if not any("SimulationMeshResolution" in str(api) for api in available_apis):
        print("  ⚠️  Beta版の新しいDeformable Body機能が実装されていません")
        print("  ⚠️  Tetmesh変換を回避する方法がありません")

        print("\n【推奨される代替方法】")
        print("\n1. SoftBody機能を使用 (PhysxSoftBodyAPI)")
        print("   - より新しい実装")
        print("   - Triangle Meshをサポート")
        print("   - Tetmesh変換が不要")

        print("\n2. Omniverseをアップデート")
        print("   - Kit 107.0以降を推奨")
        print("   - Beta版Deformable Body機能が実装されています")

        print("\n3. SoftBodyスクリプトの作成")
        print("   - apply_softbody_to_cable.py を作成します")

    else:
        print("  ✅ Beta版の機能が利用可能です")
        print("  → SimulationMeshResolution を 0 に設定してください")

if __name__ == "__main__":
    check_version_and_features()
