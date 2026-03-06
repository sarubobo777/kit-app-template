## FINAL VERSION - 2025/07/01 (シンプルリセット版) ##
import omni.ext
import omni.usd
import omni.kit.app
import omni.timeline
import carb
from pxr import Usd, UsdPhysics, PhysxSchema, UsdGeom, Sdf, Gf

class HybridTriggerExtension(omni.ext.IExt):
    def on_startup(self, ext_id: str):
        print("[my_extension_log] [HybridTriggerExtension] Startup.")
        self._ext_id = ext_id
        self._timeline = omni.timeline.get_timeline_interface()
        self._was_playing = self._timeline.is_playing()

        # ▼▼▼【修正点】初期位置を記憶する必要がなくなったため、関連する変数を削除▼▼▼
        # self._initial_transforms = {}
        self._immobilize_timers = {}
        # ▲▲▲ ここまで ▲▲▲

        self._usd_context = omni.usd.get_context()
        self._last_known_stage_id = None

        self._update_sub = omni.kit.app.get_app().get_update_event_stream().create_subscription_to_pop(
            self._on_update, name="my_update_sub"
        )

    def on_shutdown(self):
        print("[my_extension_log] [HybridTriggerExtension] Shutdown.")
        if self._update_sub:
            self._update_sub.unsubscribe()
            self._update_sub = None
        self._immobilize_timers = None
        self._usd_context = None

    # ▼▼▼【修正点】この関数は全面的に書き換えられました▼▼▼
    def _restore_scene_state(self):
        """
        シミュレーション停止時に、/World/items以下の全物理オブジェクトを
        親の原点(translate 0,0,0)にリセットし、物理状態をクリーンアップする
        """
        print("[my_extension_log] [HybridTriggerExtension] _restore_scene_state CALLED (New Reset Logic).")
        stage = self._usd_context.get_stage()
        if not stage: return

        items_root_prim = stage.GetPrimAtPath("/World/items")
        if not items_root_prim:
            carb.log_warn("[my_extension_log] Prim at '/World/items' not found. Skipping restore.")
            return

        print("[my_extension_log] Resetting all items under /World/items...")
        # /World/items以下をスキャン
        for prim in Usd.PrimRange(items_root_prim):
            # 物理オブジェクトのみを対象とする
            if prim.HasAPI(UsdPhysics.RigidBodyAPI):

                # 1. ローカルのTranslateを(0,0,0)に設定
                item_xform = UsdGeom.Xformable(prim)
                translate_op = item_xform.GetTranslateOp()
                if not translate_op:
                    translate_op = item_xform.AddTranslateOp()
                    item_xform.SetXformOpOrder([translate_op])
                translate_op.Set(Gf.Vec3f(0, 0, 0))

                # 2. カスタム属性のクリーンアップ
                if prim.HasAttribute("custom:isFollowing"): prim.RemoveProperty("custom:isFollowing")
                if prim.HasAttribute("custom:requestingImmobilize"): prim.RemoveProperty("custom:requestingImmobilize")

                # 3. 物理オーバーライド属性のクリーンアップ
                disable_sim_attr = prim.GetAttribute("physxRigidBody:disableSimulation")
                if disable_sim_attr:
                    disable_sim_attr.Set(False)

                disable_gravity_attr = prim.GetAttribute("physxRigidBody:disableGravity")
                if disable_gravity_attr:
                    disable_gravity_attr.Set(False)

        # タイマーリストをクリア
        self._immobilize_timers.clear()
        print("[my_extension_log] [HybridTriggerExtension] All items have been reset.")
    # ▲▲▲ ここまで ▲▲▲

    # ▼▼▼【修正点】この関数は不要になったため削除しました▼▼▼
    # def _capture_initial_transforms(self):
    # ▲▲▲ ここまで ▲▲▲

    def _on_update(self, e: carb.events.IEvent):
        stage = self._usd_context.get_stage()
        if stage:
            current_stage_id = stage.GetRootLayer().identifier
            if self._last_known_stage_id != current_stage_id:
                print(f"[my_extension_log] [HybridTriggerExtension] New stage detected (ID: {current_stage_id}), initializing...")
                self._initialize_trigger_setup(stage)
                self._last_known_stage_id = current_stage_id

        is_playing = self._timeline.is_playing()

        # ▼▼▼【修正点】ロジックをシンプルに変更▼▼▼
        if not is_playing and self._was_playing:
            # 再生状態から停止状態に切り替わった最初のフレームでのみ、後片付けを実行
            self._restore_scene_state()

        self._was_playing = is_playing

        if not is_playing:
            return
        # ▲▲▲ ここまで ▲▲▲

        if not stage: return

        selection = self._usd_context.get_selection()
        selected_paths = selection.get_selected_prim_paths()
        current_time = self._timeline.get_current_time()

        expired_timers = []
        for path_str, expiry_time in self._immobilize_timers.items():
            if current_time >= expiry_time:
                prim = stage.GetPrimAtPath(path_str)
                if prim.IsValid():
                    disable_sim_attr = prim.GetAttribute("physxRigidBody:disableSimulation")
                    if disable_sim_attr:
                        disable_sim_attr.Set(False)
                    print(f"[my_extension_log] [HybridTriggerExtension] Immobilize timer expired. Set disableSimulation=False for {path_str}")
                expired_timers.append(path_str)
        for path_str in expired_timers:
            if path_str in self._immobilize_timers: del self._immobilize_timers[path_str]

        items_root_prim = stage.GetPrimAtPath("/World/items")
        if not items_root_prim: return

        for prim in Usd.PrimRange(items_root_prim):
            if prim.HasAttribute("custom:requestingImmobilize"):
                prim.CreateAttribute("physxRigidBody:disableSimulation", Sdf.ValueTypeNames.Bool, False).Set(True)
                self._immobilize_timers[str(prim.GetPath())] = current_time + 1.0
                prim.RemoveProperty("custom:requestingImmobilize")
                print(f"[my_extension_log] [HybridTriggerExtension] Immobilize request detected. Set disableSimulation=True for {prim.GetPath()} and started 1s timer.")
            if prim.HasAttribute("custom:isFollowing"):
                if str(prim.GetPath()) in selected_paths:
                    continue
                following_attr = prim.GetAttribute("custom:isFollowing")
                trigger_path_str = following_attr.Get()
                if not trigger_path_str: continue
                trigger_prim = stage.GetPrimAtPath(trigger_path_str)
                if trigger_prim.IsValid():
                    if str(prim.GetPath()) not in self._immobilize_timers:
                        self._update_item_transform(trigger_prim, prim)

    # (以降の関数は変更ありません。見やすさのため省略します)
    def _initialize_trigger_setup(self, stage):
        print("[my_extension_log] [HybridTriggerExtension] _initialize_trigger_setup CALLED.")
        if not stage: return
        trigger_path_str = "/World/MillingMachine/TriggerBox"
        trigger_prim = stage.GetPrimAtPath(trigger_path_str)
        if not trigger_prim.IsValid():
            carb.log_warn(f"[my_extension_log] [HybridTriggerExtension] Trigger prim not found at '{trigger_path_str}'.")
            return
        script_path = r"C:\Users\nryou\Documents\Omniverse\zemiProject\kit-app-template\source\extensions\trigger_tracking\trigger_tracking\trigger_script.py"
        print(f"[my_extension_log] [HybridTriggerExtension] Setting up trigger '{trigger_path_str}' to run script: {script_path}")
        try:
            from pxr import PhysxSchema
            trigger_api = PhysxSchema.PhysxTriggerAPI.Apply(trigger_prim)
            trigger_api.CreateEnterScriptTypeAttr().Set(PhysxSchema.Tokens.scriptFile)
            trigger_api.CreateOnEnterScriptAttr().Set(script_path)
            trigger_api.CreateLeaveScriptTypeAttr().Set(PhysxSchema.Tokens.scriptFile)
            trigger_api.CreateOnLeaveScriptAttr().Set(script_path)
            print(f"[my_extension_log] [HybridTriggerExtension] Setup complete for trigger.")
        except ImportError:
            carb.log_error("[my_extension_log] [HybridTriggerExtension] Failed to import PhysxSchema. Make sure the Physics extension is enabled.")
    def _update_item_transform(self, trigger_prim, item_prim):
        trigger_xform = UsdGeom.Xformable(trigger_prim)
        trigger_world_tf = trigger_xform.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
        trigger_world_pos = trigger_world_tf.ExtractTranslation()
        parent_prim = item_prim.GetParent()
        parent_world_tf = Gf.Matrix4d(1.0)
        if parent_prim and parent_prim.GetPath() != Sdf.Path.absoluteRootPath:
            parent_xform = UsdGeom.Xformable(parent_prim)
            parent_world_tf = parent_xform.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
        local_pos = parent_world_tf.GetInverse().Transform(trigger_world_pos)
        item_xform = UsdGeom.Xformable(item_prim)
        translate_op = item_xform.GetTranslateOp()
        if not translate_op:
            translate_op = item_xform.AddTranslateOp()
            item_xform.SetXformOpOrder([translate_op])
        translate_op.Set(local_pos)