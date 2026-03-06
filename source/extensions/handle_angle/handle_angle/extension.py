"""
Enhanced HandleDrive Extension v4
RevoluteJointの制約を強化し、意図しない力による動きを制限する
"""

import omni.ext
import omni.usd
import omni.kit.app
import omni.timeline
import math
import typing
from pxr import Usd, Gf, Sdf, UsdGeom, UsdPhysics, PhysxSchema

class EnhancedHandleController:
    """強化されたハンドルコントローラー - Transform監視方式"""

    def __init__(self, name: str, joint_path: str, handle_object_path: str, target_path: str,
                 axis: str, move_per_rotation: float, linked_target_path: str = None,
                 rotation_angle_per_movement: float = 360.0):
        # 基本設定
        self.name = name
        self.joint_path = Sdf.Path(joint_path)
        self.handle_object_path = Sdf.Path(handle_object_path)  # 回転するハンドルオブジェクト
        self.target_path = Sdf.Path(target_path)
        self.linked_target_path = Sdf.Path(linked_target_path) if linked_target_path else None
        self.axis = axis.upper()  # 'X', 'Y', 'Z'
        self.move_per_rotation = move_per_rotation
        self.rotation_angle_per_movement = rotation_angle_per_movement  # 移動を引き起こす回転角度（デフォルト360度）
        self.drive_api = None
        self.physx_joint_api = None

        # 制約パラメータ（調整可能）
        self.drive_stiffness = 1e6      # スティフネス
        self.drive_damping = 1e4        # ダンピング
        self.max_drive_force = 5000.0   # 最大駆動力
        self.friction_torque = 20.0     # フリクション

        # 移動制限
        self.min_limit = -1.0
        self.max_limit = 1.0
        self.initial_position = 0.0

        # Transform監視用の状態
        self.current_position = 0.0
        self.last_angle = None
        self.total_rotation = 0.0
        self.initial_transform = None   # 初期Transform保存用

        # 位置リセット用の初期状態保存
        self.initial_target_position = None      # ターゲットオブジェクトの初期位置
        self.initial_linked_target_position = None  # 連動ターゲットの初期位置（存在する場合）

        # 改善された連続回転追跡用
        self.rotation_direction = 0     # 回転方向の記憶（正:1, 負:-1, 未確定:0）
        self.consecutive_samples = []   # 最近の角度サンプル（異常検出用）
        self.max_samples = 8            # 保持するサンプル数（増加）
        self.direction_stability_count = 0  # 方向安定性カウンター
        self.velocity_samples = []      # 角速度サンプル
        self.max_velocity_samples = 5   # 角速度サンプル数
        self.rotation_momentum = 0.0    # 回転の慣性

    def set_limits(self, min_val: float, max_val: float, initial: float):
        """移動制限を設定"""
        self.min_limit = min_val
        self.max_limit = max_val
        self.initial_position = initial
        self.current_position = initial

    def set_drive_parameters(self, stiffness: float = None, damping: float = None,
                           max_force: float = None, friction: float = None):
        """ドライブパラメータを設定"""
        if stiffness is not None:
            self.drive_stiffness = stiffness
        if damping is not None:
            self.drive_damping = damping
        if max_force is not None:
            self.max_drive_force = max_force
        if friction is not None:
            self.friction_torque = friction

class EnhancedHandleDriveExtension(omni.ext.IExt):
    """強化されたハンドルドライブ拡張機能"""

    def on_startup(self, ext_id):
        print("[Enhanced HandleDrive v4] 起動中...")
        self._timeline = omni.timeline.get_timeline_interface()
        self._stage = None
        self._handles = []
        self._is_running = False
        self._initial_positions_saved = False  # 初期位置保存フラグ
        self._target_groups = {}  # ターゲットごとのハンドルグループ
        self._cumulative_movements = {}  # ターゲットごとの累積移動量

        # 更新イベントの登録
        app = omni.kit.app.get_app()
        self._update_sub = app.get_update_event_stream().create_subscription_to_pop(
            self._on_update, name="Enhanced HandleDrive Update"
        )

        # ステージ取得と初期化
        self._initialize_stage()
        print("[Enhanced HandleDrive v4] 起動完了")

    def on_shutdown(self):
        print("[Enhanced HandleDrive v4] 終了中...")

        # エクステンション終了時にも初期位置にリセット
        if self._stage and self._handles and self._initial_positions_saved:
            self._on_simulation_stop()

        if self._update_sub:
            self._update_sub.unsubscribe()
            self._update_sub = None
        print("[Enhanced HandleDrive v4] 終了完了")

    def _initialize_stage(self):
        """ステージとハンドルの初期化"""
        self._stage = omni.usd.get_context().get_stage()
        if not self._stage:
            print("[Enhanced HandleDrive v4] ERROR: ステージが取得できません")
            return

        # ArticulationRoot設定の最適化
        self._configure_articulation_root()

        # ハンドルの設定
        self._setup_enhanced_handles()

        # RevoluteJointの強化設定
        self._enhance_joint_constraints()

        # 診断
        self._diagnose_joints()

    def _configure_articulation_root(self):
        """ArticulationRootの最適化設定 - Transform監視方式用"""
        # Transform監視方式では、ArticulationRootの設定を最小限に抑える
        print("[Enhanced HandleDrive v4] Transform監視方式 - ArticulationRoot設定をスキップ")

        # 必要に応じて個別のJointのみ設定
        # Kinematic設定は行わない（Articulationエラーを回避）

    def _setup_enhanced_handles(self):
        """強化されたハンドル設定"""
        self._handles = []
        stage = omni.usd.get_context().get_stage()

        # 1. 右ハンドル - Transform監視方式
        # rotation_angle_per_movementパラメータで移動を引き起こす回転角度を指定可能
        # 例: rotation_angle_per_movement=180.0 → 180度ごとに移動
        # デフォルト: 360.0度（1回転ごと）
        right = EnhancedHandleController(
            name="右ハンドル",
            joint_path="/World/New_MillingMachine/Handle_Right/RevoluteJoint",
            handle_object_path="/World/New_MillingMachine/Handle_Right",  # 回転するハンドルオブジェクト
            target_path="/World/New_MillingMachine/Table",
            axis="Y",
            move_per_rotation= 0.05,
            linked_target_path= None,
            rotation_angle_per_movement=80.0  # デフォルト値、必要に応じて変更可能
        )
        right.set_limits(-3, 2, 0.0)
        # 適度な制約パラメータ（Transform監視では強すぎない設定）
        right.set_drive_parameters(
            stiffness=3,    # 適度なスティフネス
            damping=10,      # 適度なダンピング
            max_force=5000,   # 適度な最大力
            friction=25.0     # 適度なフリクション
        )
        self._handles.append(right)

        # 2. 左ハンドル - Transform監視方式
        left = EnhancedHandleController(
            name="左ハンドル",
            joint_path="/World/New_MillingMachine/Handle_Left/RevoluteJoint",
            handle_object_path="/World/New_MillingMachine/Handle_Left",
            target_path="/World/New_MillingMachine/Table",
            axis="Y",
            move_per_rotation=0.05,
            rotation_angle_per_movement=80.0
        )
        left.set_limits(-2.5, 1.5, 0.0)
        left.set_drive_parameters(stiffness=3, damping=10, friction=20.0)
        self._handles.append(left)

        # 3. 前ハンドル - Transform監視方式
        front = EnhancedHandleController(
            name="前ハンドル",
            joint_path="/World/New_MillingMachine/Base_002/Handle_Front/RevoluteJoint",
            handle_object_path="/World/New_MillingMachine/Base_002/Handle_Front",
            target_path="/World/New_MillingMachine/Base003",
            axis="X",
            move_per_rotation=0.05,
            linked_target_path="/World/New_MillingMachine/Table",
            rotation_angle_per_movement=80.0
        )
        front.set_limits(-1, 1.5, 0.0)
        front.set_drive_parameters(stiffness=0, damping=3, friction=10.0)
        self._handles.append(front)

        # 4. 上ハンドル1 - Transform監視方式

        # 5. 練習ハンドル
        upper2 = EnhancedHandleController(
            name="練習ハンドル",
            joint_path="/World/Cube_03/RevoluteJoint",
            handle_object_path="/World/Cube_03",
            target_path="/World/Cube_02",
            axis="X",
            move_per_rotation=0.5
        )
        upper2.set_limits(-10, 10, 0)
        upper2.set_drive_parameters(stiffness=0, damping=1e2, friction=0)
        self._handles.append(upper2)

        print(f"[Enhanced HandleDrive v4] {len(self._handles)}個の強化ハンドルを設定")

    def _enhance_joint_constraints(self):
        """RevoluteJointの制約を強化"""
        print("\n[Enhanced HandleDrive v4] === Joint制約の強化 ===")

        for handle in self._handles:
            joint_prim = self._stage.GetPrimAtPath(handle.joint_path)
            if not joint_prim.IsValid():
                print(f"[{handle.name}] ERROR: Joint primが無効です")
                continue

            try:
                # Transform監視方式：JointStateAPIは使用せず、DriveAPIのみ設定

                # 1. DriveAPIの適用と設定（物理特性の調整用）
                try:
                    handle.drive_api = UsdPhysics.DriveAPI.Apply(joint_prim, "angular")

                    # ドライブパラメータ設定
                    handle.drive_api.CreateStiffnessAttr(handle.drive_stiffness)
                    handle.drive_api.CreateDampingAttr(handle.drive_damping)
                    handle.drive_api.CreateMaxForceAttr(handle.max_drive_force)

                    # ターゲット位置とベロシティ（初期は0で固定）
                    handle.drive_api.CreateTargetPositionAttr(0.0)
                    handle.drive_api.CreateTargetVelocityAttr(0.0)
                    handle.drive_api.CreateTypeAttr("force")  # フォースドライブ使用
                    print(f"[{handle.name}] DriveAPI設定完了")
                except Exception as e:
                    print(f"[{handle.name}] DriveAPI設定エラー: {e}")

                # 2. PhysxRevoluteJointAPIの適用（フリクションなど）
                try:
                    handle.physx_joint_api = PhysxSchema.PhysxRevoluteJointAPI.Apply(joint_prim)

                    # フリクション設定
                    if hasattr(handle.physx_joint_api, 'CreateFrictionTorqueAttr'):
                        handle.physx_joint_api.CreateFrictionTorqueAttr(handle.friction_torque)
                    print(f"[{handle.name}] PhysxRevoluteJointAPI設定完了")
                except Exception as e:
                    print(f"[{handle.name}] PhysxRevoluteJointAPI設定エラー: {e}")

                # 3. 初期Transform保存（Transform監視用）
                try:
                    handle.initial_transform = self._capture_initial_transform(handle)
                    print(f"[{handle.name}] 初期Transform保存完了")
                except Exception as e:
                    print(f"[{handle.name}] 初期Transform保存エラー: {e}")

                print(f"[{handle.name}] Transform監視設定完了:")
                print(f"  - Stiffness: {handle.drive_stiffness}")
                print(f"  - Damping: {handle.drive_damping}")
                print(f"  - Max Force: {handle.max_drive_force}")
                print(f"  - Friction: {handle.friction_torque}")

            except Exception as e:
                print(f"[{handle.name}] 全体制約設定エラー: {e}")

        print("=== Joint制約強化完了 ===\n")

    def _capture_initial_transform(self, handle: EnhancedHandleController) -> typing.Optional[Gf.Matrix4d]:
        """改善された初期Transform行列保存（詳細診断付き）"""
        try:
            handle_prim = self._stage.GetPrimAtPath(handle.handle_object_path)
            if not handle_prim.IsValid():
                print(f"[{handle.name}] ERROR: ハンドルオブジェクトが見つかりません: {handle.handle_object_path}")
                return None

            xformable = UsdGeom.Xformable(handle_prim)
            if not xformable:
                print(f"[{handle.name}] ERROR: Xformableが無効")
                return None

            # ローカルTransformとワールドTransformを両方取得して比較
            local_matrix = xformable.GetLocalTransformation()
            world_matrix = xformable.ComputeLocalToWorldTransform(0)

            # 詳細診断情報を出力
            print(f"[{handle.name}] === Transform診断 === ")
            print(f"  パス: {handle.handle_object_path}")
            print(f"  監視軸: {handle.axis}")

            # ローカルTransform情報
            local_translation = local_matrix.ExtractTranslation()
            local_rotation = local_matrix.ExtractRotation()
            local_axis = local_rotation.GetAxis()
            local_angle = math.degrees(local_rotation.GetAngle())
            print(f"  ローカル位置: ({local_translation[0]:.3f}, {local_translation[1]:.3f}, {local_translation[2]:.3f})")
            print(f"  ローカル回転: 軸=({local_axis[0]:.3f}, {local_axis[1]:.3f}, {local_axis[2]:.3f}), 角度={local_angle:.1f}°")

            # ワールドTransform情報
            world_translation = world_matrix.ExtractTranslation()
            world_rotation = world_matrix.ExtractRotation()
            world_axis = world_rotation.GetAxis()
            world_angle = math.degrees(world_rotation.GetAngle())
            print(f"  ワールド位置: ({world_translation[0]:.3f}, {world_translation[1]:.3f}, {world_translation[2]:.3f})")
            print(f"  ワールド回転: 軸=({world_axis[0]:.3f}, {world_axis[1]:.3f}, {world_axis[2]:.3f}), 角度={world_angle:.1f}°")

            # RevoluteJointの軸情報を確認
            joint_prim = self._stage.GetPrimAtPath(handle.joint_path)
            if joint_prim.IsValid():
                joint = UsdPhysics.RevoluteJoint(joint_prim)
                if joint:
                    joint_axis = joint.GetAxisAttr().Get()
                    print(f"  Joint軸: {joint_axis}")

                    # 軸の一致チェック（大文字小文字を統一）
                    expected_axis = handle.axis.upper()  # 大文字に統一
                    joint_axis_upper = joint_axis.upper() if joint_axis else ""
                    if joint_axis_upper != expected_axis:
                        print(f"  ⚠️ 軸不一致: Joint軸={joint_axis}, 設定軸={expected_axis}")
                        print(f"      → 設定軸をJoint軸に合わせます: {joint_axis_upper}")
                        # 軸設定を修正
                        handle.axis = joint_axis_upper
                    else:
                        print(f"  ✅ 軸一致確認: {expected_axis}")

            # ローカルTransformを初期値として使用（より安定）
            print(f"  初期Transform: ローカルを使用")
            print(f"=== 診断完了 ===\n")

            return local_matrix  # ローカルTransformを使用

        except Exception as e:
            print(f"[{handle.name}] 初期Transform取得エラー: {e}")
            return None

    def _get_joint_angle_from_transform(self, handle: EnhancedHandleController) -> typing.Optional[float]:
        """診断機能付きTransform角度計算"""
        try:
            # ハンドルオブジェクトのTransformを取得
            handle_prim = self._stage.GetPrimAtPath(handle.handle_object_path)
            if not handle_prim.IsValid():
                return None

            xformable = UsdGeom.Xformable(handle_prim)
            if not xformable:
                return None

            # ローカルTransformを使用（より安定）
            current_matrix = xformable.GetLocalTransformation()

            # 初期Transform行列との差分を計算
            if handle.initial_transform is None:
                print(f"[{handle.name}] 初期Transform未設定、現在位置を初期値として設定")
                handle.initial_transform = current_matrix
                return 0.0

            # 直接RevoluteJointから角度を取得する方法を試す
            joint_angle = self._get_joint_angle_direct(handle)
            if joint_angle is not None:
                return joint_angle

            # Transform方式（フォールバック）
            try:
                # 初期回転から現在回転への変化を計算
                initial_rotation = handle.initial_transform.ExtractRotation()
                current_rotation = current_matrix.ExtractRotation()

                # 診断情報出力（デバッグ時のみ）
                if hasattr(handle, '_debug_count'):
                    handle._debug_count += 1
                else:
                    handle._debug_count = 0

                # 10回に1回詳細情報を出力
                if handle._debug_count % 10 == 0:
                    init_axis = initial_rotation.GetAxis()
                    init_angle = math.degrees(initial_rotation.GetAngle())
                    curr_axis = current_rotation.GetAxis()
                    curr_angle = math.degrees(current_rotation.GetAngle())
                    print(f"[{handle.name}] 診断: 初期({init_axis[0]:.2f},{init_axis[1]:.2f},{init_axis[2]:.2f})@{init_angle:.1f}° vs 現在({curr_axis[0]:.2f},{curr_axis[1]:.2f},{curr_axis[2]:.2f})@{curr_angle:.1f}°")

                # クォータニオンを使った相対回転計算
                initial_quat = initial_rotation.GetQuaternion()
                current_quat = current_rotation.GetQuaternion()

                # 相対回転クォータニオン
                relative_quat = current_quat * initial_quat.GetInverse()

                # オイラー角に変換
                euler_angles = self._quaternion_to_euler_improved(relative_quat)

                # 改善された角度取得（軸向き投影方式）
                angle_deg = self._get_axis_rotation_improved(handle, relative_quat)

                # 角度の正規化（-180〜180度）
                angle_deg = self._normalize_angle(angle_deg)

                return angle_deg

            except Exception as inner_e:
                print(f"[{handle.name}] クォータニオン計算エラー: {inner_e}")
                return None

        except Exception as e:
            print(f"[{handle.name}] Transform角度取得エラー: {e}")
            return None

    def _get_joint_angle_direct(self, handle: EnhancedHandleController) -> typing.Optional[float]:
        """直接RevoluteJointから角度を取得してみる"""
        try:
            # RevoluteJointから直接角度を取得する試み
            joint_prim = self._stage.GetPrimAtPath(handle.joint_path)
            if not joint_prim.IsValid():
                return None

            # UsdPhysics.RevoluteJointから直接取得を試す
            joint = UsdPhysics.RevoluteJoint(joint_prim)
            if joint:
                # JointStateから取得を試す（安全に）
                try:
                    # PhysxSchemaから取得を試す
                    physx_joint = PhysxSchema.PhysxRevoluteJointAPI(joint_prim)
                    if physx_joint:
                        # 可能な属性をチェック
                        attrs = joint_prim.GetAttributes()
                        for attr in attrs:
                            attr_name = attr.GetName()
                            if 'angle' in attr_name.lower() or 'position' in attr_name.lower():
                                value = attr.Get()
                                if value is not None:
                                    print(f"[{handle.name}] Joint属性発見: {attr_name} = {value}")
                                    if isinstance(value, (int, float)):
                                        return math.degrees(value) if abs(value) < 10 else value
                except Exception as e:
                    pass  # エラーは無視してTransform方式にフォールバック

            return None

        except Exception as e:
            return None

    def _get_axis_rotation_improved(self, handle: EnhancedHandleController, relative_quat) -> float:
        """ジンバルロック回避の軸投影角度計算（改善版：符号付き角度使用）"""
        try:
            # クォータニオンを軸角度表現に変換（符号付き角度を取得）
            axis_angle = self._quaternion_to_axis_angle(relative_quat)
            if axis_angle is None:
                return 0.0

            rotation_axis, rotation_angle_rad, signed_angle_rad = axis_angle

            # 指定軸ベクトルを定義
            if handle.axis == 'X':
                target_axis = [1.0, 0.0, 0.0]
            elif handle.axis == 'Y':
                target_axis = [0.0, 1.0, 0.0]
            else:  # Z
                target_axis = [0.0, 0.0, 1.0]

            # 回転軸と指定軸の内積（投影成分）の絶対値
            dot_product = (rotation_axis[0] * target_axis[0] +
                          rotation_axis[1] * target_axis[1] +
                          rotation_axis[2] * target_axis[2])

            # 符号付き角度を使用して投影（軸反転の影響を受けない）
            # dot_productの符号で回転方向を判定
            projected_angle = signed_angle_rad * abs(dot_product)

            # 回転軸が逆向きの場合は符号を反転
            if dot_product < 0:
                projected_angle = -projected_angle

            # 度数に変換
            angle_deg = math.degrees(projected_angle)

            # デバッグ情報（大きな変化のみ）
            if abs(angle_deg) > 5.0:
                print(f"[{handle.name}] 軸投影計算: 回転軸=({rotation_axis[0]:.2f},{rotation_axis[1]:.2f},{rotation_axis[2]:.2f}), "
                      f"角度={math.degrees(rotation_angle_rad):.1f}°, 符号付={math.degrees(signed_angle_rad):.1f}°, 投影={angle_deg:.1f}°")

            return angle_deg

        except Exception as e:
            print(f"[{handle.name}] 軸投影計算エラー: {e}")
            # フォールバック: オイラー角方式
            try:
                euler_angles = self._quaternion_to_euler_improved(relative_quat)
                if handle.axis == 'Z':
                    return euler_angles[2]
                elif handle.axis == 'Y':
                    return euler_angles[1]
                else:
                    return euler_angles[0]
            except:
                return 0.0

    def _quaternion_to_axis_angle(self, quat) -> typing.Optional[typing.Tuple[typing.List[float], float, float]]:
        """クォータニオンを軸角度表現に変換（符号付き角度を返す）"""
        try:
            # Gf.Quatdから成分を取得
            w = quat.GetReal()
            x, y, z = quat.GetImaginary()[0], quat.GetImaginary()[1], quat.GetImaginary()[2]

            # 正規化チェック
            length = math.sqrt(w*w + x*x + y*y + z*z)
            if length < 1e-6:
                return ([1.0, 0.0, 0.0], 0.0, 0.0)  # 回転なし

            w, x, y, z = w/length, x/length, y/length, z/length

            # 符号付き角度を計算（±πの範囲）
            # wを符号を保持したまま使用
            w_clamped = max(-1.0, min(1.0, w))
            angle = 2.0 * math.acos(w_clamped)

            if angle < 1e-6:  # 回転がほぼゼロ
                return ([1.0, 0.0, 0.0], 0.0, 0.0)

            sin_half_angle = math.sin(angle / 2.0)
            if abs(sin_half_angle) < 1e-6:
                return ([1.0, 0.0, 0.0], 0.0, 0.0)

            # 回転軸を正規化（符号を保持）
            axis_x = x / sin_half_angle
            axis_y = y / sin_half_angle
            axis_z = z / sin_half_angle

            # 符号付き角度を計算（-πからπの範囲）
            signed_angle = angle
            if w < 0:
                # 180度を超える場合は負の等価角度に変換
                signed_angle = -(2 * math.pi - angle)
                # 軸の向きは反転しない（符号付き角度で表現）

            return ([axis_x, axis_y, axis_z], angle, signed_angle)

        except Exception as e:
            print(f"軸角度変換エラー: {e}")
            return None

    def _quaternion_to_euler_improved(self, quat) -> typing.List[float]:
        """改善されたクォータニオンからオイラー角への変換"""
        try:
            # Gf.Quatdから成分を取得
            w, x, y, z = quat.GetReal(), quat.GetImaginary()[0], quat.GetImaginary()[1], quat.GetImaginary()[2]

            # より安定したオイラー角変換
            # X軸回転（ロール）
            sin_r_cp = 2 * (w * x + y * z)
            cos_r_cp = 1 - 2 * (x * x + y * y)
            roll = math.atan2(sin_r_cp, cos_r_cp)

            # Y軸回転（ピッチ）
            sin_p = 2 * (w * y - z * x)
            sin_p = max(-1.0, min(1.0, sin_p))  # クランプして安定化
            pitch = math.asin(sin_p)

            # Z軸回転（ヨー）
            sin_y_cp = 2 * (w * z + x * y)
            cos_y_cp = 1 - 2 * (y * y + z * z)
            yaw = math.atan2(sin_y_cp, cos_y_cp)

            # 度数に変換
            return [
                math.degrees(roll),   # X軸
                math.degrees(pitch),  # Y軸
                math.degrees(yaw)     # Z軸
            ]

        except Exception as e:
            print(f"クォータニオン変換エラー: {e}")
            return [0.0, 0.0, 0.0]

    def _get_axis_component_safe(self, axis, target_axis: str) -> float:
        """軸成分を安全に取得"""
        try:
            axis_length = math.sqrt(axis[0]**2 + axis[1]**2 + axis[2]**2)
            if axis_length < 1e-6:
                return 0.0

            if target_axis == 'Z':
                return axis[2] / axis_length
            elif target_axis == 'Y':
                return axis[1] / axis_length
            else:  # X軸
                return axis[0] / axis_length
        except:
            return 0.0

    def _normalize_angle(self, angle: float) -> float:
        """角度を-180〜180度に正規化"""
        while angle > 180:
            angle -= 360
        while angle < -180:
            angle += 360
        return angle

    def _quaternion_to_euler(self, rotation) -> typing.List[float]:
        """Gf.Rotationをオイラー角（度）に変換"""
        try:
            # Gf.Rotationから軸と角度を取得
            axis = rotation.GetAxis()
            angle_rad = rotation.GetAngle()

            # 軸ベクトルを正規化
            axis_length = math.sqrt(axis[0]**2 + axis[1]**2 + axis[2]**2)
            if axis_length > 1e-6:
                normalized_axis = [axis[0]/axis_length, axis[1]/axis_length, axis[2]/axis_length]
            else:
                return [0.0, 0.0, 0.0]

            # 軸角度からクォータニオンを計算
            cos_half = math.cos(angle_rad / 2)
            sin_half = math.sin(angle_rad / 2)

            w = cos_half
            x = normalized_axis[0] * sin_half
            y = normalized_axis[1] * sin_half
            z = normalized_axis[2] * sin_half

            # クォータニオンからオイラー角への変換（XYZ順）
            # X軸回転（ロール）
            sin_r_cp = 2 * (w * x + y * z)
            cos_r_cp = 1 - 2 * (x * x + y * y)
            roll = math.atan2(sin_r_cp, cos_r_cp)

            # Y軸回転（ピッチ）
            sin_p = 2 * (w * y - z * x)
            if abs(sin_p) >= 1:
                pitch = math.copysign(math.pi / 2, sin_p)  # ±90度でクランプ
            else:
                pitch = math.asin(sin_p)

            # Z軸回転（ヨー）
            sin_y_cp = 2 * (w * z + x * y)
            cos_y_cp = 1 - 2 * (y * y + z * z)
            yaw = math.atan2(sin_y_cp, cos_y_cp)

            # 度数に変換
            return [
                math.degrees(roll),   # X軸
                math.degrees(pitch),  # Y軸
                math.degrees(yaw)     # Z軸
            ]

        except Exception as e:
            print(f"Rotation変換エラー: {e}")
            return [0.0, 0.0, 0.0]

    def _diagnose_joints(self):
        """Transform監視方式の診断機能"""
        print("\n[Enhanced HandleDrive v4] === Transform監視方式診断 ===")

        for handle in self._handles:
            print(f"[{handle.name}] 診断結果:")

            # Joint確認
            joint_prim = self._stage.GetPrimAtPath(handle.joint_path)
            if joint_prim.IsValid():
                joint = UsdPhysics.RevoluteJoint(joint_prim)
                if joint:
                    axis = joint.GetAxisAttr().Get()
                    print(f"  Joint軸: {axis}")
            else:
                print("  ⚠️ Joint未検出")

            # ハンドルオブジェクト確認
            handle_prim = self._stage.GetPrimAtPath(handle.handle_object_path)
            if handle_prim.IsValid():
                print(f"  ハンドルオブジェクト: 有効")
                # 初期Transform確認
                if handle.initial_transform:
                    print(f"  初期Transform: 保存済み")
                else:
                    print("  ⚠️ 初期Transform未保存")
            else:
                print(f"  ⚠️ ハンドルオブジェクト未検出: {handle.handle_object_path}")

            # Drive API確認
            if handle.drive_api:
                try:
                    stiffness = handle.drive_api.GetStiffnessAttr().Get()
                    damping = handle.drive_api.GetDampingAttr().Get()
                    max_force = handle.drive_api.GetMaxForceAttr().Get()
                    print(f"  Drive設定: Stiffness={stiffness}, Damping={damping}, MaxForce={max_force}")
                except:
                    print("  ⚠️ Drive設定読み取りエラー")
            else:
                print("  ⚠️ DriveAPI未設定")

            # PhysX API確認
            if handle.physx_joint_api:
                try:
                    friction = handle.physx_joint_api.GetFrictionTorqueAttr().Get()
                    print(f"  PhysX設定: Friction={friction}")
                except:
                    print("  ⚠️ PhysX設定読み取りエラー")
            else:
                print("  ⚠️ PhysxJointAPI未設定")

        print("=== Transform監視方式診断完了 ===\n")

    def _on_update(self, e):
        """メインの更新処理"""
        if not self._stage:
            return

        is_playing = self._timeline.is_playing()

        # シミュレーション開始時の処理
        if is_playing and not self._is_running:
            self._on_simulation_start()
            self._is_running = True
        elif not is_playing and self._is_running:
            self._on_simulation_stop()
            self._is_running = False
            print("[Enhanced HandleDrive v4] シミュレーション停止")
            return

        # シミュレーション中の処理
        if is_playing:
            self._process_handles()
            self._monitor_constraints()  # 制約監視を追加

    def _on_simulation_start(self):
        """シミュレーション開始時の初期化"""
        print("[Enhanced HandleDrive v4] シミュレーション開始 - 安定化制約初期化")

        for handle in self._handles:
            # 安定化追跡状態をリセット
            handle.rotation_direction = 0
            handle.consecutive_samples.clear()

            # 初期Transform再取得（実際の配置位置を基準とする）
            handle.initial_transform = self._capture_initial_transform(handle)

            # 基本状態をリセット（Transform取得後）
            handle.last_angle = None
            handle.total_rotation = 0.0

            # 現在のターゲット位置を取得し、それを初期位置として設定
            current_target_position = self._get_current_target_position(handle)
            if current_target_position is not None:
                handle.initial_position = current_target_position
                handle.current_position = current_target_position
                print(f"[{handle.name}] 現在のターゲット位置を初期値として設定: {current_target_position:.3f}")
            else:
                # デフォルト初期位置を使用
                handle.current_position = handle.initial_position
                print(f"[{handle.name}] デフォルト初期位置を使用: {handle.initial_position:.3f}")

            # ドライブターゲットを現在位置に設定（固定）
            if handle.drive_api:
                handle.drive_api.GetTargetPositionAttr().Set(0.0)
                handle.drive_api.GetTargetVelocityAttr().Set(0.0)

            print(f"[{handle.name}] 安定化制約初期化完了: 位置={handle.current_position:.3f}")

        # 初回シミュレーション開始時に初期位置を保存
        if not self._initial_positions_saved:
            self._save_initial_positions()
            self._setup_target_groups()  # ターゲットグループを設定
            self._initial_positions_saved = True

    def _get_current_target_position(self, handle: EnhancedHandleController) -> typing.Optional[float]:
        """ターゲットオブジェクトの現在位置を取得"""
        try:
            target_prim = self._stage.GetPrimAtPath(handle.target_path)
            if not target_prim.IsValid():
                return None

            xformable = UsdGeom.Xformable(target_prim)
            if not xformable:
                return None

            # 現在のTranslate操作を取得
            for op in xformable.GetOrderedXformOps():
                if op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
                    current = op.Get()
                    if current is not None:
                        # 指定軸の位置を返す
                        if handle.axis == 'X':
                            return float(current[0])
                        elif handle.axis == 'Y':
                            return float(current[1])
                        else:  # Z
                            return float(current[2])

            return None

        except Exception as e:
            print(f"[{handle.name}] 現在ターゲット位置取得エラー: {e}")
            return None

    def _monitor_constraints(self):
        """制約の監視（デバッグ用）"""
        # 定期的に制約状態を監視（必要に応じて調整）
        pass

    def _check_handle_grabbed(self, handle: EnhancedHandleController) -> typing.Optional[bool]:
        """ハンドルが掴まれているかチェック（custom:grab属性を確認）

        Args:
            handle: チェック対象のハンドルコントローラー

        Returns:
            True: custom:grab = True（掴まれている）
            False: custom:grab = False（掴まれていない）
            None: custom:grab属性が存在しない（無視して通常処理）
        """
        try:
            # ハンドルオブジェクトのPrimを取得
            handle_prim = self._stage.GetPrimAtPath(handle.handle_object_path)
            if not handle_prim.IsValid():
                return None

            # ハンドルオブジェクト自体のcustom:grab属性をチェック
            grab_attr = handle_prim.GetAttribute("custom:grab")
            if grab_attr and grab_attr.HasValue():
                return grab_attr.Get()

            # 子オブジェクトのcustom:grab属性をチェック
            for child in handle_prim.GetChildren():
                child_grab_attr = child.GetAttribute("custom:grab")
                if child_grab_attr and child_grab_attr.HasValue():
                    return child_grab_attr.Get()

            # custom:grab属性が見つからない場合はNone（無視）
            return None

        except Exception as e:
            # エラー時は無視（通常処理を継続）
            return None

    def _process_handles(self):
        """改善されたTransform監視方式による各ハンドルの処理"""
        for handle in self._handles:
            # ★追加★ custom:grab属性をチェック（掴んでいない場合は移動処理をスキップ）
            is_grabbed = self._check_handle_grabbed(handle)
            if is_grabbed is False:
                # custom:grab = False の場合、移動処理をスキップ
                # ただし、角度の更新は行う（掴み直した時に正しく動作するため）
                current_angle = self._get_joint_angle_from_transform(handle)
                if current_angle is not None:
                    handle.last_angle = current_angle
                continue

            # Transform監視による現在の角度を取得
            current_angle = self._get_joint_angle_from_transform(handle)
            if current_angle is None:
                continue

            # 角度サンプルを記録（異常検出用）
            handle.consecutive_samples.append(current_angle)
            if len(handle.consecutive_samples) > handle.max_samples:
                handle.consecutive_samples.pop(0)

            # 初回は記録のみ
            if handle.last_angle is None:
                handle.last_angle = current_angle
                continue

            # 改善された角度変化を計算
            delta = self._calculate_stable_angle_delta(handle, current_angle, handle.last_angle)

            # ノイズ除去（小さな変化は無視）
            if abs(delta) < 0.5:
                continue

            # 回転方向の追跡更新
            self._update_rotation_direction(handle, delta)

            # 制限到達チェック（累積更新前）
            at_limit = self._is_at_movement_limit(handle)

            # 制限に到達していて、さらに同じ方向に回転している場合は累積を制限
            if at_limit and self._is_rotation_toward_limit(handle, delta):
                print(f"[{handle.name}] 制限到達中の同方向回転を無視: {delta:+.1f}° (累積維持: {handle.total_rotation:.1f}°)")
                # 累積回転は更新しない（制限解除まで待機）
            else:
                # 改善された累積回転更新（境界ジャンプ対応）
                handle.total_rotation = self._update_cumulative_rotation(handle, current_angle, delta)

            # デバッグ出力（大きな変化のみ）
            if abs(delta) > 5.0:
                direction_str = "正" if handle.rotation_direction > 0 else "負" if handle.rotation_direction < 0 else "未確定"
                print(f"[{handle.name}] Transform角度: {current_angle:.1f}°, 変化: {delta:+.1f}°, 累積: {handle.total_rotation:.1f}°, 方向: {direction_str}")

            # 360度ごとに移動（協調制御対応）
            self._check_and_move_coordinated(handle)

            # 現在角度を記録
            handle.last_angle = current_angle

    def _check_and_move_coordinated(self, handle: EnhancedHandleController):
        """協調制御対応の移動チェック"""
        # 何回転したか計算
        rotations = int(handle.total_rotation / handle.rotation_angle_per_movement)

        if rotations != 0:
            # 協調制御か単独制御かで処理を分岐
            if hasattr(handle, '_is_coordinated') and handle._is_coordinated:
                self._handle_coordinated_movement(handle, rotations)
            else:
                self._handle_individual_movement(handle, rotations)

    def _handle_coordinated_movement(self, handle: EnhancedHandleController, rotations: int):
        """協調制御での移動処理"""
        try:
            target_key = handle._target_group_key
            movement = rotations * handle.move_per_rotation

            # グループ全体の累積移動量を更新
            if target_key not in self._cumulative_movements:
                self._cumulative_movements[target_key] = 0.0

            previous_total = self._cumulative_movements[target_key]
            new_total = previous_total + movement

            # 制限チェック（グループ全体で）
            group_handles = self._target_groups[target_key]
            combined_limits = self._get_combined_limits(group_handles)

            would_exceed_limit = False
            clamped_total = new_total

            if new_total > combined_limits['max']:
                clamped_total = combined_limits['max']
                would_exceed_limit = True
            elif new_total < combined_limits['min']:
                clamped_total = combined_limits['min']
                would_exceed_limit = True

            # 実際に移動があるか確認
            actual_movement = clamped_total - previous_total
            if abs(actual_movement) > 0.001:
                # 協調移動実行
                if self._execute_coordinated_movement(handle, target_key, clamped_total):
                    direction = "正方向" if rotations > 0 else "負方向"
                    print(f"[{handle.name}] ★協調移動★ {abs(rotations)}回転 → {handle.axis}軸 {direction} {abs(actual_movement):.3f} (総移動: {clamped_total:.3f})")

                    # グループ内の全ハンドルの位置を更新
                    for group_handle in group_handles:
                        group_handle.current_position = group_handle.initial_position + clamped_total

                    # 累積移動量を更新
                    self._cumulative_movements[target_key] = clamped_total

                # 処理済みの回転を減算
                handle.total_rotation -= rotations * handle.rotation_angle_per_movement

            elif would_exceed_limit:
                # 制限到達の処理
                self._handle_coordinated_limit_reached(handle, target_key)
            else:
                # 移動量が小さすぎる場合
                handle.total_rotation -= rotations * handle.rotation_angle_per_movement

        except Exception as e:
            print(f"[{handle.name}] 協調移動エラー: {e}")
            # フォールバック: 個別移動
            self._handle_individual_movement(handle, rotations)

    def _handle_individual_movement(self, handle: EnhancedHandleController, rotations: int):
        """個別制御での移動処理（従来の方式）"""
        # 移動量を計算
        movement = rotations * handle.move_per_rotation
        new_position = handle.current_position + movement

        # 制限チェック（クランプ前の計算）
        would_exceed_limit = False
        clamped_position = new_position

        if new_position > handle.max_limit:
            clamped_position = handle.max_limit
            would_exceed_limit = True
        elif new_position < handle.min_limit:
            clamped_position = handle.min_limit
            would_exceed_limit = True

        # 実際に移動があるか確認
        if abs(clamped_position - handle.current_position) > 0.001:
            # 移動実行
            if self._set_target_position(handle, clamped_position):
                direction = "正方向" if rotations > 0 else "負方向"
                print(f"[{handle.name}] ★個別移動★ {abs(rotations)}回転 → {handle.axis}軸 {direction} {abs(movement):.3f}")

                handle.current_position = clamped_position

            # 処理済みの回転を減算
            handle.total_rotation -= rotations * handle.rotation_angle_per_movement

        elif would_exceed_limit:
            # 制限に達して移動できない場合：累積回転をリセット
            limit_name = "最大制限" if new_position > handle.max_limit else "最小制限"
            print(f"[{handle.name}] {limit_name}到達 - 累積回転をリセット (累積: {handle.total_rotation:.1f}° → 0°)")
            handle.total_rotation = 0.0  # 累積をリセット

            # 制限到達時は回転方向もリセット（即座に逆方向に反応するため）
            if abs(handle.total_rotation) < 1.0:  # ほぼゼロの場合
                handle.rotation_direction = 0
                handle.direction_stability_count = 0
                if hasattr(handle, 'direction_change_count'):
                    handle.direction_change_count = 0
                print(f"[{handle.name}] 方向状態もリセット - 即座な逆方向反応を可能にします")
        else:
            # 移動量が小さすぎる場合でも処理済み回転は減算
            handle.total_rotation -= rotations * handle.rotation_angle_per_movement

    def _get_combined_limits(self, group_handles):
        """グループ内のハンドルの制限を統合"""
        min_limit = min(h.min_limit for h in group_handles)
        max_limit = max(h.max_limit for h in group_handles)
        return {'min': min_limit, 'max': max_limit}

    def _execute_coordinated_movement(self, handle: EnhancedHandleController, target_key: str, total_position: float) -> bool:
        """協調移動の実行"""
        try:
            target_path, axis = target_key.split(':')
            target_sdf_path = Sdf.Path(target_path)

            # 絶対位置として設定
            absolute_position = handle.initial_position + total_position

            success = self._move_object_to_absolute_position(target_sdf_path, axis, absolute_position)

            # 連動ターゲットも移動
            if handle.linked_target_path:
                linked_success = self._move_object_to_absolute_position(handle.linked_target_path, axis, absolute_position)
                success = success and linked_success

            return success

        except Exception as e:
            print(f"[{handle.name}] 協調移動実行エラー: {e}")
            return False

    def _move_object_to_absolute_position(self, object_path: Sdf.Path, axis: str, position: float) -> bool:
        """オブジェクトを絶対位置に移動"""
        try:
            prim = self._stage.GetPrimAtPath(object_path)
            if not prim.IsValid():
                return False

            xformable = UsdGeom.Xformable(prim)
            if not xformable:
                return False

            # 既存のTranslate操作を探すか作成
            translate_op = None
            for op in xformable.GetOrderedXformOps():
                if op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
                    translate_op = op
                    break

            if not translate_op:
                translate_op = xformable.AddTranslateOp()

            # 現在位置を取得
            current = translate_op.Get()
            if current is None:
                current = Gf.Vec3d(0, 0, 0)

            # 指定軸のみ更新（絶対位置）
            if axis == 'X':
                new_pos = Gf.Vec3d(position, current[1], current[2])
            elif axis == 'Y':
                new_pos = Gf.Vec3d(current[0], position, current[2])
            else:  # Z
                new_pos = Gf.Vec3d(current[0], current[1], position)

            # 位置を設定
            translate_op.Set(new_pos)
            return True

        except Exception as e:
            print(f"絶対位置移動エラー ({object_path}): {e}")
            return False

    def _handle_coordinated_limit_reached(self, handle: EnhancedHandleController, target_key: str):
        """協調制御での制限到達処理"""
        # グループ全体で制限到達として処理
        group_handles = self._target_groups[target_key]
        combined_limits = self._get_combined_limits(group_handles)
        current_total = self._cumulative_movements[target_key]

        if current_total >= combined_limits['max']:
            limit_name = "最大制限"
        else:
            limit_name = "最小制限"

        print(f"[{handle.name}] 協調制御 {limit_name}到達 - グループ累積をリセット (総移動: {current_total:.3f} → 0)")

        # グループ内の全ハンドルをリセット
        for group_handle in group_handles:
            group_handle.total_rotation = 0.0
            group_handle.rotation_direction = 0
            group_handle.direction_stability_count = 0
            if hasattr(group_handle, 'direction_change_count'):
                group_handle.direction_change_count = 0

    def _is_at_movement_limit(self, handle: EnhancedHandleController) -> bool:
        """オブジェクトが移動制限に到達しているかチェック"""
        tolerance = 0.01  # 制限近傍の許容範囲
        return (abs(handle.current_position - handle.max_limit) < tolerance or
                abs(handle.current_position - handle.min_limit) < tolerance)

    def _is_rotation_toward_limit(self, handle: EnhancedHandleController, delta: float) -> bool:
        """回転が制限方向を向いているかチェック"""
        if abs(delta) < 1.0:  # 小さな変化は無視
            return False

        # 現在の位置が最大制限近くで、正の回転（さらに制限方向）
        if abs(handle.current_position - handle.max_limit) < 0.01:
            # 移動方向を判定（move_per_rotationの符号を考慮）
            move_direction = 1 if handle.move_per_rotation > 0 else -1
            rotation_toward_max = (delta > 0 and move_direction > 0) or (delta < 0 and move_direction < 0)
            return rotation_toward_max

        # 現在の位置が最小制限近くで、負の回転（さらに制限方向）
        if abs(handle.current_position - handle.min_limit) < 0.01:
            # 移動方向を判定（move_per_rotationの符号を考慮）
            move_direction = 1 if handle.move_per_rotation > 0 else -1
            rotation_toward_min = (delta < 0 and move_direction > 0) or (delta > 0 and move_direction < 0)
            return rotation_toward_min

        return False

    def _update_cumulative_rotation(self, handle: EnhancedHandleController, current_angle: float, delta: float) -> float:
        """改善された累積回転更新（境界ジャンプと連続性を考慮）"""
        try:
            # 前回の累積値
            previous_total = handle.total_rotation

            # 基本的な累積更新
            new_total = previous_total + delta

            # 境界近傍での特別処理（±85度付近）
            if abs(current_angle) > 80.0:  # 境界近傍
                # 継続的な同方向回転の検出
                if len(handle.consecutive_samples) >= 3:
                    recent_deltas = []
                    for i in range(1, min(4, len(handle.consecutive_samples))):
                        prev_sample = handle.consecutive_samples[-i-1]
                        curr_sample = handle.consecutive_samples[-i]
                        sample_delta = self._calculate_angle_delta(curr_sample, prev_sample)
                        if abs(sample_delta) > 0.5:
                            recent_deltas.append(sample_delta)

                    # 連続した同方向回転の確認
                    if len(recent_deltas) >= 2:
                        avg_delta = sum(recent_deltas) / len(recent_deltas)
                        consistent_direction = all(d * avg_delta > 0 for d in recent_deltas)

                        if consistent_direction and abs(avg_delta) > 3.0:
                            # 安定した回転が続いている場合、境界での制限を回避
                            if abs(current_angle) > 85.0 and abs(delta) < 30.0:
                                # 境界での小さな変化は連続回転の一部として扱う
                                boost_factor = 1.5 if abs(avg_delta) > 10.0 else 1.2
                                new_total = previous_total + (delta * boost_factor)
                                print(f"[{handle.name}] 境界連続回転補正: {delta:.1f}° → {delta*boost_factor:.1f}° (累積: {new_total:.1f}°)")

            # 設定角度到達の検出（境界問題を回避）
            threshold = handle.rotation_angle_per_movement * 0.97  # 97%到達で検出
            if abs(new_total) >= threshold:
                rotations = int(new_total / handle.rotation_angle_per_movement)
                if rotations != 0:
                    print(f"[{handle.name}] {handle.rotation_angle_per_movement}度到達検出: 累積={new_total:.1f}° → {rotations}回転相当")
                    # 設定角度単位での処理は _check_and_move_constrained で実行
                    return new_total

            return new_total

        except Exception as e:
            print(f"[{handle.name}] 累積更新エラー: {e}")
            return handle.total_rotation + delta


    def _calculate_angle_delta(self, current: float, previous: float) -> float:
        """改善された角度差計算（連続回転対応）"""
        delta = current - previous

        # -180～+180の範囲に正規化
        while delta > 180:
            delta -= 360
        while delta < -180:
            delta += 360

        # 大きな角度変化の検出と補正（回転方向の連続性を保持）
        if abs(delta) > 150:  # 大きな変化を検出
            # 逆方向の可能性をチェック
            alternative_delta = delta - 360 if delta > 0 else delta + 360

            # より小さい変化を採用（連続性を保持）
            if abs(alternative_delta) < abs(delta):
                delta = alternative_delta
                print(f"[角度補正] 大きな変化を検出: 元={current-previous:.1f}°, 補正後={delta:.1f}°")

        return delta

    def _calculate_stable_angle_delta(self, handle: EnhancedHandleController, current: float, previous: float) -> float:
        """大幅に改善された角度差計算（慣性と安定性を考慮）"""
        # 基本的な角度差分計算
        raw_delta = self._calculate_angle_delta(current, previous)

        # 角速度の記録と更新
        handle.velocity_samples.append(raw_delta)
        if len(handle.velocity_samples) > handle.max_velocity_samples:
            handle.velocity_samples.pop(0)

        # 慣性による補正（連続性を重視）
        if len(handle.velocity_samples) >= 3:
            # 最近の角速度の平均を計算
            recent_velocities = [v for v in handle.velocity_samples[:-1] if abs(v) > 0.5]
            if recent_velocities:
                avg_velocity = sum(recent_velocities) / len(recent_velocities)
                handle.rotation_momentum = 0.7 * handle.rotation_momentum + 0.3 * avg_velocity

        # 慣性を考慮した補正
        delta = raw_delta

        # 大きな角度ジャンプの検出と補正
        if abs(delta) > 120:  # 大きな変化を検出
            # 慣性方向と一致するかチェック
            if abs(handle.rotation_momentum) > 2.0:  # 十分な慣性がある場合
                momentum_direction = 1 if handle.rotation_momentum > 0 else -1

                # 境界を越えた可能性を検討
                alternatives = [
                    delta,
                    delta - 360 if delta > 0 else delta + 360,
                    delta + 360 if delta < 0 else delta - 360
                ]

                # 慣性方向と最も一致する候補を選択
                best_delta = min(alternatives, key=lambda d: abs(d - handle.rotation_momentum))

                if abs(best_delta) < abs(delta):
                    print(f"[{handle.name}] 慣性補正: {delta:.1f}° → {best_delta:.1f}° (慣性: {handle.rotation_momentum:.1f}°)")
                    delta = best_delta

        # 方向確定時の連続性チェック
        if handle.rotation_direction != 0 and abs(delta) > 90:
            momentum_direction = 1 if handle.rotation_momentum > 0 else -1
            delta_direction = 1 if delta > 0 else -1

            # 慣性と逆方向の大きな変化は疑わしい
            if momentum_direction != delta_direction and abs(handle.rotation_momentum) > 5.0:
                # 境界越えの可能性をチェック
                corrected_delta = delta + 360 * momentum_direction
                if abs(corrected_delta) < abs(delta) and abs(corrected_delta) < 60:
                    print(f"[{handle.name}] 方向連続性補正: {delta:.1f}° → {corrected_delta:.1f}°")
                    delta = corrected_delta

        # 異常検出（改善版）
        if len(handle.consecutive_samples) >= 5:
            # より厳密な異常検出
            recent_changes = []
            for i in range(1, len(handle.consecutive_samples)):
                recent_delta = self._calculate_angle_delta(
                    handle.consecutive_samples[i],
                    handle.consecutive_samples[i-1]
                )
                if abs(recent_delta) > 0.8:  # ノイズ除去
                    recent_changes.append(recent_delta)

            if len(recent_changes) >= 3:
                avg_change = sum(abs(d) for d in recent_changes) / len(recent_changes)
                std_change = math.sqrt(sum((abs(d) - avg_change)**2 for d in recent_changes) / len(recent_changes))

                # 統計的異常検出（3σ基準）
                if abs(delta) > avg_change + 3 * std_change and abs(delta) > 45:
                    print(f"[{handle.name}] 統計的異常検出: {delta:.1f}° (基準: {avg_change:.1f}±{3*std_change:.1f}°)")
                    # より保守的な補正
                    if abs(handle.rotation_momentum) > 1.0:
                        # 慣性方向に制限
                        max_change = max(30, avg_change + 2 * std_change)
                        delta = max(-max_change, min(max_change, delta))
                    else:
                        # 慣性不明時はより厳しく制限
                        delta = max(-20, min(20, delta))

        return delta

    def _update_rotation_direction(self, handle: EnhancedHandleController, delta: float):
        """改善された回転方向の追跡（ヒステリシスとモメンタム考慮）"""
        if abs(delta) < 1.5:  # 小さな変化は無視（閾値を上げる）
            return

        # 新しい方向を判定
        new_direction = 1 if delta > 0 else -1

        # 慣性方向も考慮
        momentum_direction = 0
        if abs(handle.rotation_momentum) > 2.0:
            momentum_direction = 1 if handle.rotation_momentum > 0 else -1

        # 方向が未確定の場合
        if handle.rotation_direction == 0:
            # 十分な変化がある場合のみ確定
            if abs(delta) > 5.0:
                handle.rotation_direction = new_direction
                handle.direction_stability_count = 1
                print(f"[{handle.name}] 回転方向確定: {'正方向' if new_direction > 0 else '負方向'}")
            return

        # 既存方向と同じ場合
        if handle.rotation_direction == new_direction:
            handle.direction_stability_count = min(handle.direction_stability_count + 1, 10)
            return

        # 方向が変わろうとしている場合（ヒステリシス適用）
        required_stability = 3  # 方向変更に必要な安定性
        if handle.direction_stability_count >= 5:  # 高安定時はより厳しく
            required_stability = 5

        # 慣性と一致する場合は変更しやすくする
        if momentum_direction != 0 and momentum_direction == new_direction:
            required_stability = max(1, required_stability - 2)

        # 十分な変化と慣性がある場合のみ方向変更
        if abs(delta) > 15.0:  # 方向変更の閾値を上げる
            # 連続した変化をカウント
            if not hasattr(handle, 'direction_change_count'):
                handle.direction_change_count = 0

            handle.direction_change_count += 1

            # 十分な連続性がある場合に変更
            if handle.direction_change_count >= required_stability:
                print(f"[{handle.name}] 回転方向変更: {'正方向' if new_direction > 0 else '負方向'} (安定性: {handle.direction_change_count})")
                handle.rotation_direction = new_direction
                handle.direction_stability_count = 1
                handle.direction_change_count = 0
        else:
            # 小さな変化では変更カウントをリセット
            if hasattr(handle, 'direction_change_count'):
                handle.direction_change_count = 0

    def _set_target_position(self, handle: EnhancedHandleController, position: float) -> bool:
        """ターゲットオブジェクトの位置を設定（連動オブジェクトも同時移動）"""
        success = True

        # メインターゲットを移動
        success &= self._move_object(handle, handle.target_path, position)

        # 連動ターゲットも移動
        if handle.linked_target_path:
            success &= self._move_object(handle, handle.linked_target_path, position)

        return success

    def _move_object(self, handle: EnhancedHandleController, target_path: Sdf.Path, position: float) -> bool:
        """指定されたオブジェクトを移動"""
        try:
            prim = self._stage.GetPrimAtPath(target_path)
            if not prim.IsValid():
                print(f"[{handle.name}] ERROR: ターゲットが見つかりません: {target_path}")
                return False

            xformable = UsdGeom.Xformable(prim)
            if not xformable:
                return False

            # 既存のTranslate操作を探すか作成
            translate_op = None
            for op in xformable.GetOrderedXformOps():
                if op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
                    translate_op = op
                    break

            if not translate_op:
                translate_op = xformable.AddTranslateOp()

            # 現在位置を取得
            current = translate_op.Get()
            if current is None:
                current = Gf.Vec3d(0, 0, 0)

            # 指定軸のみ更新
            if handle.axis == 'X':
                new_pos = Gf.Vec3d(position, current[1], current[2])
            elif handle.axis == 'Y':
                new_pos = Gf.Vec3d(current[0], position, current[2])
            else:  # Z
                new_pos = Gf.Vec3d(current[0], current[1], position)

            # 位置を設定
            translate_op.Set(new_pos)
            print(f"[{handle.name}] {target_path} を {handle.axis}軸 {position:.3f} に移動")
            return True

        except Exception as e:
            print(f"[{handle.name}] {target_path} 位置設定エラー: {e}")
            return False

    def _save_initial_positions(self):
        """全てのハンドルのターゲットオブジェクトの初期位置を保存"""
        print("[Enhanced HandleDrive v4] === 初期位置の保存 ===")

        for handle in self._handles:
            # メインターゲットの初期位置を保存
            handle.initial_target_position = self._get_object_position(handle.target_path)
            if handle.initial_target_position is not None:
                print(f"[{handle.name}] メインターゲット初期位置: {handle.initial_target_position}")
            else:
                print(f"[{handle.name}] メインターゲット初期位置取得失敗")

            # 連動ターゲットの初期位置を保存（存在する場合）
            if handle.linked_target_path:
                handle.initial_linked_target_position = self._get_object_position(handle.linked_target_path)
                if handle.initial_linked_target_position is not None:
                    print(f"[{handle.name}] 連動ターゲット初期位置: {handle.initial_linked_target_position}")
                else:
                    print(f"[{handle.name}] 連動ターゲット初期位置取得失敗")

        print("=== 初期位置保存完了 ===\n")

    def _setup_target_groups(self):
        """同じターゲットを制御するハンドルをグループ化"""
        print("[Enhanced HandleDrive v4] === ターゲットグループ設定 ===")

        self._target_groups = {}
        self._cumulative_movements = {}

        for handle in self._handles:
            target_key = f"{handle.target_path}:{handle.axis}"

            if target_key not in self._target_groups:
                self._target_groups[target_key] = []
                self._cumulative_movements[target_key] = 0.0

            self._target_groups[target_key].append(handle)

        # グループ情報を出力
        for target_key, group_handles in self._target_groups.items():
            if len(group_handles) > 1:
                handle_names = [h.name for h in group_handles]
                print(f"  協調制御グループ [{target_key}]: {', '.join(handle_names)}")

                # 協調制御用の設定
                for handle in group_handles:
                    handle._is_coordinated = True
                    handle._target_group_key = target_key
            else:
                group_handles[0]._is_coordinated = False
                group_handles[0]._target_group_key = None

        print("=== ターゲットグループ設定完了 ===\n")

    def _get_object_position(self, object_path: Sdf.Path) -> typing.Optional[Gf.Vec3d]:
        """指定されたオブジェクトの現在位置を取得"""
        try:
            prim = self._stage.GetPrimAtPath(object_path)
            if not prim.IsValid():
                return None

            xformable = UsdGeom.Xformable(prim)
            if not xformable:
                return None

            # 現在のTranslate操作を取得
            for op in xformable.GetOrderedXformOps():
                if op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
                    current = op.Get()
                    if current is not None:
                        return current

            # Translate操作がない場合はデフォルト位置
            return Gf.Vec3d(0, 0, 0)

        except Exception as e:
            print(f"位置取得エラー ({object_path}): {e}")
            return None

    def _on_simulation_stop(self):
        """シミュレーション停止時の処理（初期位置にリセット）"""
        print("[Enhanced HandleDrive v4] === 初期位置へのリセット ===")

        for handle in self._handles:
            # メインターゲットを初期位置にリセット
            if handle.initial_target_position is not None:
                if self._reset_object_position(handle.target_path, handle.initial_target_position):
                    print(f"[{handle.name}] メインターゲットを初期位置にリセット: {handle.initial_target_position}")
                else:
                    print(f"[{handle.name}] メインターゲットリセット失敗")

            # 連動ターゲットを初期位置にリセット（存在する場合）
            if handle.linked_target_path and handle.initial_linked_target_position is not None:
                if self._reset_object_position(handle.linked_target_path, handle.initial_linked_target_position):
                    print(f"[{handle.name}] 連動ターゲットを初期位置にリセット: {handle.initial_linked_target_position}")
                else:
                    print(f"[{handle.name}] 連動ターゲットリセット失敗")

            # ハンドルの内部状態もリセット
            handle.current_position = handle.initial_position
            handle.total_rotation = 0.0
            handle.last_angle = None
            handle.rotation_direction = 0
            handle.consecutive_samples.clear()
            handle.velocity_samples.clear()
            handle.rotation_momentum = 0.0
            handle.direction_stability_count = 0
            if hasattr(handle, 'direction_change_count'):
                handle.direction_change_count = 0

        # 協調制御の累積移動量もリセット
        self._cumulative_movements = {}
        print("協調制御の累積移動量もリセットしました")

        print("=== 初期位置リセット完了 ===\n")

    def _reset_object_position(self, object_path: Sdf.Path, target_position: Gf.Vec3d) -> bool:
        """指定されたオブジェクトを指定位置にリセット"""
        try:
            prim = self._stage.GetPrimAtPath(object_path)
            if not prim.IsValid():
                print(f"ERROR: リセットターゲットが見つかりません: {object_path}")
                return False

            xformable = UsdGeom.Xformable(prim)
            if not xformable:
                return False

            # 既存のTranslate操作を探すか作成
            translate_op = None
            for op in xformable.GetOrderedXformOps():
                if op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
                    translate_op = op
                    break

            if not translate_op:
                translate_op = xformable.AddTranslateOp()

            # 位置を設定
            translate_op.Set(target_position)
            return True

        except Exception as e:
            print(f"{object_path} リセットエラー: {e}")
            return False

# デバッグ用のグローバル参照
_enhanced_extension_instance = None

def get_enhanced_extension():
    """現在の強化Extensionインスタンスを取得"""
    return _enhanced_extension_instance