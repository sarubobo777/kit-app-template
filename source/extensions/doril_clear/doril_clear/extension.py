import omni.ext
import omni.kit.app
import omni.usd
import numpy as np
import carb
from pxr import Usd, UsdGeom, Gf, Sdf, UsdShade

LOG_PREFIX = "[my_extension][Doril_boolean]"

class DorilBooleanExtension(omni.ext.IExt):
    def on_startup(self, ext_id):
        print(f"{LOG_PREFIX} Extension starting up.")

        self._drill_path = "/World/Drill"
        self._metal_path = "/World/Metal"
        self._cube_counter = 0

        self._update_sub = omni.kit.app.get_app().get_update_event_stream().create_subscription_to_pop(
            self._on_update, name="realtime_fake_boolean"
        )

        self._last_drill_pos = None
        self._transparent_material_path = "/World/TransparentMaterial"

        print(f"{LOG_PREFIX} Ready. Drill: {self._drill_path}, Metal: {self._metal_path}")

    def on_shutdown(self):
        print(f"{LOG_PREFIX} Extension shutting down.")
        if self._update_sub:
            self._update_sub.unsubscribe()
            self._update_sub = None

    def _create_transparent_material(self, stage):
        mat_prim = stage.DefinePrim(self._transparent_material_path, "Material")
        material = UsdShade.Material(mat_prim)

        shader_path = self._transparent_material_path + "/Shader"
        shader_prim = stage.DefinePrim(shader_path, "Shader")
        shader = UsdShade.Shader(shader_prim)

        shader.CreateIdAttr("UsdPreviewSurface")
        shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set((1.0, 1.0, 1.0))
        shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(0.1)
        shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.2)
        shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)

        material.CreateSurfaceOutput().ConnectToSource(shader, "surface")
        return material

    def _on_update(self, e):
        stage = omni.usd.get_context().get_stage()
        if not stage:
            return

        drill_prim = stage.GetPrimAtPath(self._drill_path)
        metal_prim = stage.GetPrimAtPath(self._metal_path)
        if not drill_prim.IsValid() or not metal_prim.IsValid():
            return

        xform_cache = UsdGeom.XformCache()
        drill_transform = xform_cache.GetLocalToWorldTransform(drill_prim)
        drill_pos = drill_transform.ExtractTranslation()

        if self._last_drill_pos and (Gf.Vec3d(drill_pos) - self._last_drill_pos).GetLength() < 1.0:
            return
        self._last_drill_pos = Gf.Vec3d(drill_pos)

        bbox_cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "render"])
        if not bbox_cache.ComputeWorldBound(drill_prim).GetBox().IntersectWith(
            bbox_cache.ComputeWorldBound(metal_prim).GetBox()
        ):
            return

        cut_path = f"/World/CutCube_{self._cube_counter:03d}"
        self._cube_counter += 1
        cube = UsdGeom.Cube.Define(stage, cut_path)
        UsdGeom.XformCommonAPI(cube).SetTranslate(drill_pos)
        UsdGeom.XformCommonAPI(cube).SetScale(Gf.Vec3f(2.0, 2.0, 2.0))

        mat_prim = stage.GetPrimAtPath(self._transparent_material_path)
        if not mat_prim or not mat_prim.IsValid():
            self._create_transparent_material(stage)
            mat_prim = stage.GetPrimAtPath(self._transparent_material_path)

        material = UsdShade.Material(mat_prim)
        UsdShade.MaterialBindingAPI(cube).Bind(material)

        print(f"{LOG_PREFIX} Created cut cube at {cut_path} (pos={drill_pos})")
