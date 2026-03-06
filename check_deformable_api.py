"""
PhysxDeformableBodyAPI の利用可能な属性を確認するスクリプト
バージョンによって異なる属性名を特定
"""

from pxr import PhysxSchema

def check_deformable_api_attributes():
    """PhysxDeformableBodyAPIの利用可能なメソッドを確認"""

    print("=" * 70)
    print("PhysxDeformableBodyAPI 利用可能な属性チェック")
    print("=" * 70)

    # PhysxDeformableBodyAPI のすべての属性を取得
    api_class = PhysxSchema.PhysxDeformableBodyAPI

    print("\n【Create*Attr メソッド一覧】")
    create_methods = [attr for attr in dir(api_class) if attr.startswith('Create') and 'Attr' in attr]

    if create_methods:
        for method in sorted(create_methods):
            print(f"  ✓ {method}")
    else:
        print("  ⚠️  Create*Attr メソッドが見つかりません")

    print("\n【Get*Attr メソッド一覧】")
    get_methods = [attr for attr in dir(api_class) if attr.startswith('Get') and 'Attr' in attr]

    if get_methods:
        for method in sorted(get_methods):
            print(f"  ✓ {method}")
    else:
        print("  ⚠️  Get*Attr メソッドが見つかりません")

    print("\n【推奨される設定】")

    # よく使われる属性の存在確認
    common_attrs = [
        ('CreateSelfCollisionAttr', 'Self Collision (自己衝突)'),
        ('CreateEnableSelfCollisionAttr', 'Enable Self Collision'),
        ('CreateSolverPositionIterationCountAttr', 'Solver Position Iterations'),
        ('CreateVertexVelocityDampingAttr', 'Vertex Velocity Damping'),
        ('CreateSimulationMeshResolutionAttr', 'Simulation Mesh Resolution'),
        ('CreateCollisionSimplificationAttr', 'Collision Simplification'),
    ]

    for method_name, description in common_attrs:
        has_method = hasattr(api_class, method_name)
        status = "✅ 利用可能" if has_method else "❌ 利用不可"
        print(f"  {status}: {method_name}")
        print(f"           ({description})")

    print("\n" + "=" * 70)
    print("PhysxDeformableBodyMaterialAPI の利用可能な属性チェック")
    print("=" * 70)

    material_class = PhysxSchema.PhysxDeformableBodyMaterialAPI

    print("\n【Create*Attr メソッド一覧】")
    material_create_methods = [attr for attr in dir(material_class) if attr.startswith('Create') and 'Attr' in attr]

    if material_create_methods:
        for method in sorted(material_create_methods):
            print(f"  ✓ {method}")

    print("\n【重要なマテリアル属性】")
    material_attrs = [
        ('CreateYoungsModulusAttr', "Young's Modulus (剛性)"),
        ('CreatePoissonsRatioAttr', "Poisson's Ratio (体積保存)"),
        ('CreateDynamicFrictionAttr', 'Dynamic Friction (動摩擦)'),
        ('CreateDampingAttr', 'Damping (減衰)'),
    ]

    for method_name, description in material_attrs:
        has_method = hasattr(material_class, method_name)
        status = "✅ 利用可能" if has_method else "❌ 利用不可"
        print(f"  {status}: {method_name}")
        print(f"           ({description})")

    print("\n" + "=" * 70)

if __name__ == "__main__":
    check_deformable_api_attributes()
