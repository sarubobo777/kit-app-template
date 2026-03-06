# trigger_script.py (物理状態リセット機能付き)
import sys
import carb
from pxr import Usd, UsdGeom, UsdUtils, UsdPhysics, Sdf, Gf

FOLLOWING_ATTR_NAME = "custom:isFollowing"
FOLLOWING_ATTR_TYPE = Sdf.ValueTypeNames.String
IMMOBILIZE_REQUEST_ATTR_NAME = "custom:requestingImmobilize"

# (handle_enter_event関数は変更ありません。見やすさのため省略します)
def handle_enter_event(stage, trigger_path, other_path):
    if not str(other_path).startswith("/World/items/"):
        carb.log_info(f"[my_extension_log] [TriggerScript] Skipped: '{other_path}' is not a target item.")
        return
    carb.log_info(f"[my_extension_log] [TriggerScript] Enter Event: '{other_path}' entered '{trigger_path}'")
    trigger_prim = stage.GetPrimAtPath(trigger_path)
    other_prim = stage.GetPrimAtPath(other_path)
    if not trigger_prim.IsValid() or not other_prim.IsValid(): return
    trigger_xform = UsdGeom.Xformable(trigger_prim)
    trigger_world_tf = trigger_xform.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
    trigger_world_pos = trigger_world_tf.ExtractTranslation()
    parent_prim = other_prim.GetParent()
    parent_world_tf = Gf.Matrix4d(1.0)
    if parent_prim and parent_prim.GetPath() != Sdf.Path.absoluteRootPath:
        parent_xform = UsdGeom.Xformable(parent_prim)
        parent_world_tf = parent_xform.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
    local_pos = parent_world_tf.GetInverse().Transform(trigger_world_pos)
    item_xform = UsdGeom.Xformable(other_prim)
    translate_op = item_xform.GetTranslateOp()
    if not translate_op:
        translate_op = item_xform.AddTranslateOp()
        item_xform.SetXformOpOrder([translate_op])
    translate_op.Set(local_pos)
    carb.log_info(f"[my_extension_log] [TriggerScript] Snapped '{other_path}' to trigger position instantly.")
    other_prim.CreateAttribute(FOLLOWING_ATTR_NAME, FOLLOWING_ATTR_TYPE, False).Set(str(trigger_path))
    rb_api = UsdPhysics.RigidBodyAPI.Get(stage, other_path)
    if rb_api:
        other_prim.CreateAttribute(IMMOBILIZE_REQUEST_ATTR_NAME, Sdf.ValueTypeNames.Bool, False).Set(True)
        carb.log_info(f"[my_extension_log] [TriggerScript] Set {IMMOBILIZE_REQUEST_ATTR_NAME}=True for '{other_path}'")
        prim = other_prim
        disable_gravity_attr = prim.CreateAttribute("physxRigidBody:disableGravity", Sdf.ValueTypeNames.Bool, False)
        disable_gravity_attr.Set(True)
        rb_api.GetVelocityAttr().Set(Gf.Vec3f(0, 0, 0))
        rb_api.GetAngularVelocityAttr().Set(Gf.Vec3f(0, 0, 0))
    else:
        carb.log_warn(f"[my_extension_log] [TriggerScript] No RigidBodyAPI found on '{other_path}'")


def handle_leave_event(stage, trigger_path, other_path):
    carb.log_warn("<<<<< LEAVE EVENT DETECTED! >>>>>")

    if not str(other_path).startswith("/World/items/"):
        return

    carb.log_info(f"[my_extension_log] [TriggerScript] Leave Event: '{other_path}' left '{trigger_path}'")
    other_prim = stage.GetPrimAtPath(other_path)
    if not other_prim.IsValid(): return

    # 追従と固定化の印を削除
    if other_prim.HasAttribute(FOLLOWING_ATTR_NAME): other_prim.RemoveProperty(FOLLOWING_ATTR_NAME)
    if other_prim.HasAttribute(IMMOBILIZE_REQUEST_ATTR_NAME): other_prim.RemoveProperty(IMMOBILIZE_REQUEST_ATTR_NAME)

    # 親の位置にスナップさせる
    parent_prim = other_prim.GetParent()
    if parent_prim and parent_prim.GetPath() != Sdf.Path.absoluteRootPath:
        item_xform = UsdGeom.Xformable(other_prim)
        translate_op = item_xform.GetTranslateOp()
        if not translate_op:
            translate_op = item_xform.AddTranslateOp()
            item_xform.SetXformOpOrder([translate_op])
        translate_op.Set(Gf.Vec3f(0, 0, 0))

    # 物理状態をリセット
    rb_api = UsdPhysics.RigidBodyAPI.Get(stage, other_path)
    if rb_api:
        # ▼▼▼【ここからが新規追加の処理です】▼▼▼
        # 速度と角速度をゼロにして、弾き飛ばされた勢いをキャンセルする
        rb_api.GetVelocityAttr().Set(Gf.Vec3f(0, 0, 0))
        rb_api.GetAngularVelocityAttr().Set(Gf.Vec3f(0, 0, 0))
        carb.log_info(f"[my_extension_log] [TriggerScript] Reset velocity for '{other_path}'.")
        # ▲▲▲ ここまで ▲▲▲

        # 重力を元に戻す
        prim = other_prim
        disable_gravity_attr = prim.GetAttribute("physxRigidBody:disableGravity")
        if disable_gravity_attr:
            disable_gravity_attr.Set(False)
    else:
        carb.log_warn(f"[my_extension_log] [TriggerScript] No RigidBodyAPI found on '{other_path}'")

# (main関数は変更ありません)
def main():
    if len(sys.argv) < 5: return
    try:
        stage_id = int(sys.argv[1])
        trigger_path_str = sys.argv[2]
        other_path_str = sys.argv[3]
        event_name = sys.argv[4]
    except (ValueError, IndexError): return
    cache = UsdUtils.StageCache.Get()
    stage = cache.Find(Usd.StageCache.Id.FromLongInt(stage_id))
    if not stage: return
    trigger_path = Sdf.Path(trigger_path_str)
    other_path = Sdf.Path(other_path_str)
    if event_name == "EnterEvent": handle_enter_event(stage, trigger_path, other_path)
    elif event_name == "LeaveEvent": handle_leave_event(stage, trigger_path, other_path)
main()