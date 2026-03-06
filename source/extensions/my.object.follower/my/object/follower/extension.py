import omni.ext
import omni.usd
import omni.kit.app
import omni.kit.commands
import omni.timeline
import carb
from pxr import Gf, Usd, UsdGeom, UsdPhysics

class MyObjectFollowerExtension(omni.ext.IExt):
    """物理ジョイントを考慮したオブジェクト追従Extension"""

    def on_startup(self, ext_id: str):
        """Extensionが起動したときに呼ばれる"""
        print("[my.object.follower] Extension startup (Joint-aware version)")

        # --- ▼ ユーザー設定項目 ▼ ---
        self._target_path = "/World/New_MillingMachine/Table"

        # ジョイントで接続されているオブジェクトは除外
        # または、ジョイントのBody0を更新する方法を選択
        self._follower_paths = [
            "/World/New_MillingMachine/Handle_Left",
            # Handle_Rightはジョイントで接続されているので直接移動しない
        ]

        # ジョイントのBody0を更新する対象
        self._joint_configs = [
            {
                "joint_path": "/World/New_MillingMachine/RevoluteJoint",  # ジョイントのパス
                "body0_target": "/World/New_MillingMachine/Table",        # Body0として設定したいパス
                "body1_target": "/World/New_MillingMachine/Handle_Right"  # Body1（確認用）
            }
        ]

        self._check_interval = 10
        # --- ▲ ユーザー設定項目 ▲ ---

        self._stage = None
        self._is_playing = False
        self._last_target_pos = None
        self._frame_count = 0
        self._update_subscription = None
        self._timeline_subscription = None

        # 初期設定：ジョイントの接続を修正
        self._setup_joints()

        # タイムラインインターフェースを取得
        self._timeline = omni.timeline.get_timeline_interface()

        # タイムラインイベントストリームを購読
        self._setup_timeline_events()

        # 初期状態をチェック
        if self._timeline.is_playing():
            print("[my.object.follower] Already playing, starting update")
            self._is_playing = True
            self._start_updating_event()

    def _setup_joints(self):
        """ジョイントの接続を適切に設定"""
        stage = omni.usd.get_context().get_stage()
        if not stage:
            print("[my.object.follower] Stage not available for joint setup")
            return

        for config in self._joint_configs:
            joint_prim = stage.GetPrimAtPath(config["joint_path"])
            if not joint_prim or not joint_prim.IsValid():
                print(f"[my.object.follower] Joint not found: {config['joint_path']}")
                continue

            # PhysicsJointとして取得
            physics_joint = UsdPhysics.Joint(joint_prim)
            if not physics_joint:
                print(f"[my.object.follower] Not a physics joint: {config['joint_path']}")
                continue

            try:
                # Body0をTableに設定
                body0_rel = physics_joint.GetBody0Rel()
                body0_rel.ClearTargets()
                body0_rel.AddTarget(config["body0_target"])

                # Body1の確認（既に設定されているはず）
                body1_rel = physics_joint.GetBody1Rel()
                current_body1 = body1_rel.GetTargets()

                print(f"[my.object.follower] Joint '{config['joint_path']}' configured:")
                print(f"  Body0: {config['body0_target']}")
                print(f"  Body1: {current_body1}")

                # ジョイントのローカル位置を調整（必要に応じて）
                # これにより、Handle_RightがTableに対して相対的に動くようになる

            except Exception as e:
                print(f"[my.object.follower] Error configuring joint: {e}")

    def _setup_timeline_events(self):
        """タイムラインイベントの購読を設定"""
        try:
            event_stream = self._timeline.get_timeline_event_stream()
            if event_stream:
                self._timeline_subscription = event_stream.create_subscription_to_pop(
                    self._on_timeline_event,
                    name="my_object_follower"
                )
                print("[my.object.follower] Timeline event subscription created")
                self._setup_status_check()
        except Exception as e:
            print(f"[my.object.follower] Error setting up timeline events: {e}")
            self._setup_status_check()

    def _setup_status_check(self):
        """定期的にタイムラインの状態をチェック"""
        try:
            app = omni.kit.app.get_app()
            update_stream = app.get_update_event_stream()
            self._status_check_counter = 0

            self._status_check_sub = update_stream.create_subscription_to_pop(
                self._check_timeline_status,
                name="status_checker"
            )
            print("[my.object.follower] Status check subscription created")
        except Exception as e:
            print(f"[my.object.follower] Error setting up status check: {e}")

    def _check_timeline_status(self, e):
        """定期的にタイムラインの状態を確認"""
        self._status_check_counter += 1

        if self._status_check_counter % 30 == 0:
            is_playing_now = self._timeline.is_playing()

            if is_playing_now != self._is_playing:
                if is_playing_now:
                    print("[my.object.follower] Play detected (status check)")
                    self._is_playing = True
                    self._start_updating_event()
                else:
                    print("[my.object.follower] Stop detected (status check)")
                    self._is_playing = False
                    self._stop_updating_event()

    def on_shutdown(self):
        """Extensionが終了したときに呼ばれる"""
        print("[my.object.follower] Extension shutdown")

        if self._timeline_subscription:
            self._timeline_subscription = None

        if hasattr(self, '_status_check_sub'):
            self._status_check_sub = None

        self._stop_updating_event()

    def _on_timeline_event(self, event):
        """タイムラインのイベント処理"""
        event_type = None

        if hasattr(event, 'type'):
            event_type = event.type
        elif hasattr(event, 'payload'):
            if isinstance(event.payload, dict) and 'type' in event.payload:
                event_type = event.payload['type']
            elif hasattr(event.payload, 'type'):
                event_type = event.payload.type

        if event_type == omni.timeline.TimelineEventType.PLAY:
            print("[my.object.follower] PLAY event detected")
            self._is_playing = True
            self._start_updating_event()
        elif event_type in [omni.timeline.TimelineEventType.STOP, omni.timeline.TimelineEventType.PAUSE]:
            print("[my.object.follower] STOP/PAUSE event detected")
            self._is_playing = False
            self._stop_updating_event()

    def _start_updating_event(self):
        """フレームごとの更新処理の購読を開始"""
        if self._update_subscription is not None:
            return

        print("[my.object.follower] Starting update subscription")

        self._stage = omni.usd.get_context().get_stage()
        if not self._stage:
            print("[my.object.follower] Error: Stage not found")
            return

        self._frame_count = 0
        self._last_target_pos = self._get_prim_translation(self._target_path)

        if self._last_target_pos:
            print(f"[my.object.follower] Initial target position: {self._last_target_pos}")

        try:
            app = omni.kit.app.get_app()
            update_stream = app.get_update_event_stream()
            self._update_subscription = update_stream.create_subscription_to_pop(
                self._on_update,
                name="object_follower_update"
            )
            print("[my.object.follower] Update subscription created successfully")
        except Exception as e:
            print(f"[my.object.follower] Error creating update subscription: {e}")

    def _stop_updating_event(self):
        """フレームごとの更新処理の購読を停止"""
        if self._update_subscription:
            print("[my.object.follower] Stopping update subscription")
            self._update_subscription = None
            self._last_target_pos = None

    def _on_update(self, e):
        """毎フレーム実行される更新処理"""
        if not self._is_playing or not self._stage:
            return

        self._frame_count += 1

        if self._frame_count % self._check_interval != 0:
            return

        current_target_pos = self._get_prim_translation(self._target_path)
        if current_target_pos is None:
            if self._last_target_pos is not None:
                print(f"[my.object.follower] Target lost: {self._target_path}")
                self._last_target_pos = None
            return

        if self._last_target_pos is None:
            print(f"[my.object.follower] Target found at: {current_target_pos}")
            self._last_target_pos = current_target_pos
            return

        if not Gf.IsClose(current_target_pos, self._last_target_pos, 1e-5):
            delta = current_target_pos - self._last_target_pos
            print(f"[my.object.follower] Target moved by: {delta}")

            # 直接追従するオブジェクトを移動
            self._move_followers(delta)

            # ジョイントで接続されたオブジェクトは自動的に追従する
            # (Body0がTableに設定されているため)

        self._last_target_pos = current_target_pos

    def _get_prim_translation(self, prim_path: str):
        """指定されたPrimのTranslate量を取得"""
        if not self._stage:
            return None

        prim = self._stage.GetPrimAtPath(prim_path)
        if not prim or not prim.IsValid():
            return None

        try:
            xformable = UsdGeom.Xformable(prim)
            time = Usd.TimeCode.Default()
            transform_matrix = xformable.GetLocalTransformation(time)
            return transform_matrix.ExtractTranslation()
        except Exception as e:
            print(f"[my.object.follower] Error getting translation for {prim_path}: {e}")
            return None

    def _move_followers(self, delta):
        """追従オブジェクトの位置を更新"""
        for path in self._follower_paths:
            current_pos = self._get_prim_translation(path)
            if current_pos is None:
                print(f"[my.object.follower] Warning: Follower '{path}' not found")
                continue

            new_pos = current_pos + delta

            try:
                omni.kit.commands.execute('ChangeProperty',
                    prop_path=f'{path}.xformOp:translate',
                    value=new_pos,
                    prev=current_pos
                )
                print(f"[my.object.follower] Moved '{path}' to {new_pos}")
            except Exception as e:
                print(f"[my.object.follower] Error moving '{path}': {e}")