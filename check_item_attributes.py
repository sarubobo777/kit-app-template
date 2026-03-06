#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
アイテム設定拡張機能用の属性チェックスクリプト

このスクリプトは、ステージ内のオブジェクトが必要なカスタム属性を持っているかをチェックします。
"""

from pxr import Usd, UsdGeom, UsdPhysics, Sdf
import omni.usd


# ========================================
# チェック対象パスの設定
# ========================================
# チェックしたいオブジェクトのパスをここに記入してください
#
# 使用例:
# TARGET_PATHS = [
#     "/World/Items/ItemXform/Cube_01",
#     "/World/Items/ItemXform/Cube_02",
#     "/World/New_MillingMachine/Table/VoxelMesh",
# ]
#
# パスの確認方法:
# 1. Omniverseのステージビューでオブジェクトを選択
# 2. Property Windowの上部に表示されているパスをコピー
# 3. 下のTARGET_PATHSリストに追加
#
TARGET_PATHS = [
    "/World/ItemTray/Xform/Proxy_cube"
]

# TARGET_PATHSが空の場合の動作
# True: ステージ全体をスキャン（遅い）
# False: 何もチェックしない
SCAN_ALL_IF_EMPTY = True


# 必須属性の定義
REQUIRED_ATTRIBUTES = {
    "custom:Number": Sdf.ValueTypeNames.Int,
    "custom:placed": Sdf.ValueTypeNames.Bool,
    "custom:task": Sdf.ValueTypeNames.Bool,
    "custom:original_position": Sdf.ValueTypeNames.Float3,
    "custom:proxy": Sdf.ValueTypeNames.Bool,
    "custom:grab": Sdf.ValueTypeNames.Bool,
}

OPTIONAL_ATTRIBUTES = {
    "custom:slot_id": Sdf.ValueTypeNames.String,
}


def check_prim_attributes(prim: Usd.Prim, prim_path: str) -> dict:
    """
    プリムの属性をチェック

    Args:
        prim: チェック対象のプリム
        prim_path: プリムパス（表示用）

    Returns:
        dict: チェック結果
    """
    result = {
        "path": prim_path,
        "type": prim.GetTypeName(),
        "has_rigidbody": False,
        "has_collision": False,
        "missing_attrs": [],
        "invalid_attrs": [],
        "optional_attrs": [],
        "valid": True,
    }

    # 親にRigidBodyAPIがあるかチェック
    parent_prim = prim.GetParent()
    if parent_prim and parent_prim.IsValid():
        if parent_prim.HasAPI(UsdPhysics.RigidBodyAPI):
            result["has_rigidbody"] = True

    # CollisionAPIがあるかチェック
    if prim.HasAPI(UsdPhysics.CollisionAPI):
        result["has_collision"] = True

    # 必須属性をチェック
    for attr_name, expected_type in REQUIRED_ATTRIBUTES.items():
        attr = prim.GetAttribute(attr_name)

        if not attr:
            result["missing_attrs"].append(attr_name)
            result["valid"] = False
        elif not attr.HasValue():
            result["invalid_attrs"].append(f"{attr_name} (値なし)")
            result["valid"] = False
        else:
            # 型チェック
            actual_type = attr.GetTypeName()
            if actual_type != expected_type:
                result["invalid_attrs"].append(
                    f"{attr_name} (型不一致: {actual_type} != {expected_type})"
                )
                result["valid"] = False

    # オプション属性をチェック
    for attr_name, expected_type in OPTIONAL_ATTRIBUTES.items():
        attr = prim.GetAttribute(attr_name)
        if attr and attr.HasValue():
            result["optional_attrs"].append(attr_name)

    return result


def find_candidate_items(stage: Usd.Stage) -> list:
    """
    アイテム候補を検索

    TARGET_PATHSが指定されている場合はそのパスのプリムのみを返します。
    空の場合でSCAN_ALL_IF_EMPTYがTrueの場合は全オブジェクトをスキャンします。

    Args:
        stage: USDステージ

    Returns:
        list: 候補プリムのリスト
    """
    candidates = []

    # TARGET_PATHSが指定されている場合
    if TARGET_PATHS:
        print(f"指定されたパス数: {len(TARGET_PATHS)}")
        for path in TARGET_PATHS:
            prim = stage.GetPrimAtPath(path)
            if not prim.IsValid():
                print(f"⚠️  パスが無効: {path}")
                continue

            candidates.append(prim)
            print(f"✓ パス追加: {path}")

        return candidates

    # TARGET_PATHSが空で、SCAN_ALL_IF_EMPTYがTrueの場合
    if SCAN_ALL_IF_EMPTY:
        print("全オブジェクトをスキャン中...")
        target_types = ["Mesh", "Cube", "Sphere", "Cylinder"]

        for prim in stage.Traverse():
            if prim.GetTypeName() in target_types:
                # 親がXformであることを確認
                parent = prim.GetParent()
                if parent and parent.IsValid() and parent.GetTypeName() == "Xform":
                    candidates.append(prim)

        return candidates

    # どちらも該当しない場合
    print("⚠️  TARGET_PATHSが空で、SCAN_ALL_IF_EMPTY=Falseのため、チェック対象なし")
    return candidates


def print_result(result: dict):
    """
    チェック結果を表示

    Args:
        result: チェック結果辞書
    """
    status = "✓ OK" if result["valid"] else "❌ NG"
    print(f"\n{status} {result['path']}")
    print(f"  タイプ: {result['type']}")
    print(f"  親にRigidBody: {'あり' if result['has_rigidbody'] else 'なし'}")
    print(f"  Collision: {'あり' if result['has_collision'] else 'なし'}")

    if result["missing_attrs"]:
        print(f"  ❌ 欠落属性:")
        for attr in result["missing_attrs"]:
            print(f"    - {attr}")

    if result["invalid_attrs"]:
        print(f"  ❌ 無効属性:")
        for attr in result["invalid_attrs"]:
            print(f"    - {attr}")

    if result["optional_attrs"]:
        print(f"  オプション属性:")
        for attr in result["optional_attrs"]:
            print(f"    - {attr}")


def create_missing_attributes(prim: Usd.Prim, result: dict) -> bool:
    """
    欠落している属性を作成（オプション機能）

    Args:
        prim: 対象プリム
        result: チェック結果

    Returns:
        bool: 成功した場合True
    """
    print(f"\n🔧 属性を作成中: {result['path']}")

    try:
        for attr_name in result["missing_attrs"]:
            expected_type = REQUIRED_ATTRIBUTES[attr_name]

            # デフォルト値を設定
            default_values = {
                "custom:Number": 0,
                "custom:placed": False,
                "custom:task": False,
                "custom:original_position": (0.0, 0.0, 0.0),
                "custom:proxy": False,
                "custom:grab": True,
            }

            attr = prim.CreateAttribute(attr_name, expected_type)
            attr.Set(default_values[attr_name])
            print(f"  ✓ 作成: {attr_name} = {default_values[attr_name]}")

        return True

    except Exception as e:
        print(f"  ❌ エラー: {e}")
        return False


def main():
    """メイン処理"""
    print("=" * 70)
    print("アイテム設定属性チェックスクリプト")
    print("=" * 70)

    # ステージ取得
    usd_context = omni.usd.get_context()
    stage = usd_context.get_stage()

    if not stage:
        print("❌ ステージが開かれていません")
        return

    print(f"\nステージ: {stage.GetRootLayer().identifier}")

    # モード表示
    if TARGET_PATHS:
        print(f"\nモード: 指定パスチェック")
        print(f"対象パス数: {len(TARGET_PATHS)}")
    elif SCAN_ALL_IF_EMPTY:
        print(f"\nモード: 全オブジェクトスキャン")
    else:
        print(f"\nモード: チェック対象なし")

    # アイテム候補を検索
    print("\n--- アイテム候補を検索中... ---")
    candidates = find_candidate_items(stage)
    print(f"\n検出: {len(candidates)}個の候補")

    if not candidates:
        print("アイテム候補が見つかりませんでした")
        return

    # 各候補をチェック
    results = []
    for prim in candidates:
        result = check_prim_attributes(prim, str(prim.GetPath()))
        results.append(result)
        print_result(result)

    # サマリー
    print("\n" + "=" * 70)
    print("チェック結果サマリー")
    print("=" * 70)

    valid_count = sum(1 for r in results if r["valid"])
    invalid_count = len(results) - valid_count

    print(f"総候補数: {len(results)}")
    print(f"✓ 有効: {valid_count}")
    print(f"❌ 無効: {invalid_count}")

    # 無効なアイテムがある場合、修正オプションを提示
    if invalid_count > 0:
        print("\n--- 修正オプション ---")
        print("無効なアイテムに対して属性を自動作成しますか？")
        print("警告: この操作はUSDステージを変更します。")

        response = input("実行する場合は 'yes' と入力: ")

        if response.lower() == "yes":
            print("\n🔧 属性を作成中...")
            for prim, result in zip(candidates, results):
                if not result["valid"] and result["missing_attrs"]:
                    create_missing_attributes(prim, result)

            print("\n✓ 属性作成完了")
            print("再度チェックを実行してください。")
        else:
            print("キャンセルしました。")
    else:
        print("\n✓ すべてのアイテムが有効です！")


if __name__ == "__main__":
    main()


# ========================================
# 実行方法
# ========================================
# 1. Omniverseでステージを開く
# 2. Script Editorを開く (Window > Script Editor)
# 3. 以下のコードを実行:
#
#    exec(open("C:/users/nryou/documents/omniverse/zemiproject/kit-app-template/check_item_attributes.py").read())
#
# または、Pythonコンソールから:
#    import sys
#    sys.path.append("C:/users/nryou/documents/omniverse/zemiproject/kit-app-template")
#    import check_item_attributes
#    check_item_attributes.main()
#
# ========================================
