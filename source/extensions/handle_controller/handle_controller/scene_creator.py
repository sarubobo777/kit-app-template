"""
Scene Creator Module for Handle Controller Extension
Creates handles with revolute joints and target objects
"""

from pxr import Usd, UsdGeom, UsdPhysics, Gf, UsdShade, Sdf, PhysxSchema
import omni.usd
import carb
from typing import Tuple, Optional


class SceneCreator:
    """Helper class to create scene elements"""

    def __init__(self, stage: Usd.Stage):
        self.stage = stage

    def create_sample_scene(self):
        """Create a complete sample scene with 5 handles and targets"""
        carb.log_info("[SceneCreator] Creating sample scene...")

        # Create physics scene if not exists
        self._setup_physics_scene()

        # Create ground plane
        self._create_ground_plane()

        # Create 5 handles with their targets
        handle_configs = [
            {
                "position": Gf.Vec3f(-100, 0, 50),
                "color": Gf.Vec3f(1, 0, 0),  # Red
                "axis": Gf.Vec3f(1, 0, 0),
                "name": "Handle_1",
                "target_name": "Target_1"
            },
            {
                "position": Gf.Vec3f(-50, 0, 50),
                "color": Gf.Vec3f(0, 1, 0),  # Green
                "axis": Gf.Vec3f(0, 1, 0),
                "name": "Handle_2",
                "target_name": "Target_2"
            },
            {
                "position": Gf.Vec3f(0, 0, 50),
                "color": Gf.Vec3f(0, 0, 1),  # Blue
                "axis": Gf.Vec3f(0, 0, 1),
                "name": "Handle_3",
                "target_name": "Target_3"
            },
            {
                "position": Gf.Vec3f(50, 0, 50),
                "color": Gf.Vec3f(1, 1, 0),  # Yellow
                "axis": Gf.Vec3f(1, 1, 0).GetNormalized(),
                "name": "Handle_4",
                "target_name": "Target_4"
            },
            {
                "position": Gf.Vec3f(100, 0, 50),
                "color": Gf.Vec3f(1, 0, 1),  # Magenta
                "axis": Gf.Vec3f(1, 0, 1).GetNormalized(),
                "name": "Handle_5",
                "target_name": "Target_5"
            }
        ]

        for config in handle_configs:
            self._create_handle_and_target(
                handle_name=config["name"],
                target_name=config["target_name"],
                position=config["position"],
                color=config["color"],
                move_axis=config["axis"]
            )

        carb.log_info("[SceneCreator] Sample scene created successfully")

    def _setup_physics_scene(self):
        """Setup physics scene with proper settings"""
        # Check if physics scene exists
        physics_scene_path = "/World/PhysicsScene"
        physics_scene_prim = self.stage.GetPrimAtPath(physics_scene_path)

        if not physics_scene_prim or not physics_scene_prim.IsValid():
            # Create physics scene
            physics_scene = UsdPhysics.Scene.Define(self.stage, physics_scene_path)
            physics_scene.CreateGravityDirectionAttr(Gf.Vec3f(0, 0, -1))
            physics_scene.CreateGravityMagnitudeAttr(981)  # cm/s^2

            # Add PhysX-specific settings
            physx_scene = PhysxSchema.PhysxSceneAPI.Apply(physics_scene.GetPrim())
            physx_scene.CreateEnableGPUDynamicsAttr(False)
            physx_scene.CreateBroadphaseTypeAttr("MBP")
            physx_scene.CreateSolverTypeAttr("TGS")

    def _create_ground_plane(self):
        """Create a ground plane for the scene"""
        ground_path = "/World/GroundPlane"

        # Check if ground already exists
        if self.stage.GetPrimAtPath(ground_path):
            return

        # Create ground plane mesh
        ground_mesh = UsdGeom.Mesh.Define(self.stage, ground_path)

        # Define a large plane
        points = [
            Gf.Vec3f(-500, -500, 0),
            Gf.Vec3f(500, -500, 0),
            Gf.Vec3f(500, 500, 0),
            Gf.Vec3f(-500, 500, 0)
        ]
        ground_mesh.CreatePointsAttr(points)
        ground_mesh.CreateFaceVertexCountsAttr([4])
        ground_mesh.CreateFaceVertexIndicesAttr([0, 1, 2, 3])
        ground_mesh.CreateNormalsAttr([Gf.Vec3f(0, 0, 1)])

        # Add collision
        collision_api = UsdPhysics.CollisionAPI.Apply(ground_mesh.GetPrim())
        UsdPhysics.MeshCollisionAPI.Apply(ground_mesh.GetPrim())

        # Create material
        material = self._create_material("GroundMaterial", Gf.Vec3f(0.5, 0.5, 0.5))
        if material:
            UsdShade.MaterialBindingAPI(ground_mesh).Bind(material)

    def _create_handle_and_target(self, handle_name: str, target_name: str,
                                  position: Gf.Vec3f, color: Gf.Vec3f,
                                  move_axis: Gf.Vec3f):
        """Create a handle with revolute joint and its target object"""

        # Create handle assembly
        handle_base_path = f"/World/{handle_name}_Base"
        handle_path = f"/World/{handle_name}"
        target_path = f"/World/{target_name}"

        # Create base (fixed part)
        base = self._create_cylinder(
            handle_base_path,
            radius=3,
            height=10,
            position=position,
            color=Gf.Vec3f(0.3, 0.3, 0.3)
        )

        # Make base static
        rigid_body = UsdPhysics.RigidBodyAPI.Apply(base.GetPrim())
        rigid_body.CreateRigidBodyEnabledAttr(True)
        rigid_body.CreateKinematicEnabledAttr(True)  # Make it kinematic (fixed)

        # Create handle (rotating part)
        handle_position = position + Gf.Vec3f(0, 0, 15)
        handle = self._create_handle_geometry(
            handle_path,
            position=handle_position,
            color=color
        )

        # Add rigid body to handle
        handle_rigid = UsdPhysics.RigidBodyAPI.Apply(handle.GetPrim())
        handle_rigid.CreateRigidBodyEnabledAttr(True)

        # Create revolute joint between base and handle
        joint_path = f"/World/{handle_name}_Joint"
        joint = self._create_revolute_joint(
            joint_path,
            body0_path=handle_base_path,
            body1_path=handle_path,
            local_pos0=Gf.Vec3f(0, 0, 5),  # Top of base
            local_pos1=Gf.Vec3f(0, 0, -5),  # Bottom of handle
            axis=Gf.Vec3f(0, 0, 1)  # Rotate around Z axis
        )

        # Create target object
        target_position = position + Gf.Vec3f(0, 100, 0)
        target = self._create_cube(
            target_path,
            size=10,
            position=target_position,
            color=color
        )

        # Make target kinematic so it can be moved programmatically
        target_rigid = UsdPhysics.RigidBodyAPI.Apply(target.GetPrim())
        target_rigid.CreateRigidBodyEnabledAttr(True)
        target_rigid.CreateKinematicEnabledAttr(True)

    def _create_handle_geometry(self, path: str, position: Gf.Vec3d,  # Changed to Vec3d
                               color: Gf.Vec3f) -> UsdGeom.Xform:
        """Create handle geometry (wheel-like shape)"""
        xform = UsdGeom.Xform.Define(self.stage, path)

        # Set position
        xform.AddTranslateOp().Set(position)

        # Create wheel rim (cylinder)
        rim_path = f"{path}/Rim"
        rim = UsdGeom.Cylinder.Define(self.stage, rim_path)
        rim.CreateRadiusAttr(15)
        rim.CreateHeightAttr(3)
        rim.CreateAxisAttr("Z")

        # Create wheel spokes
        for i in range(4):
            angle = i * 90
            spoke_path = f"{path}/Spoke_{i}"
            spoke = UsdGeom.Cube.Define(self.stage, spoke_path)
            spoke.CreateSizeAttr(2)

            spoke_xform = UsdGeom.XformCommonAPI(spoke)
            spoke_xform.SetTranslate(Gf.Vec3d(0, 0, 0))  # Changed to Vec3d
            spoke_xform.SetRotate(Gf.Vec3f(0, 0, angle))  # Rotation can stay as Vec3f
            spoke_xform.SetScale(Gf.Vec3f(14, 1, 1))  # Scale can stay as Vec3f

        # Create center hub
        hub_path = f"{path}/Hub"
        hub = UsdGeom.Cylinder.Define(self.stage, hub_path)
        hub.CreateRadiusAttr(3)
        hub.CreateHeightAttr(5)
        hub.CreateAxisAttr("Z")

        # Add collision
        collision_api = UsdPhysics.CollisionAPI.Apply(xform.GetPrim())

        # Create and apply material
        material = self._create_material(f"{path}_Material", color)
        if material:
            UsdShade.MaterialBindingAPI(xform).Bind(material)

        return xform

    def _create_cylinder(self, path: str, radius: float, height: float,
                        position: Gf.Vec3d, color: Gf.Vec3f) -> UsdGeom.Cylinder:  # Changed position to Vec3d
        """Create a cylinder primitive"""
        cylinder = UsdGeom.Cylinder.Define(self.stage, path)
        cylinder.CreateRadiusAttr(radius)
        cylinder.CreateHeightAttr(height)
        cylinder.CreateAxisAttr("Z")

        # Set position
        xform = UsdGeom.XformCommonAPI(cylinder)
        xform.SetTranslate(position)  # Now using Vec3d

        # Add collision
        collision_api = UsdPhysics.CollisionAPI.Apply(cylinder.GetPrim())

        # Create and apply material
        material = self._create_material(f"{path}_Material", color)
        if material:
            UsdShade.MaterialBindingAPI(cylinder).Bind(material)

        return cylinder

    def _create_cube(self, path: str, size: float, position: Gf.Vec3d,  # Changed to Vec3d
                    color: Gf.Vec3f) -> UsdGeom.Cube:
        """Create a cube primitive"""
        cube = UsdGeom.Cube.Define(self.stage, path)
        cube.CreateSizeAttr(size)

        # Set position
        xform = UsdGeom.XformCommonAPI(cube)
        xform.SetTranslate(position)  # Now using Vec3d

        # Add collision
        collision_api = UsdPhysics.CollisionAPI.Apply(cube.GetPrim())

        # Create and apply material
        material = self._create_material(f"{path}_Material", color)
        if material:
            UsdShade.MaterialBindingAPI(cube).Bind(material)

        return cube

    def _create_revolute_joint(self, path: str, body0_path: str, body1_path: str,
                              local_pos0: Gf.Vec3f, local_pos1: Gf.Vec3f,
                              axis: Gf.Vec3f) -> UsdPhysics.RevoluteJoint:
        """Create a revolute joint between two bodies"""
        joint = UsdPhysics.RevoluteJoint.Define(self.stage, path)

        # Set connected bodies
        joint.CreateBody0Rel().SetTargets([body0_path])
        joint.CreateBody1Rel().SetTargets([body1_path])

        # Set local positions
        joint.CreateLocalPos0Attr(local_pos0)
        joint.CreateLocalPos1Attr(local_pos1)

        # Set local rotations (quaternions)
        joint.CreateLocalRot0Attr(Gf.Quatf(1, 0, 0, 0))
        joint.CreateLocalRot1Attr(Gf.Quatf(1, 0, 0, 0))

        # Set joint axis
        joint.CreateAxisAttr(axis)

        # Enable joint
        joint.CreateJointEnabledAttr(True)

        # Set joint limits (optional - for free rotation)
        joint.CreateLowerLimitAttr(-float('inf'))
        joint.CreateUpperLimitAttr(float('inf'))

        # Add PhysX-specific properties for better simulation
        physx_joint = PhysxSchema.PhysxJointAPI.Apply(joint.GetPrim())
        physx_joint.CreateJointFrictionAttr(0.5)  # Add some friction to handles

        return joint

    def _create_material(self, name: str, color: Gf.Vec3f) -> Optional[UsdShade.Material]:
        """Create a simple colored material"""
        try:
            material_path = f"/World/Materials/{name}"
            material = UsdShade.Material.Define(self.stage, material_path)

            # Create shader
            shader = UsdShade.Shader.Define(self.stage, f"{material_path}/Shader")
            shader.CreateImplementationSourceAttr(UsdShade.Tokens.sourceAsset)
            shader.SetSourceAsset("OmniPBR.mdl", "mdl")
            shader.SetSourceAssetSubIdentifier("OmniPBR", "mdl")

            # Set color
            shader.CreateInput("diffuse_color_constant", Sdf.ValueTypeNames.Color3f).Set(color)

            # Connect shader to material
            material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")

            return material
        except Exception as e:
            carb.log_warn(f"Failed to create material: {e}")
            return None