# Tableのトランスフォーム情報を確認するスクリプト
import omni.usd
from pxr import UsdGeom, Gf

stage = omni.usd.get_context().get_stage()
table_path = "/World/New_MillingMachine/Table"
table_prim = stage.GetPrimAtPath(table_path)

if table_prim.IsValid():
    xformable = UsdGeom.Xformable(table_prim)
    
    # ローカルトランスフォーム
    local_transform = xformable.GetLocalTransformation()
    
    # ワールドトランスフォーム
    world_transform = xformable.ComputeLocalToWorldTransform(0)
    
    print(f"Table Transform Info:")
    print(f"Local Transform:\n{local_transform}")
    print(f"\nWorld Transform:\n{world_transform}")
    
    # スケール抽出
    scale = Gf.Vec3d()
    rotation = Gf.Rotation()
    translation = Gf.Vec3d()
    world_transform.Factor(scale, rotation, translation, Gf.Vec3d(0))
    
    print(f"\nDecomposed:")
    print(f"  Translation: {translation}")
    print(f"  Scale: {scale}")
    print(f"  Rotation: {rotation}")
else:
    print(f"Table not found at {table_path}")
