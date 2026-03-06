from pxr import Usd, UsdPhysics, Sdf
import omni.usd

# Stageを取得
context = omni.usd.get_context()
stage = context.get_stage()

if not stage:
    print("エラー: Stageが開かれていません")
    exit(1)

# handle_drillのパスを探す
handle_drill_paths = [
    "/World/New_MillingMachine/Main/Handle_Dril",
    "/World/New_MillingMachine/Main/handle_drill",
    "/World/New_MillingMachine/Main/Doril/Drill/Handle_Dril"
]

handle_prim = None
for path in handle_drill_paths:
    prim = stage.GetPrimAtPath(path)
    if prim.IsValid():
        handle_prim = prim
        print(f"✓ Handle Prim発見: {path}")
        break

if not handle_prim:
    print("⚠️ handle_drillが見つかりません")
    print("ステージ内のPrimをリスト:")
    for prim in stage.Traverse():
        if "handle" in str(prim.GetPath()).lower() or "dril" in str(prim.GetPath()).lower():
            print(f"  - {prim.GetPath()}")
    exit(1)

# カスタム属性をチェック
print("\n=== カスタム属性チェック ===")
disable_drive_attr = handle_prim.GetAttribute("custom:disable_drive")
if disable_drive_attr:
    value = disable_drive_attr.Get()
    print(f"custom:disable_drive: {value}")
else:
    print("custom:disable_drive: 属性なし")

# RevoluteJointを探す
print("\n=== RevoluteJoint検索 ===")
handle_path = str(handle_prim.GetPath())
joints_found = []

for prim in stage.Traverse():
    if prim.IsA(UsdPhysics.RevoluteJoint):
        joint = UsdPhysics.RevoluteJoint(prim)
        body0_rel = joint.GetBody0Rel()
        body1_rel = joint.GetBody1Rel()
        
        body0_targets = [str(t) for t in body0_rel.GetTargets()] if body0_rel else []
        body1_targets = [str(t) for t in body1_rel.GetTargets()] if body1_rel else []
        
        if handle_path in body0_targets or handle_path in body1_targets:
            joints_found.append(prim)
            print(f"✓ 接続されたRevoluteJoint発見: {prim.GetPath()}")
            print(f"  Body0: {body0_targets}")
            print(f"  Body1: {body1_targets}")
            
            # 軸を確認
            axis_attr = joint.GetAxisAttr()
            if axis_attr:
                print(f"  Axis: {axis_attr.Get()}")
            
            # custom:disable_drive属性をチェック
            joint_disable_attr = prim.GetAttribute("custom:disable_drive")
            if joint_disable_attr:
                print(f"  Joint's custom:disable_drive: {joint_disable_attr.Get()}")
            else:
                print(f"  Joint's custom:disable_drive: 属性なし")

if not joints_found:
    print("⚠️ このオブジェクトに接続されたRevoluteJointが見つかりません")

print("\n=== 診断完了 ===")
