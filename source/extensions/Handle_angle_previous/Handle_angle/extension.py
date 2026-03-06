import omni.ext
import omni.usd
import omni.kit.app
import omni.timeline
import carb
import time
import math
from pxr import Gf, Sdf, UsdGeom

class HandleDriveExtension(omni.ext.IExt):
    def on_startup(self, ext_id):
        print("[HandleDriveExtension] Startup")
        self._timeline = omni.timeline.get_timeline_interface()
        self._last_log_time = time.time()

        self._handle_path = "/World/MillingMachine/Armature_002/Handle_Right/Cylinder_008"
        self._table_path = "/World/MillingMachine/Armature_002/Table/Cube_003"
        self._pivot_path = "/World/Handle_left_pivot"

        self._gauge = 0
        self._step_threshold = 15.0
        self._prev_pos = None
        self._subscription = None

        self._stage = omni.usd.get_context().get_stage()
        if self._stage:
            self._initialize_after_stage_loaded()

        omni.usd.get_context().get_stage_event_stream().create_subscription_to_pop(self._on_stage_event)

    def on_shutdown(self):
        if self._subscription:
            self._subscription.unsubscribe()
            self._subscription = None

    def _initialize_after_stage_loaded(self):
        self._prev_pos = self._get_xz_position(self._handle_path)
        self._subscription = omni.kit.app.get_app().get_update_event_stream().create_subscription_to_pop(self._on_update)

    def _on_stage_event(self, e):
        if e.type == int(omni.usd.StageEventType.OPENED):
            self._stage = omni.usd.get_context().get_stage()
            self._initialize_after_stage_loaded()

    def _on_update(self, e):
        if not self._timeline.is_playing():
            return

        handle_pos = self._get_xz_position(self._handle_path)
        pivot_pos = self._get_xz_position(self._pivot_path)
        if self._prev_pos is None or handle_pos is None or pivot_pos is None:
            return

        angle = self._calculate_angle_deg(self._prev_pos, pivot_pos, handle_pos)

        table_prim = self._stage.GetPrimAtPath(Sdf.Path(self._table_path))
        if not table_prim:
            return

        translate_attr = table_prim.GetAttribute("xformOp:translate")
        if not translate_attr:
            return

        current_pos = translate_attr.Get()
        y = current_pos[1]
        moved = False

        #print(f"prev.pos:{self._prev_pos}, Current.pos:{handle_pos}")

        if angle >= self._step_threshold and self._gauge < 20:
            print(str(angle) + "Count Up!!!")
            print(f"prev.pos:{self._prev_pos}, Current.pos:{handle_pos}")
            self._gauge += 1
            y += 0.02
            self._prev_pos = handle_pos
            moved = True
        elif angle <= -self._step_threshold and self._gauge > -20:
            print(str(angle) + "Count Down!!!")
            print(f"prev.pos:{self._prev_pos}, Current.pos:{handle_pos}")
            self._gauge -= 1
            y -= 0.02
            self._prev_pos = handle_pos
            moved = True

        if moved:
            translate_attr.Set(Gf.Vec3f(current_pos[0], y, current_pos[2]))

        now = time.time()
        if now - self._last_log_time > 1.0:
            carb.log_info(f"Angle: {angle:.2f}, Gauge: {self._gauge}, Y: {y:.2f}")
            self._last_log_time = now

    def _get_xz_position(self, path):
        prim = self._stage.GetPrimAtPath(Sdf.Path(path))
        if not prim or not prim.IsValid():
            return None
        xform = UsdGeom.Xformable(prim)
        transform = xform.ComputeLocalToWorldTransform(0.0)
        pos = transform.ExtractTranslation()
        return (pos[1], pos[2])

    def _calculate_angle_deg(self, p1, center, p2):
        v1 = (p1[0] - center[0], p1[1] - center[1])
        v2 = (p2[0] - center[0], p2[1] - center[1])

        v1_length = math.hypot(*v1)
        v2_length = math.hypot(*v2)
        if v1_length == 0 or v2_length == 0:
            return 0.0

        v1_unit = (v1[0] / v1_length, v1[1] / v1_length)
        v2_unit = (v2[0] / v2_length, v2[1] / v2_length)

        dot = v1_unit[0] * v2_unit[0] + v1_unit[1] * v2_unit[1]
        cross = v1_unit[0] * v2_unit[1] - v1_unit[1] * v2_unit[0]

        angle_rad = math.atan2(cross, dot)
        return math.degrees(angle_rad)
