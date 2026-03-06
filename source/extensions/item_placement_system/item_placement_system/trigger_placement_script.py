"""
Trigger Placement Script (Simplified Version)
トリガーベースのアイテム配置システム用スクリプト

このスクリプトはPhysX Triggerから呼び出され、アイテムの正誤判定と配置を実行します。
親Prim（Xformタイプ）に対して操作を行います。
"""

import os
import sys
import carb
import omni.physx
from pxr import Usd, UsdUtils, UsdGeom, UsdPhysics, Sdf, Gf

LOG_PREFIX = "[ItemPlacement][TriggerScript]"

# デバッグフラグ
DEBUG_MODE = True


def debug_log(message: str):
    """デバッグログ出力"""
    if DEBUG_MODE:
        carb.log_info(f"{LOG_PREFIX} [DEBUG] {message}")


def get_item_number(stage, item_path) -> int:
    """
    アイテムのNumber属性を取得

    Args:
        stage: USD Stage
        item_path: アイテムのパス

    Returns:
        int: Number属性の値。見つからない場合は-1
    """
    try:
        item_prim = stage.GetPrimAtPath(item_path)
        if not item_prim.IsValid():
            return -1

        # Number属性を取得
        number_attr = item_prim.GetAttribute("Number")
        if not number_attr.IsValid():
            # custom:Number も試す
            number_attr = item_prim.GetAttribute("custom:Number")

        if not number_attr.IsValid():
            return -1

        return number_attr.Get()

    except Exception as e:
        carb.log_error(f"{LOG_PREFIX} Error getting item number: {e}")
        return -1


def get_parent_xform(stage, item_path):
    """
    アイテムの親Prim（Xformタイプ）を取得

    Args:
        stage: USD Stage
        item_path: アイテムのパス

    Returns:
        Prim: 親XformのPrim、見つからない場合はNone
    """
    try:
        item_prim = stage.GetPrimAtPath(item_path)
        if not item_prim.IsValid():
            return None

        # 親を取得
        parent_prim = item_prim.GetParent()
        if not parent_prim or not parent_prim.IsValid():
            carb.log_warn(f"{LOG_PREFIX} No valid parent for {item_path}")
            return None

        # Xformableかチェック
        if parent_prim.IsA(UsdGeom.Xformable):
            debug_log(f"Found parent Xform: {parent_prim.GetPath()}")
            return parent_prim
        else:
            carb.log_warn(f"{LOG_PREFIX} Parent is not Xformable: {parent_prim.GetPath()}")
            return None

    except Exception as e:
        carb.log_error(f"{LOG_PREFIX} Error getting parent xform: {e}")
        return None


def get_rigidbody_prim(stage, parent_prim):
    """
    RigidBodyAPIを持つPrimを取得（親または子から探す）

    Args:
        stage: USD Stage
        parent_prim: 親Prim

    Returns:
        tuple: (RigidBodyAPIを持つPrim, RigidBodyAPI) または (None, None)
    """
    try:
        # まず親PrimにRigidBodyAPIがあるかチェック
        rb_api = UsdPhysics.RigidBodyAPI.Get(stage, parent_prim.GetPath())
        if rb_api:
            debug_log(f"Found RigidBodyAPI on parent: {parent_prim.GetPath()}")
            return parent_prim, rb_api

        # 子Primを探す
        for child in parent_prim.GetChildren():
            rb_api = UsdPhysics.RigidBodyAPI.Get(stage, child.GetPath())
            if rb_api:
                debug_log(f"Found RigidBodyAPI on child: {child.GetPath()}")
                return child, rb_api

        debug_log(f"No RigidBodyAPI found on {parent_prim.GetPath()} or its children")
        return None, None

    except Exception as e:
        carb.log_error(f"{LOG_PREFIX} Error finding RigidBody: {e}")
        return None, None


def get_trigger_config(stage, trigger_path):
    """
    トリガーの設定情報を取得

    Args:
        stage: USD Stage
        trigger_path: トリガーのパス

    Returns:
        dict: トリガー設定情報
    """
    trigger_prim = stage.GetPrimAtPath(trigger_path)
    if not trigger_prim.IsValid():
        return None

    config = {
        "correct_numbers": [],
        "translate_correct": Gf.Vec3f(0, 0, 0),
        "rotate_correct": Gf.Vec3f(0, 0, 0),
        "translate_wrong": Gf.Vec3f(0, 0, 0),
        "rotate_wrong": Gf.Vec3f(0, 0, 0),
        "use_proxy": False,
        "real_object_path": None,
        "task_required": False,
        "slot_id": None,
    }

    # 正解のNumber値リストを取得
    correct_numbers_attr = trigger_prim.GetAttribute("custom:correct_numbers")
    if correct_numbers_attr.IsValid():
        correct_numbers = correct_numbers_attr.Get()
        if correct_numbers:
            config["correct_numbers"] = list(correct_numbers)

    # 正解時の配置位置を取得
    translate_correct_attr = trigger_prim.GetAttribute("custom:placement_translate")
    if translate_correct_attr.IsValid():
        translate = translate_correct_attr.Get()
        if translate:
            config["translate_correct"] = Gf.Vec3f(translate[0], translate[1], translate[2])

    # 正解時の回転角度を取得（度数法）
    rotate_correct_attr = trigger_prim.GetAttribute("custom:placement_rotate")
    if rotate_correct_attr.IsValid():
        rotate = rotate_correct_attr.Get()
        if rotate:
            config["rotate_correct"] = Gf.Vec3f(rotate[0], rotate[1], rotate[2])

    # 不正解時のリセット位置を取得（オプション）
    translate_wrong_attr = trigger_prim.GetAttribute("custom:translate_wrong")
    if translate_wrong_attr.IsValid():
        translate = translate_wrong_attr.Get()
        if translate:
            config["translate_wrong"] = Gf.Vec3f(translate[0], translate[1], translate[2])

    # 不正解時のリセット回転角度を取得（度数法）
    rotate_wrong_attr = trigger_prim.GetAttribute("custom:rotate_wrong")
    if rotate_wrong_attr.IsValid():
        rotate = rotate_wrong_attr.Get()
        if rotate:
            config["rotate_wrong"] = Gf.Vec3f(rotate[0], rotate[1], rotate[2])

    # Proxy使用フラグ
    proxy_path_attr = trigger_prim.GetAttribute("custom:proxy_path")
    real_path_attr = trigger_prim.GetAttribute("custom:real_path")
    if proxy_path_attr.IsValid() and real_path_attr.IsValid():
        proxy_path = proxy_path_attr.Get()
        real_path = real_path_attr.Get()
        if proxy_path and real_path:
            config["use_proxy"] = True
            config["real_object_path"] = real_path

    # タスク必須フラグ
    task_type_attr = trigger_prim.GetAttribute("custom:task_type")
    if task_type_attr.IsValid():
        task_type = task_type_attr.Get()
        if task_type and task_type != "none":
            config["task_required"] = True

    # Slot ID取得
    slot_id_attr = trigger_prim.GetAttribute("custom:slot_id")
    if slot_id_attr.IsValid():
        slot_id = slot_id_attr.Get()
        if slot_id:
            config["slot_id"] = slot_id

    debug_log(f"Trigger config: {config}")
    return config


def set_rigidbody_enabled(stage, parent_prim, enabled: bool):
    """
    親Primまたはその子のRigidBodyを有効/無効化
    無効化すると、RigidBodyの物理演算が停止し、コライダーは静的コライダーとして機能する

    公式ドキュメント: https://docs.omniverse.nvidia.com/kit/docs/omni_physics/latest/dev_guide/rigid_bodies_articulations/rigid_bodies.html

    Args:
        stage: USD Stage
        parent_prim: 親Prim
        enabled: True=有効（物理演算あり）, False=無効（静的コライダー化、Raycast検出可能）
    """
    try:
        # RigidBodyAPIを持つPrimを探す
        rb_prim, rb_api = get_rigidbody_prim(stage, parent_prim)

        if not rb_api:
            debug_log(f"No RigidBodyAPI found, skipping rigidbody setting for {parent_prim.GetPath()}")
            return

        # 直接USD属性としてアクセス（APIメソッドが存在しない古いバージョン対応）
        # 属性名: physics:rigidBodyEnabled
        rb_enabled_attr = rb_prim.GetAttribute("physics:rigidBodyEnabled")

        if rb_enabled_attr and rb_enabled_attr.IsValid():
            # 既存の属性を設定
            rb_enabled_attr.Set(enabled)
            carb.log_info(f"{LOG_PREFIX} Set physics:rigidBodyEnabled={enabled} for {rb_prim.GetPath()}")
        else:
            # 属性が存在しない場合は作成
            rb_enabled_attr = rb_prim.CreateAttribute("physics:rigidBodyEnabled", Sdf.ValueTypeNames.Bool, False)
            rb_enabled_attr.Set(enabled)
            carb.log_info(f"{LOG_PREFIX} Created physics:rigidBodyEnabled={enabled} for {rb_prim.GetPath()}")

    except Exception as e:
        carb.log_error(f"{LOG_PREFIX} Error setting rigidBodyEnabled: {e}")
        import traceback
        traceback.print_exc()


def set_translate(stage, parent_prim, position: Gf.Vec3f):
    """
    親PrimのTranslate属性を設定
    RigidBodyがある場合はPhysX simulation stateも更新する

    重要：XformOpOrderを常に正しい順序（Scale→Rotate→Translate）に保ちます。

    Args:
        stage: USD Stage
        parent_prim: 親Prim
        position: 移動先座標
    """
    try:
        xformable = UsdGeom.Xformable(parent_prim)

        # 1. 既存の全てのXformOpを分類（opオブジェクト自体を保存）
        existing_ops = xformable.GetOrderedXformOps()
        scale_op = None
        rotate_op = None
        translate_op = None

        for op in existing_ops:
            op_type = op.GetOpType()
            if op_type == UsdGeom.XformOp.TypeScale:
                scale_op = op
            elif op_type == UsdGeom.XformOp.TypeRotateXYZ:
                rotate_op = op
            elif op_type == UsdGeom.XformOp.TypeTranslate:
                translate_op = op
            # 他のRotateタイプも保存（念のため）
            elif op_type in (UsdGeom.XformOp.TypeRotateX, UsdGeom.XformOp.TypeRotateY, UsdGeom.XformOp.TypeRotateZ):
                if rotate_op is None:  # 最初のRotate opのみ保存
                    rotate_op = op

        # 2. XformOpOrderをクリア（XformOp自体は削除しない）
        xformable.ClearXformOpOrder()
        debug_log(f"Cleared XformOpOrder to rebuild in correct order (Scale→Rotate→Translate)")

        # 3. Translate opを作成または再利用
        if translate_op is None:
            translate_op = xformable.AddTranslateOp()
            debug_log(f"Created new Translate op")
        else:
            debug_log(f"Reusing existing Translate op")

        translate_op.Set(position)
        debug_log(f"Set Translate op: {position}")

        # 4. SetXformOpOrderで正しい順序を指定（既存のopを再利用）
        new_order = []
        if scale_op:
            new_order.append(scale_op)
            debug_log(f"Reusing existing Scale op")
        if rotate_op:
            new_order.append(rotate_op)
            debug_log(f"Reusing existing Rotate op")
        new_order.append(translate_op)

        xformable.SetXformOpOrder(new_order)

        carb.log_info(f"{LOG_PREFIX} Set translate={position} for {parent_prim.GetPath()}")

        # RigidBodyAPIがある場合、PhysX interfaceを使用してシミュレーション状態を更新
        rb_prim, rb_api = get_rigidbody_prim(stage, parent_prim)
        if rb_api:
            try:
                physx_interface = omni.physx.get_physx_simulation_interface()
                if physx_interface:
                    prim_path = str(rb_prim.GetPath())

                    # 複数の方法を試す
                    position_carb = carb.Float3(float(position[0]), float(position[1]), float(position[2]))

                    # Method 1: attach_rigid_body (強制リロード)
                    if hasattr(physx_interface, 'attach_rigid_body'):
                        physx_interface.attach_rigid_body(prim_path)
                        debug_log(f"Attached RigidBody for {prim_path}")

                    # Method 2: force_load_physics_from_usd (USD属性を物理エンジンに反映)
                    if hasattr(physx_interface, 'force_load_physics_from_usd'):
                        physx_interface.force_load_physics_from_usd()
                        debug_log(f"Forced load physics from USD")

                    debug_log(f"Updated PhysX state for {prim_path}")

            except Exception as physx_error:
                debug_log(f"Could not update PhysX state directly (this is OK): {physx_error}")

    except Exception as e:
        carb.log_error(f"{LOG_PREFIX} Error setting translate: {e}")


def set_rotate(stage, parent_prim, rotation: Gf.Vec3f):
    """
    親PrimのRotate属性を設定（度数法のXYZ回転）
    RigidBodyがある場合はPhysX simulation stateも更新する

    重要：既存の全てのRotate opをクリアしてから新しい回転を設定します。
    これにより、角度の加算ではなく絶対値での設定を保証します。

    Args:
        stage: USD Stage
        parent_prim: 親Prim
        rotation: 回転角度（度数法、XYZ）の絶対値
    """
    try:
        xformable = UsdGeom.Xformable(parent_prim)

        # 1. 既存の全てのXformOpを分類（opオブジェクト自体を保存）
        existing_ops = xformable.GetOrderedXformOps()
        scale_op = None
        translate_op = None
        rotate_xyz_op = None

        for op in existing_ops:
            op_type = op.GetOpType()
            if op_type == UsdGeom.XformOp.TypeScale:
                scale_op = op
            elif op_type == UsdGeom.XformOp.TypeTranslate:
                translate_op = op
            elif op_type == UsdGeom.XformOp.TypeRotateXYZ:
                rotate_xyz_op = op

        # 2. XformOpOrderをクリア（XformOp自体は削除しない）
        xformable.ClearXformOpOrder()
        debug_log(f"Cleared XformOpOrder to rebuild in correct order (Scale→Rotate→Translate)")

        # 3. RotateXYZ opを作成または再利用
        if rotate_xyz_op is None:
            rotate_xyz_op = xformable.AddRotateXYZOp()
            debug_log(f"Created new RotateXYZ op")
        else:
            debug_log(f"Reusing existing RotateXYZ op")

        rotate_xyz_op.Set(rotation)
        debug_log(f"Set RotateXYZ op: {rotation}")

        # 4. SetXformOpOrderで正しい順序を指定（既存のopを再利用）
        new_order = []
        if scale_op:
            new_order.append(scale_op)
            debug_log(f"Reusing existing Scale op")
        new_order.append(rotate_xyz_op)
        if translate_op:
            new_order.append(translate_op)
            debug_log(f"Reusing existing Translate op")

        xformable.SetXformOpOrder(new_order)

        carb.log_info(f"{LOG_PREFIX} Set rotation={rotation} (absolute) for {parent_prim.GetPath()}")

        # RigidBodyAPIがある場合、PhysX interfaceを使用してシミュレーション状態を更新
        rb_prim, rb_api = get_rigidbody_prim(stage, parent_prim)
        if rb_api:
            try:
                physx_interface = omni.physx.get_physx_simulation_interface()
                if physx_interface:
                    prim_path = str(rb_prim.GetPath())

                    # Method 1: attach_rigid_body (強制リロード)
                    if hasattr(physx_interface, 'attach_rigid_body'):
                        physx_interface.attach_rigid_body(prim_path)
                        debug_log(f"Attached RigidBody for rotation update: {prim_path}")

                    # Method 2: force_load_physics_from_usd (USD属性を物理エンジンに反映)
                    if hasattr(physx_interface, 'force_load_physics_from_usd'):
                        physx_interface.force_load_physics_from_usd()
                        debug_log(f"Forced load physics from USD")

                    debug_log(f"Updated PhysX state for rotation: {prim_path}")

            except Exception as physx_error:
                debug_log(f"Could not update PhysX rotation state directly (this is OK): {physx_error}")

    except Exception as e:
        carb.log_error(f"{LOG_PREFIX} Error setting rotation: {e}")


def reset_velocities(stage, parent_prim):
    """
    親Primまたはその子の線形速度と角速度をゼロに設定

    Args:
        stage: USD Stage
        parent_prim: 親Prim
    """
    try:
        # RigidBodyAPIを持つPrimを探す
        rb_prim, rb_api = get_rigidbody_prim(stage, parent_prim)

        if not rb_api:
            debug_log(f"No RigidBodyAPI found, skipping velocity reset for {parent_prim.GetPath()}")
            return

        # USD属性をゼロに設定
        velocity_attr = rb_api.GetVelocityAttr()
        if velocity_attr:
            velocity_attr.Set(Gf.Vec3f(0, 0, 0))

        angular_velocity_attr = rb_api.GetAngularVelocityAttr()
        if angular_velocity_attr:
            angular_velocity_attr.Set(Gf.Vec3f(0, 0, 0))

        carb.log_info(f"{LOG_PREFIX} Reset velocities for {rb_prim.GetPath()}")

        # PhysX interfaceを使用してシミュレーション状態も更新を試みる
        try:
            physx_interface = omni.physx.get_physx_simulation_interface()
            if physx_interface:
                prim_path = str(rb_prim.GetPath())

                # attach_rigid_bodyで物理状態をリロード
                if hasattr(physx_interface, 'attach_rigid_body'):
                    physx_interface.attach_rigid_body(prim_path)
                    debug_log(f"Reattached RigidBody to reset velocities for {prim_path}")

        except Exception as physx_error:
            debug_log(f"Could not update PhysX velocities directly (this is OK): {physx_error}")

    except Exception as e:
        carb.log_error(f"{LOG_PREFIX} Error resetting velocities: {e}")


def set_placed_attribute(stage, parent_prim, placed: bool):
    """
    親PrimのPlaced属性を設定

    Args:
        stage: USD Stage
        parent_prim: 親Prim
        placed: True/False
    """
    try:
        placed_attr = parent_prim.GetAttribute("custom:placed")
        if not placed_attr:
            placed_attr = parent_prim.CreateAttribute("custom:placed", Sdf.ValueTypeNames.Bool, False)
        placed_attr.Set(placed)
        debug_log(f"Set placed={placed} for {parent_prim.GetPath()}")
    except Exception as e:
        carb.log_error(f"{LOG_PREFIX} Error setting placed attribute: {e}")


def set_task_attribute(stage, parent_prim, task_required: bool):
    """
    親PrimのTask属性を設定

    Args:
        stage: USD Stage
        parent_prim: 親Prim
        task_required: True=タスクあり（task=False）, False=タスクなし（task=True）
    """
    try:
        task_attr = parent_prim.GetAttribute("custom:task")
        if not task_attr:
            task_attr = parent_prim.CreateAttribute("custom:task", Sdf.ValueTypeNames.Bool, False)
        # タスクあり（True）→task=False、タスクなし（False）→task=True
        task_value = not task_required
        task_attr.Set(task_value)
        debug_log(f"Set task={task_value} (task_required={task_required}) for {parent_prim.GetPath()}")
    except Exception as e:
        carb.log_error(f"{LOG_PREFIX} Error setting task attribute: {e}")


def set_real_object_visible_and_collision(stage, real_object_path: str, visible: bool, collision: bool):
    """
    Real objectの表示とコリジョンを設定

    Args:
        stage: USD Stage
        real_object_path: Real objectのパス
        visible: True=inherited, False=invisible
        collision: True/False
    """
    try:
        real_prim = stage.GetPrimAtPath(real_object_path)
        if not real_prim or not real_prim.IsValid():
            carb.log_error(f"{LOG_PREFIX} Invalid real object path: {real_object_path}")
            return

        # Visibility設定
        imageable = UsdGeom.Imageable(real_prim)
        visibility_attr = imageable.GetVisibilityAttr()
        if visibility_attr:
            if visible:
                visibility_attr.Set(UsdGeom.Tokens.inherited)
            else:
                visibility_attr.Set(UsdGeom.Tokens.invisible)
            debug_log(f"Set visibility={'inherited' if visible else 'invisible'} for {real_object_path}")

        # Collision設定
        collision_api = UsdPhysics.CollisionAPI.Get(stage, real_object_path)
        if collision_api:
            collision_attr = collision_api.GetCollisionEnabledAttr()
            if collision_attr:
                collision_attr.Set(collision)
                debug_log(f"Set collisionEnabled={collision} for {real_object_path}")

        # Placed属性設定
        set_placed_attribute(stage, real_prim, visible)

    except Exception as e:
        carb.log_error(f"{LOG_PREFIX} Error setting real object properties: {e}")


def handle_incorrect_item(stage, parent_prim, translate_wrong: Gf.Vec3f, rotate_wrong: Gf.Vec3f):
    """
    不正解時の処理

    重要: PhysXシミュレーション中にRigidBodyの位置を変更するには、
    一度detachしてから位置を設定し、再度attachする必要があります。

    Args:
        stage: USD Stage
        parent_prim: 親Prim
        translate_wrong: リセット位置
        rotate_wrong: リセット回転角度（度数法、XYZ）
    """
    try:
        debug_log("JUDGMENT: INCORRECT ❌")

        # RigidBodyAPIを持つPrimを取得
        rb_prim, rb_api = get_rigidbody_prim(stage, parent_prim)

        # PhysX interfaceを取得
        physx_interface = omni.physx.get_physx_simulation_interface()

        # 方法1: RigidBodyを一度detachして位置変更後にreattach
        if rb_api and physx_interface:
            prim_path = str(rb_prim.GetPath())

            try:
                # Step 1: RigidBodyをdetach（物理シミュレーションから除外）
                if hasattr(physx_interface, 'detach_rigid_body'):
                    physx_interface.detach_rigid_body(prim_path)
                    debug_log(f"Detached RigidBody: {prim_path}")

                # Step 2: USD属性を設定（位置と回転、正しいXformOpOrder順序で）
                # set_rotate() を先に呼ぶことで、正しい順序（Scale→Rotate→Translate）を保証
                set_rotate(stage, parent_prim, rotate_wrong)
                set_translate(stage, parent_prim, translate_wrong)

                # Step 3: 速度をゼロに設定
                velocity_attr = rb_api.GetVelocityAttr()
                if velocity_attr:
                    velocity_attr.Set(Gf.Vec3f(0, 0, 0))

                angular_velocity_attr = rb_api.GetAngularVelocityAttr()
                if angular_velocity_attr:
                    angular_velocity_attr.Set(Gf.Vec3f(0, 0, 0))

                # Step 4: RigidBody無効化（固定）
                rb_enabled_attr = rb_api.GetRigidBodyEnabledAttr()
                if not rb_enabled_attr:
                    rb_enabled_attr = rb_api.CreateRigidBodyEnabledAttr()
                rb_enabled_attr.Set(False)
                carb.log_info(f"{LOG_PREFIX} Set rigidBodyEnabled=False for {rb_prim.GetPath()}")

                # Step 5: RigidBodyをreattach（物理シミュレーションに再登録）
                if hasattr(physx_interface, 'attach_rigid_body'):
                    physx_interface.attach_rigid_body(prim_path)
                    debug_log(f"Reattached RigidBody: {prim_path}")

                # Step 6: USD変更を強制的に物理エンジンに反映
                if hasattr(physx_interface, 'force_load_physics_from_usd'):
                    physx_interface.force_load_physics_from_usd()
                    debug_log(f"Forced physics reload from USD")

                carb.log_info(f"{LOG_PREFIX} ❌ INCORRECT! Item reset to {translate_wrong} (Kinematic=True)")

            except Exception as physx_error:
                carb.log_warn(f"{LOG_PREFIX} PhysX detach/reattach method failed: {physx_error}")
                # フォールバック: 従来の方法
                set_rigidbody_enabled(stage, parent_prim, False)
                set_translate(stage, parent_prim, translate_wrong)
                reset_velocities(stage, parent_prim)
                carb.log_info(f"{LOG_PREFIX} ❌ INCORRECT! Item reset using fallback method")
        else:
            # RigidBodyがない場合は単純に位置を変更
            set_translate(stage, parent_prim, translate_wrong)
            carb.log_info(f"{LOG_PREFIX} ❌ INCORRECT! Item reset to {translate_wrong} (No RigidBody)")

    except Exception as e:
        carb.log_error(f"{LOG_PREFIX} Error in handle_incorrect_item: {e}")
        import traceback
        traceback.print_exc()


def handle_correct_item_no_proxy(stage, parent_prim, translate_correct: Gf.Vec3f, rotate_correct: Gf.Vec3f, task_required: bool, slot_id: str = None):
    """
    正解時の処理（Proxy無し）

    Args:
        stage: USD Stage
        parent_prim: 親Prim（RigidBodyを持つXform）
        translate_correct: 配置位置
        rotate_correct: 配置時の回転角度（度数法、XYZ）
        task_required: タスク必須フラグ
        slot_id: スロットID
    """
    try:
        debug_log("JUDGMENT: CORRECT ✅ (No Proxy)")

        # 子Prim（Object）を取得（属性はObjectに設定する）
        object_prim = None
        for child in parent_prim.GetChildren():
            # CollisionAPIを持つ子を探す（Objectと想定）
            if child.HasAPI(UsdPhysics.CollisionAPI):
                object_prim = child
                break

        if not object_prim:
            # 子が見つからない場合は親に設定（後方互換性）
            object_prim = parent_prim
            debug_log(f"Warning: No child with CollisionAPI found, using parent_prim for attributes")

        # 0. 現在位置を original_position として保存（移動前）
        xformable = UsdGeom.Xformable(parent_prim)
        if xformable:
            current_transform = xformable.ComputeLocalToWorldTransform(0)
            current_pos = current_transform.ExtractTranslation()

            original_pos_attr = object_prim.GetAttribute("custom:original_position")
            if not original_pos_attr:
                original_pos_attr = object_prim.CreateAttribute("custom:original_position", Sdf.ValueTypeNames.Float3, False)
            original_pos_attr.Set(Gf.Vec3f(current_pos[0], current_pos[1], current_pos[2]))
            debug_log(f"Saved original_position on {object_prim.GetPath()}: {current_pos}")

        # 0-2. slot_id を保存
        if slot_id:
            slot_id_attr = object_prim.GetAttribute("custom:slot_id")
            if not slot_id_attr:
                slot_id_attr = object_prim.CreateAttribute("custom:slot_id", Sdf.ValueTypeNames.String, False)
            slot_id_attr.Set(slot_id)
            debug_log(f"Saved slot_id on {object_prim.GetPath()}: {slot_id}")

        # 1. rotate_correctに回転（先に設定して正しいXformOpOrder順序を保証）
        set_rotate(stage, parent_prim, rotate_correct)

        # 2. translate_correctに移動
        set_translate(stage, parent_prim, translate_correct)

        # 3. 速度をゼロにリセット
        reset_velocities(stage, parent_prim)

        # 4. RigidBody無効化（静的コライダー化、Raycast検出可能）
        set_rigidbody_enabled(stage, parent_prim, False)

        # 5. placed属性をObjectにTrueに
        set_placed_attribute(stage, object_prim, True)

        # 6. task属性をObjectに設定
        set_task_attribute(stage, object_prim, task_required)

        carb.log_info(f"{LOG_PREFIX} ✅ CORRECT! Item placed at {translate_correct}, rotation={rotate_correct}, task={task_required}, slot={slot_id}")
        carb.log_info(f"{LOG_PREFIX} Attributes set on Object: {object_prim.GetPath()}")

    except Exception as e:
        carb.log_error(f"{LOG_PREFIX} Error in handle_correct_item_no_proxy: {e}")
        import traceback
        traceback.print_exc()


def handle_correct_item_with_proxy(stage, parent_prim, real_object_path: str, task_required: bool, slot_id: str = None):
    """
    正解時の処理（Proxy有り）

    Args:
        stage: USD Stage
        parent_prim: プロキシの親Prim
        real_object_path: Real objectのパス
        task_required: タスク必須フラグ
        slot_id: スロットID
    """
    try:
        debug_log("JUDGMENT: CORRECT ✅ (With Proxy)")

        # 0. Proxyの元の位置を保存（移動前）
        xformable = UsdGeom.Xformable(parent_prim)
        if xformable:
            current_transform = xformable.ComputeLocalToWorldTransform(0)
            current_pos = current_transform.ExtractTranslation()
            proxy_original_pos = Gf.Vec3f(current_pos[0], current_pos[1], current_pos[2])
        else:
            proxy_original_pos = Gf.Vec3f(0, 0, 0)

        # 1. ProxyのRigidBody無効化（静的コライダー化）
        set_rigidbody_enabled(stage, parent_prim, False)

        # 2. Proxyを(0,0,0)に移動（隠す）
        set_translate(stage, parent_prim, Gf.Vec3f(0, 0, 0))

        # 3. Real objectを表示＆コリジョン有効化、placed=True
        set_real_object_visible_and_collision(stage, real_object_path, visible=True, collision=True)

        # 4. Real objectにUSD属性を保存
        real_prim = stage.GetPrimAtPath(real_object_path)
        if real_prim and real_prim.IsValid():
            # task属性
            set_task_attribute(stage, real_prim, task_required)

            # proxy_placed フラグ
            proxy_placed_attr = real_prim.GetAttribute("custom:proxy_placed")
            if not proxy_placed_attr:
                proxy_placed_attr = real_prim.CreateAttribute("custom:proxy_placed", Sdf.ValueTypeNames.Bool, False)
            proxy_placed_attr.Set(True)

            # proxy_path（親Primのパス）
            proxy_path_attr = real_prim.GetAttribute("custom:proxy_path")
            if not proxy_path_attr:
                proxy_path_attr = real_prim.CreateAttribute("custom:proxy_path", Sdf.ValueTypeNames.String, False)
            proxy_path_attr.Set(str(parent_prim.GetPath()))

            # original_position（proxyの元の位置）
            original_pos_attr = real_prim.GetAttribute("custom:original_position")
            if not original_pos_attr:
                original_pos_attr = real_prim.CreateAttribute("custom:original_position", Sdf.ValueTypeNames.Float3, False)
            original_pos_attr.Set(proxy_original_pos)

            # slot_id
            if slot_id:
                slot_id_attr = real_prim.GetAttribute("custom:slot_id")
                if not slot_id_attr:
                    slot_id_attr = real_prim.CreateAttribute("custom:slot_id", Sdf.ValueTypeNames.String, False)
                slot_id_attr.Set(slot_id)

            # placed属性
            placed_attr = real_prim.GetAttribute("custom:placed")
            if not placed_attr:
                placed_attr = real_prim.CreateAttribute("custom:placed", Sdf.ValueTypeNames.Bool, False)
            placed_attr.Set(True)

            debug_log(f"Saved proxy attributes on {real_object_path}: proxy_path={parent_prim.GetPath()}, original_pos={proxy_original_pos}, slot_id={slot_id}")

        # 5. ProxyにProxy配置情報を記録（シミュレーション停止時のクリーンアップ用）
        proxy_placed_attr_on_proxy = parent_prim.GetAttribute("custom:proxy_placed")
        if not proxy_placed_attr_on_proxy:
            proxy_placed_attr_on_proxy = parent_prim.CreateAttribute("custom:proxy_placed", Sdf.ValueTypeNames.Bool, False)
        proxy_placed_attr_on_proxy.Set(True)

        real_path_attr = parent_prim.GetAttribute("custom:real_object_path")
        if not real_path_attr:
            real_path_attr = parent_prim.CreateAttribute("custom:real_object_path", Sdf.ValueTypeNames.String, False)
        real_path_attr.Set(real_object_path)

        carb.log_info(f"{LOG_PREFIX} Set proxy_placed=True and real_object_path={real_object_path} on {parent_prim.GetPath()}")

        # 6. ProxyのRigidBody有効化（再度掴めるようにする）
        set_rigidbody_enabled(stage, parent_prim, True)

        carb.log_info(f"{LOG_PREFIX} ✅ CORRECT! Proxy hidden, Real object shown: {real_object_path}, task={task_required}, slot={slot_id}")

    except Exception as e:
        carb.log_error(f"{LOG_PREFIX} Error in handle_correct_item_with_proxy: {e}")
        import traceback
        traceback.print_exc()


def handle_enter_event(stage, trigger_path, item_path):
    """
    トリガーEnterイベントハンドラ

    Args:
        stage: USD Stage
        trigger_path: トリガーのパス
        item_path: 侵入したアイテムのパス
    """
    try:
        debug_log("="*60)
        debug_log(f"ENTER EVENT: {item_path} -> {trigger_path}")
        debug_log("="*60)

        # 1. アイテムのNumber属性を取得
        item_number = get_item_number(stage, item_path)
        if item_number == -1:
            carb.log_warn(f"{LOG_PREFIX} Item has no valid Number attribute: {item_path}")
            return

        debug_log(f"Item Number: {item_number}")

        # 2. 親Prim（Xform）を取得
        parent_prim = get_parent_xform(stage, item_path)
        if not parent_prim:
            carb.log_error(f"{LOG_PREFIX} Cannot find parent Xform for {item_path}")
            return

        # 3. トリガー設定を取得
        trigger_config = get_trigger_config(stage, trigger_path)
        if not trigger_config:
            carb.log_error(f"{LOG_PREFIX} Failed to get trigger config: {trigger_path}")
            return

        correct_numbers = trigger_config.get("correct_numbers", [])
        debug_log(f"Expected Numbers: {correct_numbers}")

        # 4. 正誤判定
        if item_number in correct_numbers:
            # 正解
            if trigger_config.get("use_proxy"):
                # Proxy有り
                handle_correct_item_with_proxy(
                    stage,
                    parent_prim,
                    trigger_config.get("real_object_path"),
                    trigger_config.get("task_required"),
                    trigger_config.get("slot_id")
                )
            else:
                # Proxy無し
                handle_correct_item_no_proxy(
                    stage,
                    parent_prim,
                    trigger_config.get("translate_correct"),
                    trigger_config.get("rotate_correct"),
                    trigger_config.get("task_required"),
                    trigger_config.get("slot_id")
                )
        else:
            # 不正解
            handle_incorrect_item(
                stage,
                parent_prim,
                trigger_config.get("translate_wrong"),
                trigger_config.get("rotate_wrong")
            )

        debug_log("="*60)

    except Exception as e:
        carb.log_error(f"{LOG_PREFIX} Error in handle_enter_event: {e}")
        import traceback
        traceback.print_exc()


def handle_leave_event(stage, trigger_path, item_path):
    """
    トリガーLeaveイベントハンドラ（現在は未使用）

    Args:
        stage: USD Stage
        trigger_path: トリガーのパス
        item_path: 退出したアイテムのパス
    """
    debug_log(f"LEAVE EVENT: {item_path} <- {trigger_path}")


def main():
    """
    メイン関数 - PhysXエンジンから呼び出される

    sys.argv:
        [1]: stage_id (int)
        [2]: trigger_path (string)
        [3]: item_path (string)
        [4]: event_name (string) - "EnterEvent" or "LeaveEvent"
    """
    try:
        # 引数チェック
        if len(sys.argv) < 5:
            carb.log_error(f"{LOG_PREFIX} Insufficient arguments: {len(sys.argv)}")
            return

        # 引数の解析
        stage_id = int(sys.argv[1])
        trigger_path_str = sys.argv[2]
        item_path_str = sys.argv[3]
        event_name = sys.argv[4]

        debug_log(f"Script called: stage_id={stage_id}, trigger={trigger_path_str}, item={item_path_str}, event={event_name}")

        # Stageの取得
        cache = UsdUtils.StageCache.Get()
        stage = cache.Find(Usd.StageCache.Id.FromLongInt(stage_id))
        if not stage:
            carb.log_error(f"{LOG_PREFIX} Stage not found for ID: {stage_id}")
            return

        # パスの変換
        trigger_path = Sdf.Path(trigger_path_str)
        item_path = Sdf.Path(item_path_str)

        # イベントタイプに応じた処理
        if event_name == "EnterEvent":
            handle_enter_event(stage, trigger_path, item_path)
        elif event_name == "LeaveEvent":
            handle_leave_event(stage, trigger_path, item_path)
        else:
            carb.log_warn(f"{LOG_PREFIX} Unknown event: {event_name}")

    except ValueError as e:
        carb.log_error(f"{LOG_PREFIX} Argument parsing error: {e}")
    except Exception as e:
        carb.log_error(f"{LOG_PREFIX} Unexpected error in main: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
