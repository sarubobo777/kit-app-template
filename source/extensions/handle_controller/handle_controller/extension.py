"""
Improved Handle Controller Extension with actual joint angle reading
"""

import omni.ext
import omni.ui as ui
import omni.usd
from pxr import Usd, UsdGeom, Gf, UsdPhysics, Sdf, PhysxSchema
import carb
import math
from typing import Dict, List, Optional, Tuple
import omni.timeline
from omni.physx import get_physx_interface, get_physx_simulation_interface
import numpy as np

# Import the scene creator module
from .scene_creator import SceneCreator


class HandleController:
    """Controller for managing handle rotations and object movements"""

    def __init__(self):
        self.stage = None
        self.handles = {}  # Dictionary of handle configurations
        self.physx_interface = get_physx_interface()
        self.physx_sim = get_physx_simulation_interface()

    def add_handle(self, handle_id: str, handle_path: str, target_path: str,
                  joint_path: str, move_axis: Gf.Vec3f, move_amount: float,
                  min_limit: float, max_limit: float):
        """Add a handle configuration"""
        self.handles[handle_id] = {
            'handle_path': handle_path,
            'target_path': target_path,
            'joint_path': joint_path,
            'move_axis': move_axis.GetNormalized(),
            'move_amount': move_amount,
            'min_limit': min_limit,
            'max_limit': max_limit,
            'last_angle': 0.0,
            'total_rotations': 0.0,
            'current_position': Gf.Vec3d(0, 0, 0),
            'initial_position': None,
            'accumulated_angle': 0.0
        }

    def initialize(self, stage: Usd.Stage):
        """Initialize the controller with the current stage"""
        self.stage = stage

        # Read initial positions of all targets
        for handle_id, config in self.handles.items():
            target_prim = stage.GetPrimAtPath(config['target_path'])
            if target_prim and target_prim.IsValid():
                xformable = UsdGeom.Xformable(target_prim)
                if xformable:
                    # Get initial transform
                    transform = xformable.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
                    translation = transform.ExtractTranslation()
                    config['initial_position'] = translation
                    config['current_position'] = translation

            # Initialize joint angle
            config['last_angle'] = self._get_joint_angle(config['joint_path'])
            config['accumulated_angle'] = 0.0

    def update(self, dt: float):
        """Update all handle controllers"""
        if not self.stage:
            return

        for handle_id, config in self.handles.items():
            self._update_handle(handle_id, config, dt)

    def _update_handle(self, handle_id: str, config: dict, dt: float):
        """Update a single handle and its target"""
        # Get current joint angle
        current_angle = self._get_joint_angle(config['joint_path'])

        if current_angle is None:
            return

        # Calculate angle difference (handling wrapping)
        angle_diff = current_angle - config['last_angle']

        # Handle angle wrapping at ±π
        if angle_diff > math.pi:
            angle_diff -= 2 * math.pi
        elif angle_diff < -math.pi:
            angle_diff += 2 * math.pi

        # Accumulate angle
        config['accumulated_angle'] += angle_diff

        # Check if we've completed a full rotation
        if abs(config['accumulated_angle']) >= 2 * math.pi:
            # Calculate number of complete rotations
            rotations = int(config['accumulated_angle'] / (2 * math.pi))

            # Reset accumulated angle (keep remainder)
            config['accumulated_angle'] -= rotations * 2 * math.pi

            # Move target object
            self._move_target(config, rotations)

        # Update last angle
        config['last_angle'] = current_angle

    def _get_joint_angle(self, joint_path: str) -> Optional[float]:
        """Get the current angle of a revolute joint using PhysX"""
        if not self.stage:
            return None

        joint_prim = self.stage.GetPrimAtPath(joint_path)
        if not joint_prim or not joint_prim.IsValid():
            return None

        # Method 1: Try to get from PhysX simulation directly
        try:
            # Get joint state from PhysX
            joint = UsdPhysics.RevoluteJoint(joint_prim)
            if joint:
                # Try to read joint position attribute if it exists
                if joint_prim.HasAttribute("physics:jointPosition"):
                    pos_attr = joint_prim.GetAttribute("physics:jointPosition")
                    if pos_attr:
                        return pos_attr.Get()

                # Alternative: Calculate from connected body transforms
                body0_rel = joint.GetBody0Rel()
                body1_rel = joint.GetBody1Rel()

                if body0_rel and body1_rel:
                    body0_paths = body0_rel.GetTargets()
                    body1_paths = body1_rel.GetTargets()

                    if body0_paths and body1_paths:
                        body0_prim = self.stage.GetPrimAtPath(body0_paths[0])
                        body1_prim = self.stage.GetPrimAtPath(body1_paths[0])

                        if body0_prim and body1_prim:
                            # Get transforms
                            xform0 = UsdGeom.Xformable(body0_prim)
                            xform1 = UsdGeom.Xformable(body1_prim)

                            if xform0 and xform1:
                                # Calculate relative rotation
                                transform0 = xform0.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
                                transform1 = xform1.ComputeLocalToWorldTransform(Usd.TimeCode.Default())

                                # Get relative transform
                                relative_transform = transform0.GetInverse() * transform1

                                # Extract rotation around joint axis (Z)
                                rotation = relative_transform.ExtractRotation()
                                angle = math.atan2(rotation.imaginary[0], rotation.real)

                                return angle
        except Exception as e:
            carb.log_warn(f"Error reading joint angle: {e}")

        return 0.0

    def _move_target(self, config: dict, rotations: int):
        """Move the target object based on handle rotations"""
        if not self.stage or rotations == 0:
            return

        target_prim = self.stage.GetPrimAtPath(config['target_path'])
        if not target_prim or not target_prim.IsValid():
            return

        xformable = UsdGeom.Xformable(target_prim)
        if not xformable:
            return

        # Calculate movement vector
        movement = config['move_axis'] * (config['move_amount'] * rotations)

        # Get current position
        current_pos = config['current_position']

        # Calculate new position
        new_pos = current_pos + movement

        # Apply movement limits along the movement axis
        if config['initial_position'] is not None:
            # Calculate displacement from initial position
            displacement = new_pos - config['initial_position']

            # Project displacement onto movement axis
            projection = displacement.GetDot(config['move_axis'])

            # Apply limits
            clamped_projection = max(config['min_limit'], min(config['max_limit'], projection))

            # Calculate clamped position
            clamped_displacement = config['move_axis'] * clamped_projection
            new_pos = config['initial_position'] + clamped_displacement

        # Apply the new position
        translate_op = None
        for op in xformable.GetOrderedXformOps():
            if op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
                translate_op = op
                break

        if not translate_op:
            translate_op = xformable.AddTranslateOp()

        translate_op.Set(new_pos)

        # Update stored position
        config['current_position'] = new_pos

        # Log movement
        carb.log_info(f"Moved {config['target_path']} by {rotations} rotations to {new_pos}")

    def reset_all(self):
        """Reset all targets to their initial positions"""
        if not self.stage:
            return

        for config in self.handles.values():
            if config['initial_position'] is not None:
                target_prim = self.stage.GetPrimAtPath(config['target_path'])
                if target_prim and target_prim.IsValid():
                    xformable = UsdGeom.Xformable(target_prim)
                    if xformable:
                        translate_op = None
                        for op in xformable.GetOrderedXformOps():
                            if op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
                                translate_op = op
                                break

                        if translate_op:
                            translate_op.Set(config['initial_position'])
                            config['current_position'] = config['initial_position']


class HandleControllerExtension(omni.ext.IExt):
    """Main extension class"""

    def on_startup(self, ext_id):
        carb.log_info("[HandleController] Starting up...")

        self._window = None
        self._controller = HandleController()
        self._timeline = omni.timeline.get_timeline_interface()
        self._update_sub = None
        self._timeline_sub = None
        self._stage_sub = None
        self._scene_creator = None

        # Create UI
        self._build_ui()

        # Setup event subscriptions
        self._setup_subscriptions()

        # Get current stage if available
        self._on_stage_opened()

    def on_shutdown(self):
        carb.log_info("[HandleController] Shutting down...")

        # Clean up subscriptions
        if self._update_sub:
            self._update_sub.unsubscribe()
        if self._timeline_sub:
            self._timeline_sub.unsubscribe()
        if self._stage_sub:
            self._stage_sub.unsubscribe()

        # Destroy window
        if self._window:
            self._window.destroy()
            self._window = None

    def _build_ui(self):
        """Build the extension UI"""
        self._window = ui.Window("Handle Controller", width=400, height=500)

        with self._window.frame:
            with ui.VStack(spacing=5):
                ui.Label("Handle Controller System", height=30,
                        style={"font_size": 18, "font_weight": "bold"})

                ui.Separator(height=2)

                # Control buttons
                with ui.HStack(height=30):
                    ui.Button("Create Sample Scene", clicked_fn=self._create_sample_scene)
                    ui.Button("Initialize", clicked_fn=self._initialize_handles)

                with ui.HStack(height=30):
                    ui.Button("Start", clicked_fn=self._start_simulation)
                    ui.Button("Stop", clicked_fn=self._stop_simulation)
                    ui.Button("Reset", clicked_fn=self._reset_positions)

                ui.Separator(height=2)

                # Status
                self._status_label = ui.Label("Status: Idle", height=20)

                # Handles list
                with ui.CollapsableFrame("Active Handles", height=300):
                    with ui.ScrollingFrame():
                        self._handles_container = ui.VStack()

    def _setup_subscriptions(self):
        """Setup event subscriptions"""
        # Timeline events
        stream = self._timeline.get_timeline_event_stream()
        self._timeline_sub = stream.create_subscription_to_pop(self._on_timeline_event)

        # Stage events
        context = omni.usd.get_context()
        self._stage_sub = context.get_stage_event_stream().create_subscription_to_pop(
            self._on_stage_event
        )

    def _on_stage_event(self, event):
        """Handle stage events"""
        if event.type == int(omni.usd.StageEventType.OPENED):
            self._on_stage_opened()

    def _on_stage_opened(self):
        """Called when a stage is opened"""
        stage = omni.usd.get_context().get_stage()
        if stage:
            self._scene_creator = SceneCreator(stage)
            self._controller.stage = stage

    def _on_timeline_event(self, event):
        """Handle timeline events"""
        if event.type == int(omni.timeline.TimelineEventType.PLAY):
            self._on_play()
        elif event.type == int(omni.timeline.TimelineEventType.STOP):
            self._on_stop()

    def _on_play(self):
        """Called when simulation starts"""
        self._status_label.text = "Status: Running"
        if not self._update_sub:
            # Subscribe to update events
            app = omni.kit.app.get_app()
            self._update_sub = app.get_update_event_stream().create_subscription_to_pop(
                self._on_update
            )

    def _on_stop(self):
        """Called when simulation stops"""
        self._status_label.text = "Status: Stopped"
        if self._update_sub:
            self._update_sub.unsubscribe()
            self._update_sub = None

    def _on_update(self, e: carb.events.IEvent):
        """Called on each frame update during simulation"""
        dt = e.payload["dt"]
        self._controller.update(dt)

    def _create_sample_scene(self):
        """Create a sample scene with handles and targets"""
        if self._scene_creator:
            self._scene_creator.create_sample_scene()
            self._initialize_handles()
            self._status_label.text = "Status: Sample scene created"

    def _initialize_handles(self):
        """Initialize handle configurations"""
        stage = omni.usd.get_context().get_stage()
        if not stage:
            return

        # Clear existing handles
        self._controller.handles.clear()

        # Add 5 sample handles
        handle_configs = [
            ("handle_1", "/World/Handle_1", "/World/Target_1", "/World/Handle_1_Joint",
             Gf.Vec3f(1, 0, 0), 10.0, -50.0, 50.0),
            ("handle_2", "/World/Handle_2", "/World/Target_2", "/World/Handle_2_Joint",
             Gf.Vec3f(0, 1, 0), 15.0, -30.0, 30.0),
            ("handle_3", "/World/Handle_3", "/World/Target_3", "/World/Handle_3_Joint",
             Gf.Vec3f(0, 0, 1), 20.0, -40.0, 40.0),
            ("handle_4", "/World/Handle_4", "/World/Target_4", "/World/Handle_4_Joint",
             Gf.Vec3f(1, 1, 0).GetNormalized(), 12.0, -35.0, 35.0),
            ("handle_5", "/World/Handle_5", "/World/Target_5", "/World/Handle_5_Joint",
             Gf.Vec3f(1, 0, 1).GetNormalized(), 18.0, -45.0, 45.0),
        ]

        for config in handle_configs:
            self._controller.add_handle(*config)

        # Initialize controller
        self._controller.initialize(stage)

        # Update UI
        self._update_handles_ui()
        self._status_label.text = "Status: Initialized"

    def _update_handles_ui(self):
        """Update the handles list in UI"""
        self._handles_container.clear()

        with self._handles_container:
            for handle_id, config in self._controller.handles.items():
                with ui.HStack(height=20):
                    ui.Label(f"{handle_id}:", width=80)
                    ui.Label(f"Target: {config['target_path'].split('/')[-1]}", width=100)
                    ui.Label(f"Limit: [{config['min_limit']:.1f}, {config['max_limit']:.1f}]")

    def _start_simulation(self):
        """Start the simulation"""
        self._timeline.play()

    def _stop_simulation(self):
        """Stop the simulation"""
        self._timeline.stop()

    def _reset_positions(self):
        """Reset all target positions"""
        self._controller.reset_all()
        self._status_label.text = "Status: Reset"