"""
PhysxDeformableBodyMaterialAPIで利用可能な属性を確認
"""

import omni.usd
from pxr import Usd, UsdGeom, PhysxSchema, Sdf

def check_material_attributes():
    """利用可能なMaterial属性を確認"""

    print("=" * 70)
    print("PhysxDeformableBodyMaterialAPI 利用可能属性確認")
    print("=" * 70)

    stage = omni.usd.get_context().get_stage()
    if not stage:
        print("❌ Stage not loaded!")
        return

    # 一時的なMaterialを作成してAPIを確認
    temp_path = Sdf.Path("/World/TempMaterial_Check")

    # 既存のTempを削除
    if stage.GetPrimAtPath(temp_path).IsValid():
        stage.RemovePrim(temp_path)

    temp_prim = stage.DefinePrim(temp_path, "Material")
    material_api = PhysxSchema.PhysxDeformableBodyMaterialAPI.Apply(temp_prim)

    print("\n【PhysxDeformableBodyMaterialAPI - 利用可能メソッド】\n")

    # すべての属性を確認
    common_attrs = [
        ("CreateYoungsModulusAttr", "Young's Modulus (剛性)"),
        ("CreatePoissonsRatioAttr", "Poisson's Ratio (体積保存)"),
        ("CreateDynamicFrictionAttr", "Dynamic Friction (動摩擦)"),
        ("CreateDampingAttr", "Damping (減衰)"),
        ("CreateDampingScaleAttr", "Damping Scale"),
        ("CreateDensityAttr", "Density (密度)"),
    ]

    available = []
    unavailable = []

    for attr_method, description in common_attrs:
        if hasattr(material_api, attr_method):
            available.append((attr_method, description))
            print(f"✅ {attr_method:30s} - {description}")
        else:
            unavailable.append((attr_method, description))
            print(f"❌ {attr_method:30s} - {description}")

    # 実際に設定を試す
    print("\n【実際の設定テスト】\n")

    for attr_method, description in available:
        try:
            method = getattr(material_api, attr_method)
            attr = method()

            # 適切なデフォルト値を設定
            test_values = {
                "CreateYoungsModulusAttr": 1e6,
                "CreatePoissonsRatioAttr": 0.4,
                "CreateDynamicFrictionAttr": 0.5,
                "CreateDampingAttr": 0.1,
                "CreateDampingScaleAttr": 1.0,
                "CreateDensityAttr": 1000.0,
            }

            value = test_values.get(attr_method, 1.0)
            attr.Set(value)

            # 読み取りテスト
            read_value = attr.Get()
            print(f"✅ {attr_method:30s} : 設定={value}, 読取={read_value}")

        except Exception as e:
            print(f"⚠️  {attr_method:30s} : エラー - {e}")

    # Temp削除
    stage.RemovePrim(temp_path)

    print("\n" + "=" * 70)
    print("推奨設定")
    print("=" * 70)

    print("\n利用可能な属性のみを使用したMaterial設定:")
    print("\n```python")
    print("material_api = PhysxSchema.PhysxDeformableBodyMaterialAPI.Apply(material_prim)")

    for attr_method, description in available:
        if attr_method == "CreateYoungsModulusAttr":
            print(f"material_api.{attr_method}().Set(5e6)  # {description}")
        elif attr_method == "CreatePoissonsRatioAttr":
            print(f"material_api.{attr_method}().Set(0.4)  # {description}")
        elif attr_method == "CreateDynamicFrictionAttr":
            print(f"material_api.{attr_method}().Set(0.6)  # {description}")
        elif attr_method == "CreateDensityAttr":
            print(f"material_api.{attr_method}().Set(1000.0)  # {description}")

    print("```")

if __name__ == "__main__":
    check_material_attributes()
