# SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

import omni.ext
import omni.ui as ui
import omni.usd
import omni.physx
import omni.kit.app
import omni.timeline
from pxr import Usd, UsdGeom, UsdPhysics, Sdf, Gf, PhysxSchema
from dataclasses import dataclass
from typing import Optional, List, Tuple
import carb

# グローバルインスタンス
_extension_instance = None


def get_extension_instance():
    """他の拡張機能からアクセスするためのグローバルインスタンス取得関数"""
    return _extension_instance


@dataclass
class TriggerSlot:
    """トリガースロットの設定データクラス"""
    slot_id: str
    trigger_path: str
    correct_number: int
    placement_translate: Tuple[float, float, float]
    placement_rotate: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    proxy: bool = False
    real_path: str = ""
    task: bool = False
    task_path: str = ""
    display_name: str = ""
    additional_proxy_paths: List[str] = None  # 追加：複数proxyオブジェクトのパスリスト


class ItemSettingExtension(omni.ext.IExt):
    """アイテム配置・検証・状態管理を行う拡張機能"""

    def on_startup(self, _ext_id):
        """拡張機能の起動時に呼ばれる"""
        global _extension_instance
        _extension_instance = self

        carb.log_info("[item_setting] Extension startup")

        # USDコンテキスト取得
        self._usd_context = omni.usd.get_context()
        self._stage = None  # 初期化はNoneで、後で取得

        # トリガースロットの設定
        self._trigger_slots: List[TriggerSlot] = []
        self._setup_default_slots()

        # PhysXインターフェース
        self._physx_interface = None
        try:
            self._physx_interface = omni.physx.get_physx_interface()
        except Exception as e:
            carb.log_error(f"[item_setting] PhysXインターフェース取得失敗: {e}")

        # UI構築
        self._window = None
        self._build_ui()

        # ステージ読み込みイベントのリスナーを登録
        self._stage_event_sub = self._usd_context.get_stage_event_stream().create_subscription_to_pop(
            self._on_stage_event, name="item_setting stage event"
        )

        # Update Loopの登録（トリガー検知用）
        self._update_sub = None
        self._triggered_objects = {}  # {trigger_path: set(object_paths)}
        self._update_counter = 0  # デバッグ用フレームカウンター

        # Updateイベントストリームに登録
        app = omni.kit.app.get_app()
        self._update_sub = app.get_update_event_stream().create_subscription_to_pop(
            self._on_update, name="item_setting update"
        )

        # タイムラインイベント購読（シミュレーション停止時のクリーンアップ用）
        self._timeline_sub = None
        timeline = omni.timeline.get_timeline_interface()
        if timeline:
            self._timeline_sub = timeline.get_timeline_event_stream().create_subscription_to_pop(
                self._on_timeline_event, name="item_setting timeline event"
            )

        # 起動時に既にステージが開かれているかチェック
        existing_stage = self._usd_context.get_stage()
        if existing_stage:
            self._stage = existing_stage
            self._triggered_objects = {}
            self._update_counter = 0
            self._setup_triggers()

    def _on_stage_event(self, event):
        """ステージイベントのハンドラ"""
        # OPENEDイベントでセットアップ
        if event.type == int(omni.usd.StageEventType.OPENED):
            self._stage = self._usd_context.get_stage()
            if self._stage:
                self._triggered_objects = {}
                self._update_counter = 0
                self._setup_triggers()
            else:
                carb.log_error("[item_setting] ステージ取得失敗")

        # ステージクローズ時にクリーンアップ
        elif event.type == int(omni.usd.StageEventType.CLOSED):
            self._stage = None
            self._triggered_objects = {}
            self._update_counter = 0

    def _on_timeline_event(self, event):
        """タイムラインイベントのハンドラ（シミュレーション停止時のクリーンアップ）"""
        # STOPイベント（シミュレーション停止）を検出
        if event.type == int(omni.timeline.TimelineEventType.STOP):
            carb.log_info("[item_setting] シミュレーション停止 - クリーンアップ開始")
            self._cleanup_on_simulation_stop()

    def _cleanup_on_simulation_stop(self):
        """シミュレーション停止時のクリーンアップ処理"""
        carb.log_info("[item_setting] クリーンアップ処理開始")

        if not self._stage:
            carb.log_warn("[item_setting] ステージがNone、クリーンアップをスキップ")
            return

        try:
            # ステージ全体を走査して、配置済みオブジェクトを探す
            restored_normal_count = 0
            restored_proxy_count = 0

            for prim in self._stage.Traverse():
                # Meshタイプのプリムをチェック
                if prim.GetTypeName() != "Mesh":
                    continue

                # custom:placed 属性をチェック（配置されていないものはスキップ）
                placed_attr = prim.GetAttribute("custom:placed")
                if not placed_attr or not placed_attr.HasValue() or not placed_attr.Get():
                    continue  # 配置されていない

                # custom:proxy 属性をチェック
                proxy_attr = prim.GetAttribute("custom:proxy")
                is_proxy = proxy_attr.Get() if proxy_attr and proxy_attr.HasValue() else False

                if is_proxy:
                    # proxyシステムのクリーンアップ
                    # 1. proxyオブジェクトを表示
                    imageable = UsdGeom.Imageable(prim)
                    imageable.MakeVisible()

                    # 2. proxyのCollision有効化
                    collision_api = UsdPhysics.CollisionAPI(prim)
                    if collision_api:
                        collision_enabled_attr = collision_api.GetCollisionEnabledAttr()
                        if not collision_enabled_attr:
                            collision_enabled_attr = collision_api.CreateCollisionEnabledAttr()
                        collision_enabled_attr.Set(True)

                    # 3. proxyの親のRigidBodyを再有効化
                    parent_prim = prim.GetParent()
                    if parent_prim and parent_prim.IsValid() and parent_prim.HasAPI(UsdPhysics.RigidBodyAPI):
                        rb_api = UsdPhysics.RigidBodyAPI(parent_prim)
                        rb_enabled_attr = rb_api.GetRigidBodyEnabledAttr()
                        if not rb_enabled_attr:
                            rb_enabled_attr = rb_api.CreateRigidBodyEnabledAttr()
                        rb_enabled_attr.Set(True)

                    # 4. realオブジェクトのパスを取得して復元
                    real_path_attr = prim.GetAttribute("custom:real_path")
                    if real_path_attr and real_path_attr.HasValue():
                        real_path = real_path_attr.Get()
                        real_prim = self._stage.GetPrimAtPath(real_path)
                        if real_prim.IsValid():
                            # realオブジェクトを非表示
                            real_imageable = UsdGeom.Imageable(real_prim)
                            real_imageable.MakeInvisible()

                            # realのCollision無効化
                            real_collision_api = UsdPhysics.CollisionAPI(real_prim)
                            if real_collision_api:
                                real_collision_enabled_attr = real_collision_api.GetCollisionEnabledAttr()
                                if not real_collision_enabled_attr:
                                    real_collision_enabled_attr = real_collision_api.CreateCollisionEnabledAttr()
                                real_collision_enabled_attr.Set(False)

                            # realのplaced属性をFalse
                            real_placed_attr = real_prim.GetAttribute("custom:placed")
                            if real_placed_attr:
                                real_placed_attr.Set(False)

                            # realのtask属性をFalse
                            real_task_attr = real_prim.GetAttribute("custom:task")
                            if real_task_attr:
                                real_task_attr.Set(False)

                            restored_proxy_count += 1
                        else:
                            carb.log_warn(f"[item_setting] realオブジェクトが見つかりません: {real_path}")
                    else:
                        carb.log_warn(f"[item_setting] custom:real_path属性が見つかりません: {prim.GetPath()}")

                    # proxyのplaced属性もFalseに（次回使用のため）
                    if placed_attr:
                        placed_attr.Set(False)

                    # 追加のproxyオブジェクトを復元（additional_proxy_paths）
                    additional_paths_attr = prim.GetAttribute("custom:additional_proxy_paths")
                    if additional_paths_attr and additional_paths_attr.HasValue():
                        additional_paths_str = additional_paths_attr.Get()
                        if additional_paths_str:
                            additional_paths = additional_paths_str.split(",")
                            for additional_path in additional_paths:
                                additional_prim = self._stage.GetPrimAtPath(additional_path.strip())
                                if not additional_prim.IsValid():
                                    carb.log_warn(f"[item_setting] 追加proxyオブジェクトが見つかりません: {additional_path}")
                                    continue

                                # 表示する
                                additional_imageable = UsdGeom.Imageable(additional_prim)
                                additional_imageable.MakeVisible()

                                # Collision有効化（CollisionAPIがあれば）
                                additional_collision_api = UsdPhysics.CollisionAPI(additional_prim)
                                if additional_collision_api:
                                    additional_collision_enabled_attr = additional_collision_api.GetCollisionEnabledAttr()
                                    if not additional_collision_enabled_attr:
                                        additional_collision_enabled_attr = additional_collision_api.CreateCollisionEnabledAttr()
                                    additional_collision_enabled_attr.Set(True)

                else:
                    # 通常配置されたオブジェクト → RigidBodyを再有効化
                    parent_prim = prim.GetParent()
                    if not parent_prim or not parent_prim.IsValid():
                        continue

                    # 親のRigidBodyAPIを取得
                    if not parent_prim.HasAPI(UsdPhysics.RigidBodyAPI):
                        continue

                    rb_api = UsdPhysics.RigidBodyAPI(parent_prim)

                    # rigidBodyEnabledをTrueに戻す（再有効化）
                    rb_enabled_attr = rb_api.GetRigidBodyEnabledAttr()
                    if not rb_enabled_attr:
                        rb_enabled_attr = rb_api.CreateRigidBodyEnabledAttr()
                    rb_enabled_attr.Set(True)
                    restored_normal_count += 1

            carb.log_info(f"[item_setting] クリーンアップ完了: 通常オブジェクト{restored_normal_count}個、proxyシステム{restored_proxy_count}個を復元")

        except Exception as e:
            carb.log_error(f"[item_setting] クリーンアップ中にエラー発生: {e}")
            import traceback
            carb.log_error(f"[item_setting] トレースバック:\n{traceback.format_exc()}")

    def on_shutdown(self):
        """拡張機能のシャットダウン時に呼ばれる"""
        global _extension_instance
        _extension_instance = None

        # イベントサブスクリプションをクリーンアップ
        if hasattr(self, '_stage_event_sub') and self._stage_event_sub:
            self._stage_event_sub = None

        if hasattr(self, '_update_sub') and self._update_sub:
            self._update_sub = None

        if hasattr(self, '_timeline_sub') and self._timeline_sub:
            self._timeline_sub = None

        if self._window:
            self._window.destroy()
            self._window = None

        print("[item_setting] Extension shutdown")

    def _setup_default_slots(self):
        """デフォルトのトリガースロットを設定
        # 例: プロキシを使用しないスロット
        self._trigger_slots.append(
            TriggerSlot(
                slot_id="slot_1",
                trigger_path="/World/New_MillingMachine/Main/Doril/Trigger_Drill",
                correct_number=1,
                placement_translate=(0.0, 10.0, 0.0),
                placement_rotate=(0.0, 0.0, 0.0),
                proxy=False,
                display_name="ドリルスロット (Number=1)"
            )
        )

        # 例: プロキシを使用するスロット（VoxelMesh用）
        self._trigger_slots.append(
            TriggerSlot(
                slot_id="voxel_slot",
                trigger_path="/World/New_MillingMachine/Table/Set_Base/Trigger_Table",
                correct_number=2,
                placement_translate=(13.552419574874861, 0, 36.755128131831896),
                placement_rotate=(0.0, 0.0, 0.0),
                proxy=True,
                real_path="/World/New_MillingMachine/Table/VoxelMesh",
                task=True,
                task_path="",
                display_name="テーブルスロット (Number=2, Proxy使用)"
            )
        )

        # 例: 複数オブジェクトを一緒に非表示にするスロット（Joint接続オブジェクト用）
        # self._trigger_slots.append(
        #     TriggerSlot(
        #         slot_id="plug_cable_slot",
        #         trigger_path="/World/Industrial/Industrial/Trigger_Plug",
        #         correct_number=3,
        #         placement_translate=(115.0, -0.63, 78.5),
        #         placement_rotate=(0.0, 0.0, 0.0),
        #         proxy=True,
        #         real_path="/World/Industrial/Industrial/Plug_Real",
        #         task=True,
        #         task_path="",
        #         additional_proxy_paths=[
        #             "/World/New_MillingMachine/Plug/Cable_01"
        #         ],
        #         display_name="プラグとケーブル (Number=3, 複数Proxy使用)"
        #     )
        # )
        """

        self._trigger_slots.append(
            TriggerSlot(
                slot_id="Table_socket",
                trigger_path="/World/Industrial/Industrial/Trigger_Plug",
                correct_number=1,
                placement_translate=(0, 0, 0),
                placement_rotate=(0.0, 0.0, 0.0),
                proxy=True,
                real_path="/World/ケーブル_固定ver/Cable/Mesh",
                task=True,
                task_path="",
                additional_proxy_paths=[
                     "/World/New_MillingMachine/Plug/Cable_01"
                 ],
                display_name="テーブルのコンセント (Number=1, Proxy使用)"

            )
        )

        self._trigger_slots.append(
            TriggerSlot(
                slot_id="Drill_socket",
                trigger_path="/World/New_MillingMachine/Main/Doril/Trigger_Drill",
                correct_number=2,
                placement_translate=(13.552419574874861, 0, 36.755128131831896),
                placement_rotate=(0.0, 0.0, 0.0),
                proxy=True,
                real_path="/World/New_MillingMachine/Main/Doril/Drill/Drill/_______001",
                task=True,
                task_path="",
                display_name="ドリルチャック (Number=2, Proxy使用)"
            )
        )

        self._trigger_slots.append(
            TriggerSlot(
                slot_id="Workbench",
                trigger_path="/World/New_MillingMachine/Table/Set_Base/Trigger_Table",
                correct_number=3,
                placement_translate=(13.552419574874861, 0, 36.755128131831896),
                placement_rotate=(0.0, 0.0, 0.0),
                proxy=True,
                real_path="/World/New_MillingMachine/Table/VoxelMesh",
                task=True,
                task_path="",
                display_name="作業台 (Number=3, Proxy使用)"
            )
        )

        #Practice用
        self._trigger_slots.append(
            TriggerSlot(
                slot_id="slot_1",
                trigger_path="/World/Trigger/Trigger",
                correct_number=1,
                placement_translate=(-100, 85, -35),
                placement_rotate=(0.0, 0.0, 0.0),
                proxy=False,
                task=True,
                display_name="練習 (Number=1)"
            )
        )


    def _setup_triggers(self):
        """PhysX Triggerの初期化とスクリプト設定"""
        # ステージがNoneの場合は現在のステージを取得
        if not self._stage:
            self._stage = self._usd_context.get_stage()

        if not self._stage:
            carb.log_error("[item_setting] ステージが取得できません - セットアップを中断")
            return

        for i, slot in enumerate(self._trigger_slots):
            trigger_prim = self._stage.GetPrimAtPath(slot.trigger_path)
            if not trigger_prim.IsValid():
                carb.log_error(f"[item_setting] トリガープリムが無効: {slot.trigger_path}")
                continue

            # CollisionAPIの適用（必須）
            if not trigger_prim.HasAPI(UsdPhysics.CollisionAPI):
                UsdPhysics.CollisionAPI.Apply(trigger_prim)

            # PhysxTriggerAPIの適用
            if not trigger_prim.HasAPI(PhysxSchema.PhysxTriggerAPI):
                trigger_api = PhysxSchema.PhysxTriggerAPI.Apply(trigger_prim)
            else:
                trigger_api = PhysxSchema.PhysxTriggerAPI(trigger_prim)

            # トリガースクリプトをクリア（PhysxTriggerStateAPIと競合するため）
            enter_script_attr = trigger_api.GetOnEnterScriptAttr()
            if enter_script_attr:
                current_script = enter_script_attr.Get()
                if current_script and str(current_script):
                    carb.log_warn(f"[item_setting] OnEnterScriptが設定されています: {current_script} - クリア")
                    enter_script_attr.Set(Sdf.AssetPath(""))
            else:
                enter_script_attr = trigger_api.CreateOnEnterScriptAttr()
                enter_script_attr.Set(Sdf.AssetPath(""))

            leave_script_attr = trigger_api.GetOnLeaveScriptAttr()
            if leave_script_attr:
                current_script = leave_script_attr.Get()
                if current_script and str(current_script):
                    carb.log_warn(f"[item_setting] OnLeaveScriptが設定されています: {current_script} - クリア")
                    leave_script_attr.Set(Sdf.AssetPath(""))
            else:
                leave_script_attr = trigger_api.CreateOnLeaveScriptAttr()
                leave_script_attr.Set(Sdf.AssetPath(""))

            # PhysxTriggerStateAPIの適用（侵入検知用）
            if not trigger_prim.HasAPI(PhysxSchema.PhysxTriggerStateAPI):
                PhysxSchema.PhysxTriggerStateAPI.Apply(trigger_prim)

    def _on_update(self, event):
        """
        Update Loopでトリガー状態を監視（PhysX Scene Query使用）
        Args:
            event: Updateイベント
        """
        # フレームカウンター
        self._update_counter += 1

        # ステージが有効でない場合はスキップ
        if not self._stage:
            return

        # PhysXインターフェースが無い場合はスキップ
        if not self._physx_interface:
            return

        try:
            # PhysX Scene Queryインターフェースを取得
            scene_query = omni.physx.get_physx_scene_query_interface()
            if not scene_query:
                return

            # 各トリガースロットについてチェック
            for slot in self._trigger_slots:
                trigger_prim = self._stage.GetPrimAtPath(slot.trigger_path)
                if not trigger_prim.IsValid():
                    continue

                # トリガーのワールド座標とサイズを取得
                xformable = UsdGeom.Xformable(trigger_prim)
                world_tf = xformable.ComputeLocalToWorldTransform(Usd.TimeCode.Default())

                # トリガーの中心位置を取得
                trigger_center = world_tf.ExtractTranslation()

                # トリガーのバウンディングボックスを取得
                bbox_cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_])
                bbox = bbox_cache.ComputeWorldBound(trigger_prim)
                bbox_range = bbox.ComputeAlignedRange()

                # バウンディングボックスのサイズを計算
                bbox_size = bbox_range.GetSize()
                radius = max(bbox_size[0], bbox_size[1], bbox_size[2]) / 2.0

                # Overlap Sphereで範囲内のオブジェクトを検索
                # コールバックで収集するリスト
                detected_hits = []

                def report_hit(hit):
                    """overlap_sphereのコールバック関数"""
                    detected_hits.append(hit)
                    return True  # 継続して検索

                # overlap_sphere呼び出し（正しい引数順序: radius, pos, reportFn）
                hit_count = scene_query.overlap_sphere(
                    float(radius * 1.2),  # radius
                    carb.Float3(float(trigger_center[0]), float(trigger_center[1]), float(trigger_center[2])),  # pos
                    report_hit  # reportFn
                )

                # 検出されたオブジェクトのパスを取得
                current_colliders = set()
                for hit in detected_hits:
                    if hasattr(hit, 'rigid_body') and hit.rigid_body:
                        collider_path = hit.rigid_body
                        current_colliders.add(collider_path)

                if len(current_colliders) == 0:
                    # トリガー内にコライダーがいない
                    self._triggered_objects[slot.trigger_path] = set()
                    continue

                # 現在トリガー内にいるコライダーのセット
                current_colliders_set = set(current_colliders)

                # 前回の状態を取得（なければ空セット）
                previous_colliders = self._triggered_objects.get(slot.trigger_path, set())

                # 新しく侵入したコライダーを検出
                new_colliders = current_colliders_set - previous_colliders

                # 新しく侵入したコライダーに対してhandle_trigger_entryを呼び出す
                for collider_path in new_colliders:
                    # コライダーパスから実際のオブジェクトパスを特定
                    # overlap_sphereはRigidBodyを持つプリム（通常は親Xform）を返す
                    collider_prim = self._stage.GetPrimAtPath(collider_path)
                    if not collider_prim.IsValid():
                        carb.log_error(f"[item_setting] コライダープリム無効: {collider_path}")
                        continue

                    # 検出されたプリム（通常はRigidBodyを持つ親Xform）の子を探す
                    found_mesh = False
                    for child in collider_prim.GetChildren():
                        if child.GetTypeName() == "Mesh":
                            # custom:Number 属性をチェック
                            number_attr = child.GetAttribute("custom:Number")
                            if number_attr and number_attr.HasValue():
                                # このMeshオブジェクトに対して処理を実行
                                self.handle_trigger_entry(str(child.GetPath()), slot.trigger_path)
                                found_mesh = True
                                break

                    if not found_mesh:
                        # 子にMeshがない場合、検出されたプリム自身がMeshかチェック
                        if collider_prim.GetTypeName() == "Mesh":
                            number_attr = collider_prim.GetAttribute("custom:Number")
                            if number_attr and number_attr.HasValue():
                                self.handle_trigger_entry(str(collider_prim.GetPath()), slot.trigger_path)
                                found_mesh = True

                    if not found_mesh:
                        carb.log_warn(f"[item_setting] Number属性を持つMeshが見つかりません: {collider_path}")

                # 現在の状態を保存
                self._triggered_objects[slot.trigger_path] = current_colliders_set

        except Exception as e:
            carb.log_error(f"[item_setting] _on_update でエラー発生: {e}")
            import traceback
            carb.log_error(f"[item_setting] トレースバック:\n{traceback.format_exc()}")

    def _diagnose_triggers(self):
        """トリガーの詳細診断（デバッグ用）"""
        carb.log_info("[item_setting] トリガー診断開始")

        if not self._stage:
            carb.log_error("[item_setting] ステージがNone - 診断不可")
            return

        # シミュレーション状態をチェック
        timeline = omni.timeline.get_timeline_interface()
        is_playing = timeline.is_playing()
        carb.log_info(f"[item_setting] シミュレーション状態: {'実行中' if is_playing else '停止中'}")
        carb.log_info(f"[item_setting] ⚠️ PhysX Triggerはシミュレーション実行中のみ動作します")

        for i, slot in enumerate(self._trigger_slots):
            carb.log_info("")
            carb.log_info(f"[item_setting] --- スロット {i+1}/{len(self._trigger_slots)}: {slot.slot_id} ---")
            carb.log_info(f"[item_setting] トリガーパス: {slot.trigger_path}")

            trigger_prim = self._stage.GetPrimAtPath(slot.trigger_path)
            if not trigger_prim.IsValid():
                carb.log_error(f"[item_setting] ❌ トリガープリムが無効")
                continue

            carb.log_info(f"[item_setting] プリムタイプ: {trigger_prim.GetTypeName()}")

            # CollisionAPIチェック
            has_collision = trigger_prim.HasAPI(UsdPhysics.CollisionAPI)
            carb.log_info(f"[item_setting] CollisionAPI: {'✓ 適用済み' if has_collision else '❌ 未適用'}")

            # PhysxTriggerAPIチェック
            has_trigger_api = trigger_prim.HasAPI(PhysxSchema.PhysxTriggerAPI)
            carb.log_info(f"[item_setting] PhysxTriggerAPI: {'✓ 適用済み' if has_trigger_api else '❌ 未適用'}")

            # PhysxTriggerStateAPIチェック
            has_state_api = trigger_prim.HasAPI(PhysxSchema.PhysxTriggerStateAPI)
            carb.log_info(f"[item_setting] PhysxTriggerStateAPI: {'✓ 適用済み' if has_state_api else '❌ 未適用'}")

            # PhysxTriggerAPIのスクリプト設定をチェック
            if has_trigger_api:
                trigger_api = PhysxSchema.PhysxTriggerAPI(trigger_prim)

                # on_enter_script をチェック
                enter_script_attr = trigger_api.GetOnEnterScriptAttr()
                if enter_script_attr and enter_script_attr.HasValue():
                    enter_script = enter_script_attr.Get()
                    if enter_script and str(enter_script):
                        carb.log_warn(f"[item_setting] ⚠️ OnEnterScript設定あり: {enter_script}")
                        carb.log_warn(f"[item_setting] ⚠️ スクリプトが設定されているとPhysxTriggerStateAPIが動作しない可能性があります")
                    else:
                        carb.log_info(f"[item_setting] OnEnterScript: 空（正常）")
                else:
                    carb.log_info(f"[item_setting] OnEnterScript: 未設定（正常）")

                # on_leave_script をチェック
                leave_script_attr = trigger_api.GetOnLeaveScriptAttr()
                if leave_script_attr and leave_script_attr.HasValue():
                    leave_script = leave_script_attr.Get()
                    if leave_script and str(leave_script):
                        carb.log_warn(f"[item_setting] ⚠️ OnLeaveScript設定あり: {leave_script}")
                    else:
                        carb.log_info(f"[item_setting] OnLeaveScript: 空（正常）")
                else:
                    carb.log_info(f"[item_setting] OnLeaveScript: 未設定（正常）")

            if has_state_api:
                trigger_state_api = PhysxSchema.PhysxTriggerStateAPI(trigger_prim)
                triggered_collisions_rel = trigger_state_api.GetTriggeredCollisionsRel()
                if triggered_collisions_rel:
                    current_colliders = triggered_collisions_rel.GetTargets()
                    carb.log_info(f"[item_setting] 現在のコライダー数: {len(current_colliders)}")
                    for collider_path in current_colliders:
                        carb.log_info(f"[item_setting]   - {collider_path}")
                else:
                    carb.log_warn(f"[item_setting] TriggeredCollisionsRel が None")


    def _diagnose_object(self):
        """オブジェクトの物理設定を診断（デバッグ用）"""
        carb.log_info("[item_setting] オブジェクト診断開始")

        if not self._stage:
            carb.log_error("[item_setting] ステージがNone - 診断不可")
            return

        object_path = self._object_path_field.model.get_value_as_string()
        carb.log_info(f"[item_setting] 診断対象: {object_path}")

        object_prim = self._stage.GetPrimAtPath(object_path)
        if not object_prim.IsValid():
            carb.log_error(f"[item_setting] ❌ オブジェクトプリムが無効: {object_path}")
            return

        carb.log_info(f"[item_setting] プリムタイプ: {object_prim.GetTypeName()}")

        # 階層構造を表示
        parent_prim = object_prim.GetParent()
        if parent_prim.IsValid():
            carb.log_info(f"[item_setting] 親プリム: {parent_prim.GetPath()}")
            carb.log_info(f"[item_setting] 親タイプ: {parent_prim.GetTypeName()}")
        else:
            carb.log_warn(f"[item_setting] 親プリムなし")

        # オブジェクト自身のAPI確認
        carb.log_info("")
        carb.log_info(f"[item_setting] --- {object_path} の物理API ---")

        has_collision = object_prim.HasAPI(UsdPhysics.CollisionAPI)
        carb.log_info(f"[item_setting] CollisionAPI: {'✓ 適用済み' if has_collision else '❌ 未適用'}")

        has_rigidbody = object_prim.HasAPI(UsdPhysics.RigidBodyAPI)
        carb.log_info(f"[item_setting] RigidBodyAPI: {'✓ 適用済み' if has_rigidbody else '❌ 未適用'}")

        if has_rigidbody:
            rb_api = UsdPhysics.RigidBodyAPI(object_prim)
            kinematic_attr = rb_api.GetKinematicEnabledAttr()
            if kinematic_attr and kinematic_attr.HasValue():
                is_kinematic = kinematic_attr.Get()
                carb.log_info(f"[item_setting] KinematicEnabled: {is_kinematic} {'(Kinematic - 物理無効)' if is_kinematic else '(Dynamic - 物理有効)'}")
            else:
                carb.log_info(f"[item_setting] KinematicEnabled: 属性なし（デフォルト=Dynamic）")

        # 親プリムのAPI確認
        if parent_prim.IsValid():
            carb.log_info("")
            carb.log_info(f"[item_setting] --- {parent_prim.GetPath()} の物理API ---")

            parent_has_collision = parent_prim.HasAPI(UsdPhysics.CollisionAPI)
            carb.log_info(f"[item_setting] CollisionAPI: {'✓ 適用済み' if parent_has_collision else '❌ 未適用'}")

            parent_has_rigidbody = parent_prim.HasAPI(UsdPhysics.RigidBodyAPI)
            carb.log_info(f"[item_setting] RigidBodyAPI: {'✓ 適用済み' if parent_has_rigidbody else '❌ 未適用'}")

            if parent_has_rigidbody:
                rb_api = UsdPhysics.RigidBodyAPI(parent_prim)
                kinematic_attr = rb_api.GetKinematicEnabledAttr()
                if kinematic_attr and kinematic_attr.HasValue():
                    is_kinematic = kinematic_attr.Get()
                    carb.log_info(f"[item_setting] KinematicEnabled: {is_kinematic} {'(Kinematic - 物理無効)' if is_kinematic else '(Dynamic - 物理有効)'}")
                else:
                    carb.log_info(f"[item_setting] KinematicEnabled: 属性なし（デフォルト=Dynamic）")

        # 推奨設定を表示
        carb.log_info("")
        carb.log_info("[item_setting] --- 推奨設定 ---")
        carb.log_info("[item_setting] PhysX Triggerで検出されるには：")
        carb.log_info("[item_setting] 1. 親プリム（Xform）にRigidBodyAPI適用（Dynamic状態）")
        carb.log_info("[item_setting] 2. 子プリム（Mesh）にCollisionAPI適用")
        carb.log_info("[item_setting] 3. シミュレーション実行中（Playボタン押下）")


    def _build_ui(self):
        """UIウィンドウの構築"""
        self._window = ui.Window("Item Setting", width=400, height=300)
        with self._window.frame:
            with ui.VStack(spacing=5):
                ui.Label("アイテム配置システム", height=30, style={"font_size": 18})
                ui.Separator()

                ui.Label("設定済みトリガースロット:")
                for slot in self._trigger_slots:
                    with ui.HStack(height=20):
                        ui.Label(f"• {slot.display_name}", width=ui.Percent(70))
                        ui.Label(f"Number={slot.correct_number}", width=ui.Percent(30))

                ui.Spacer(height=10)
                ui.Button("トリガー再初期化", clicked_fn=self._setup_triggers, height=30)
                ui.Button("トリガー診断", clicked_fn=self._diagnose_triggers, height=30)

                ui.Spacer(height=10)
                ui.Label("オブジェクト診断:")
                self._object_path_field = ui.StringField(height=20)
                self._object_path_field.model.set_value("/World/ItemTray/Xform/Proxy_cube")
                ui.Button("オブジェクトの物理設定を確認", clicked_fn=self._diagnose_object, height=30)

    def handle_trigger_entry(self, object_path: str, trigger_path: str):
        """
        トリガー侵入時の処理
        Args:
            object_path: 侵入したオブジェクトのパス
            trigger_path: トリガーのパス
        """
        carb.log_info(f"[item_setting] handle_trigger_entry: {object_path} -> {trigger_path}")

        try:
            if not self._stage:
                carb.log_error("[item_setting] ステージがNone")
                return

            # トリガースロットを検索
            slot = None
            for s in self._trigger_slots:
                if s.trigger_path == trigger_path:
                    slot = s
                    break

            if not slot:
                carb.log_error(f"[item_setting] トリガースロット未登録: {trigger_path}")
                return

            carb.log_info(f"[item_setting] スロット発見: {slot.slot_id}, correct_number={slot.correct_number}, proxy={slot.proxy}")

            # オブジェクトのプリムを取得
            object_prim = self._stage.GetPrimAtPath(object_path)
            if not object_prim.IsValid():
                carb.log_error(f"[item_setting] オブジェクトプリムが無効: {object_path}")
                return

            carb.log_info(f"[item_setting] オブジェクトプリム有効: タイプ={object_prim.GetTypeName()}")

            # Number属性を確認
            number_attr = object_prim.GetAttribute("custom:Number")
            if not number_attr:
                carb.log_warn(f"[item_setting] custom:Number属性が存在しません: {object_path}")
                return

            if not number_attr.HasValue():
                carb.log_warn(f"[item_setting] custom:Number属性に値がありません: {object_path}")
                return

            item_number = number_attr.Get()
            carb.log_info(f"[item_setting] オブジェクトNumber値: {item_number}")

            # オブジェクトの親（Xform）を取得
            parent_prim = object_prim.GetParent()
            if not parent_prim.IsValid():
                carb.log_error(f"[item_setting] 親プリムが無効: {object_path}")
                return

            carb.log_info(f"[item_setting] 親プリム: {parent_prim.GetPath()}, タイプ={parent_prim.GetTypeName()}")

            # Number属性が一致するか確認
            if item_number == slot.correct_number:
                carb.log_info(f"[item_setting] ✓ Number一致: {item_number} == {slot.correct_number}")

                # proxy属性を確認
                proxy_attr = object_prim.GetAttribute("custom:proxy")
                is_proxy = proxy_attr.Get() if proxy_attr and proxy_attr.HasValue() else False
                carb.log_info(f"[item_setting] proxy属性: {is_proxy}")

                if is_proxy and slot.proxy:
                    # プロキシシステムでの配置
                    carb.log_info("[item_setting] プロキシシステムでの配置を実行")
                    self._place_item_with_proxy(object_prim, parent_prim, slot)
                elif not is_proxy and not slot.proxy:
                    # 通常の配置
                    carb.log_info("[item_setting] 通常配置を実行")
                    self._place_item_normal(object_prim, parent_prim, slot)
                else:
                    # プロキシ設定が不一致
                    carb.log_warn(f"[item_setting] プロキシ設定が不一致: is_proxy={is_proxy}, slot.proxy={slot.proxy}")
                    self._reset_item_to_original(object_prim, parent_prim)
            else:
                # Number不一致 - 元の位置に戻す
                carb.log_warn(f"[item_setting] ❌ Number不一致: {item_number} != {slot.correct_number}")
                self._reset_item_to_original(object_prim, parent_prim)

        except Exception as e:
            carb.log_error(f"[item_setting] handle_trigger_entry でエラー発生: {e}")
            import traceback
            carb.log_error(f"[item_setting] トレースバック:\n{traceback.format_exc()}")

    def _place_item_normal(self, object_prim: Usd.Prim, parent_prim: Usd.Prim, slot: TriggerSlot):
        """
        通常のアイテム配置（proxy:False）
        Args:
            object_prim: オブジェクトプリム
            parent_prim: 親プリム（Xform）
            slot: トリガースロット
        """
        carb.log_info(f"[item_setting] _place_item_normal: {object_prim.GetPath()}")
        carb.log_info(f"[item_setting] slot: {slot.slot_id}")

        try:
            # 1. 親のRigid Body Enabledを無効化
            carb.log_info("[item_setting] Rigid Body Enabled無効化処理開始")
            rb_api = UsdPhysics.RigidBodyAPI(parent_prim)
            if rb_api:
                # Rigid Body Enabledを無効化
                rb_enabled_attr = rb_api.GetRigidBodyEnabledAttr()
                if not rb_enabled_attr:
                    rb_enabled_attr = rb_api.CreateRigidBodyEnabledAttr()
                rb_enabled_attr.Set(False)

                carb.log_info(f"[item_setting] ✓ Rigid Body Enabled無効化完了: {parent_prim.GetPath()}")
            else:
                carb.log_warn(f"[item_setting] RigidBodyAPI取得失敗")

            # 2. 親の位置・回転を設定
            carb.log_info("[item_setting] Transform設定開始")
            xformable = UsdGeom.Xformable(parent_prim)

            # TranslateOpを設定
            translate_op = None
            for xform_op in xformable.GetOrderedXformOps():
                if xform_op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
                    translate_op = xform_op
                    break

            if not translate_op:
                translate_op = xformable.AddTranslateOp()
                carb.log_info("[item_setting] TranslateOp作成")

            translate_op.Set(Gf.Vec3d(*slot.placement_translate))
            carb.log_info(f"[item_setting] ✓ 位置設定: {slot.placement_translate}")

            # OrientOpを設定（オイラー角からクォータニオンに変換）
            orient_op = None
            for xform_op in xformable.GetOrderedXformOps():
                if xform_op.GetOpType() == UsdGeom.XformOp.TypeOrient:
                    orient_op = xform_op
                    break

            if not orient_op:
                orient_op = xformable.AddOrientOp()
                carb.log_info("[item_setting] OrientOp作成")

            # XYZオイラー角からクォータニオンに変換
            rotation_x = Gf.Rotation(Gf.Vec3d(1, 0, 0), slot.placement_rotate[0])
            rotation_y = Gf.Rotation(Gf.Vec3d(0, 1, 0), slot.placement_rotate[1])
            rotation_z = Gf.Rotation(Gf.Vec3d(0, 0, 1), slot.placement_rotate[2])
            final_rotation = rotation_z * rotation_y * rotation_x
            orient_op.Set(Gf.Quatf(final_rotation.GetQuat()))
            carb.log_info(f"[item_setting] ✓ 回転設定: {slot.placement_rotate}")

            # 3. オブジェクトのplaced属性とtask属性を更新
            carb.log_info("[item_setting] カスタム属性更新開始")
            placed_attr = object_prim.GetAttribute("custom:placed")
            if not placed_attr:
                placed_attr = object_prim.CreateAttribute("custom:placed", Sdf.ValueTypeNames.Bool)
                carb.log_info("[item_setting] custom:placed属性作成")
            placed_attr.Set(True)

            task_attr = object_prim.GetAttribute("custom:task")
            if not task_attr:
                task_attr = object_prim.CreateAttribute("custom:task", Sdf.ValueTypeNames.Bool)
                carb.log_info("[item_setting] custom:task属性作成")
            task_attr.Set(slot.task)

        except Exception as e:
            carb.log_error(f"[item_setting] _place_item_normal でエラー発生: {e}")
            import traceback
            carb.log_error(f"[item_setting] トレースバック:\n{traceback.format_exc()}")

    def _place_item_with_proxy(self, object_prim: Usd.Prim, parent_prim: Usd.Prim, slot: TriggerSlot):
        """
        プロキシシステムでのアイテム配置（proxy:True）
        Args:
            object_prim: プロキシオブジェクトプリム
            parent_prim: プロキシの親プリム（Xform）
            slot: トリガースロット
        """
        carb.log_info(f"[item_setting] _place_item_with_proxy: {object_prim.GetPath()}")
        carb.log_info(f"[item_setting] real_path: {slot.real_path}")

        try:
            # 1. プロキシの親のRigid Body Enabledを無効化
            carb.log_info("[item_setting] プロキシRigid Body Enabled無効化処理開始")
            rb_api = UsdPhysics.RigidBodyAPI(parent_prim)
            if rb_api:
                # Rigid Body Enabledを無効化
                rb_enabled_attr = rb_api.GetRigidBodyEnabledAttr()
                if not rb_enabled_attr:
                    rb_enabled_attr = rb_api.CreateRigidBodyEnabledAttr()
                rb_enabled_attr.Set(False)

                carb.log_info(f"[item_setting] ✓ プロキシRigid Body Enabled無効化完了: {parent_prim.GetPath()}")
            else:
                carb.log_warn("[item_setting] プロキシRigidBodyAPI取得失敗")

            # 2. プロキシオブジェクトを非表示にしてCollision無効化
            carb.log_info("[item_setting] プロキシ非表示処理開始")
            imageable = UsdGeom.Imageable(object_prim)
            imageable.MakeInvisible()
            carb.log_info(f"[item_setting] ✓ プロキシ非表示: {object_prim.GetPath()}")

            collision_api = UsdPhysics.CollisionAPI(object_prim)
            if collision_api:
                collision_api.GetCollisionEnabledAttr().Set(False)
                carb.log_info("[item_setting] ✓ プロキシCollision無効化")

            # 3. プロキシの親の位置・回転を設定
            carb.log_info("[item_setting] プロキシTransform設定開始")
            xformable = UsdGeom.Xformable(parent_prim)

            # TranslateOp
            translate_op = None
            for xform_op in xformable.GetOrderedXformOps():
                if xform_op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
                    translate_op = xform_op
                    break

            if not translate_op:
                translate_op = xformable.AddTranslateOp()

            translate_op.Set(Gf.Vec3d(*slot.placement_translate))
            carb.log_info(f"[item_setting] ✓ プロキシ位置設定: {slot.placement_translate}")

            # OrientOp
            orient_op = None
            for xform_op in xformable.GetOrderedXformOps():
                if xform_op.GetOpType() == UsdGeom.XformOp.TypeOrient:
                    orient_op = xform_op
                    break

            if not orient_op:
                orient_op = xformable.AddOrientOp()

            rotation_x = Gf.Rotation(Gf.Vec3d(1, 0, 0), slot.placement_rotate[0])
            rotation_y = Gf.Rotation(Gf.Vec3d(0, 1, 0), slot.placement_rotate[1])
            rotation_z = Gf.Rotation(Gf.Vec3d(0, 0, 1), slot.placement_rotate[2])
            final_rotation = rotation_z * rotation_y * rotation_x
            orient_op.Set(Gf.Quatf(final_rotation.GetQuat()))
            carb.log_info(f"[item_setting] ✓ プロキシ回転設定: {slot.placement_rotate}")

            # 4. 実オブジェクト（real_object）を表示
            carb.log_info(f"[item_setting] 実オブジェクト処理開始: {slot.real_path}")
            real_prim = self._stage.GetPrimAtPath(slot.real_path)
            if not real_prim.IsValid():
                carb.log_error(f"[item_setting] ❌ 実オブジェクトが見つかりません: {slot.real_path}")
                return

            carb.log_info(f"[item_setting] 実オブジェクト有効: タイプ={real_prim.GetTypeName()}")

            real_imageable = UsdGeom.Imageable(real_prim)
            real_imageable.MakeVisible()
            carb.log_info(f"[item_setting] ✓ 実オブジェクト表示: {slot.real_path}")

            # 実オブジェクトのCollision有効化
            real_collision_api = UsdPhysics.CollisionAPI(real_prim)
            if real_collision_api:
                real_collision_api.GetCollisionEnabledAttr().Set(True)
                carb.log_info("[item_setting] ✓ 実オブジェクトCollision有効化")

            # 実オブジェクトのplaced属性とtask属性を更新
            carb.log_info("[item_setting] 実オブジェクトカスタム属性更新開始")
            placed_attr = real_prim.GetAttribute("custom:placed")
            if not placed_attr:
                placed_attr = real_prim.CreateAttribute("custom:placed", Sdf.ValueTypeNames.Bool)
                carb.log_info("[item_setting] custom:placed属性作成")
            placed_attr.Set(True)

            task_attr = real_prim.GetAttribute("custom:task")
            if not task_attr:
                task_attr = real_prim.CreateAttribute("custom:task", Sdf.ValueTypeNames.Bool)
                carb.log_info("[item_setting] custom:task属性作成")
            task_attr.Set(slot.task)

            # 5. プロキシオブジェクトにrealオブジェクトのパスを保存（クリーンアップ用）
            carb.log_info("[item_setting] プロキシにreal_path属性を保存")
            real_path_attr = object_prim.GetAttribute("custom:real_path")
            if not real_path_attr:
                real_path_attr = object_prim.CreateAttribute("custom:real_path", Sdf.ValueTypeNames.String)
            real_path_attr.Set(slot.real_path)
            carb.log_info(f"[item_setting] ✓ custom:real_path保存: {slot.real_path}")

            # 6. プロキシオブジェクトにplaced属性を設定（クリーンアップ処理で検出されるため）
            carb.log_info("[item_setting] プロキシにplaced属性を設定")
            proxy_placed_attr = object_prim.GetAttribute("custom:placed")
            if not proxy_placed_attr:
                proxy_placed_attr = object_prim.CreateAttribute("custom:placed", Sdf.ValueTypeNames.Bool)
                carb.log_info("[item_setting] proxyにcustom:placed属性作成")
            proxy_placed_attr.Set(True)
            carb.log_info(f"[item_setting] ✓ proxy custom:placed = True")

            # 7.real_objectにパスを設定
            proxy_path_attr = real_prim.GetAttribute("custom:proxy_path")
            if not proxy_path_attr or not proxy_path_attr.IsValid():
                proxy_path_attr = real_prim.CreateAttribute("custom:proxy_path", Sdf.ValueTypeNames.String)
                carb.log_info("[item_setting] real_primにcustom:proxy_path属性作成")
            proxy_path_attr.Set(str(object_prim.GetPath()))

            # 8. 追加のproxyオブジェクトを処理（additional_proxy_paths）
            if slot.additional_proxy_paths:
                carb.log_info(f"[item_setting] 追加proxyオブジェクト処理開始: {len(slot.additional_proxy_paths)}個")

                for additional_path in slot.additional_proxy_paths:
                    additional_prim = self._stage.GetPrimAtPath(additional_path)
                    if not additional_prim.IsValid():
                        carb.log_warn(f"[item_setting] 追加proxyオブジェクトが見つかりません: {additional_path}")
                        continue

                    # 非表示にする
                    additional_imageable = UsdGeom.Imageable(additional_prim)
                    additional_imageable.MakeInvisible()
                    carb.log_info(f"[item_setting] ✓ 追加proxy非表示: {additional_path}")

                    # Collision無効化（CollisionAPIがあれば）
                    additional_collision_api = UsdPhysics.CollisionAPI(additional_prim)
                    if additional_collision_api:
                        additional_collision_api.GetCollisionEnabledAttr().Set(False)
                        carb.log_info(f"[item_setting] ✓ 追加proxyCollision無効化: {additional_path}")

                # プロキシオブジェクトにadditional_proxy_pathsを保存（クリーンアップ用）
                additional_paths_str = ",".join(slot.additional_proxy_paths)
                additional_paths_attr = object_prim.GetAttribute("custom:additional_proxy_paths")
                if not additional_paths_attr:
                    additional_paths_attr = object_prim.CreateAttribute("custom:additional_proxy_paths", Sdf.ValueTypeNames.String)
                additional_paths_attr.Set(additional_paths_str)
                carb.log_info(f"[item_setting] ✓ custom:additional_proxy_paths保存: {additional_paths_str}")

        except Exception as e:
            carb.log_error(f"[item_setting] _place_item_with_proxy でエラー発生: {e}")
            import traceback
            carb.log_error(f"[item_setting] トレースバック:\n{traceback.format_exc()}")

    def _reset_item_to_original(self, object_prim: Usd.Prim, parent_prim: Usd.Prim):
        """
        アイテムを元の位置に戻す（Number不一致時）
        Args:
            object_prim: オブジェクトプリム
            parent_prim: 親プリム（Xform）
        """
        carb.log_info(f"[item_setting] _reset_item_to_original: {object_prim.GetPath()}")

        try:
            # 1. 親のRigid Body Enabledを無効化
            carb.log_info("[item_setting] Rigid Body Enabled無効化処理開始")
            rb_api = UsdPhysics.RigidBodyAPI(parent_prim)
            if rb_api:
                # Rigid Body Enabledを無効化
                rb_enabled_attr = rb_api.GetRigidBodyEnabledAttr()
                if not rb_enabled_attr:
                    rb_enabled_attr = rb_api.CreateRigidBodyEnabledAttr()
                rb_enabled_attr.Set(False)

                carb.log_info("[item_setting] ✓ Rigid Body Enabled無効化完了")

            # 2. プロキシのCollision有効化
            collision_api = UsdPhysics.CollisionAPI(object_prim)
            if collision_api:
                collision_api.GetCollisionEnabledAttr().Set(False)
                carb.log_info("[item_setting] Collision無効化")

            # 3. 元の位置を取得
            carb.log_info("[item_setting] 元の位置取得開始")
            original_pos_attr = object_prim.GetAttribute("custom:original_position")
            if not original_pos_attr or not original_pos_attr.HasValue():
                carb.log_error(f"[item_setting] ❌ 元の位置が保存されていません: {object_prim.GetPath()}")
                return

            original_position = original_pos_attr.Get()
            carb.log_info(f"[item_setting] 元の位置: {original_position}")

            # 4. 親の位置を元に戻す
            carb.log_info("[item_setting] Transform設定開始")
            xformable = UsdGeom.Xformable(parent_prim)

            translate_op = None
            for xform_op in xformable.GetOrderedXformOps():
                if xform_op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
                    translate_op = xform_op
                    break

            if not translate_op:
                translate_op = xformable.AddTranslateOp()
                carb.log_info("[item_setting] TranslateOp作成")

            collision_api.GetCollisionEnabledAttr().Set(True)
            carb.log_info("[item_setting] Collision有効化")

            # 5. 親のRigid Body Enabledを有効化
            carb.log_info("[item_setting] Rigid Body Enabled有効化処理開始")
            rb_enabled_attr = rb_api.CreateRigidBodyEnabledAttr()
            rb_enabled_attr.Set(True)
            carb.log_info("[item_setting] ✓ Rigid Body Enabled有効化完了")

            translate_op.Set(Gf.Vec3d(original_position[0], original_position[1], original_position[2]))
            carb.log_info(f"[item_setting] ✓ 元の位置に戻しました: {parent_prim.GetPath()} -> {original_position}")

        except Exception as e:
            carb.log_error(f"[item_setting] _reset_item_to_original でエラー発生: {e}")
            import traceback
            carb.log_error(f"[item_setting] トレースバック:\n{traceback.format_exc()}")

    def remove_item(self, object_path: str):
        """
        配置されたアイテムを取り外す（VR UIから呼ばれる）
        Args:
            object_path: 取り外すオブジェクトのパス
        """
        if not self._stage:
            carb.log_warn("[item_setting] ステージが取得できません")
            return

        object_prim = self._stage.GetPrimAtPath(object_path)
        if not object_prim.IsValid():
            carb.log_warn(f"[item_setting] オブジェクトが見つかりません: {object_path}")
            return

        # proxy属性を確認
        proxy_attr = object_prim.GetAttribute("custom:proxy")
        is_proxy = proxy_attr.Get() if proxy_attr and proxy_attr.HasValue() else False

        if is_proxy:
            # プロキシシステムの取り外し
            self._remove_item_proxy(object_prim)
        else:
            # 通常アイテムの取り外し
            self._remove_item_normal(object_prim)

        carb.log_info(f"[item_setting] アイテム取り外し完了: {object_path}")

    def _remove_item_proxy(self, object_prim: Usd.Prim):
        """
        プロキシシステムアイテムの取り外し
        Args:
            object_prim: 実オブジェクト（real_object）のプリム
        """
        carb.log_info(f"[item_setting] _remove_item_proxy開始: {object_prim.GetPath()}")

        # 1. real_objectからproxy_pathを取得
        proxy_path_attr = object_prim.GetAttribute("custom:proxy_path")
        if not proxy_path_attr or not proxy_path_attr.HasValue():
            carb.log_error(f"[item_setting] custom:proxy_path属性が見つかりません: {object_prim.GetPath()}")
            return

        proxy_path = proxy_path_attr.Get()
        carb.log_info(f"[item_setting] proxy_path取得: {proxy_path}")

        proxy_prim = self._stage.GetPrimAtPath(proxy_path)
        if not proxy_prim.IsValid():
            carb.log_error(f"[item_setting] proxyオブジェクトが見つかりません: {proxy_path}")
            return

        # 2. proxyオブジェクトを再表示
        carb.log_info("[item_setting] proxyオブジェクトを再表示")
        proxy_imageable = UsdGeom.Imageable(proxy_prim)
        proxy_imageable.MakeVisible()

        carb.log_info(f"[item_setting] ✓ proxy再表示: {proxy_path}")

        # 追加のproxyオブジェクトを再表示（additional_proxy_paths）
        additional_paths_attr = proxy_prim.GetAttribute("custom:additional_proxy_paths")
        if additional_paths_attr and additional_paths_attr.HasValue():
            additional_paths_str = additional_paths_attr.Get()
            if additional_paths_str:
                additional_paths = additional_paths_str.split(",")
                carb.log_info(f"[item_setting] 追加proxyオブジェクト再表示開始: {len(additional_paths)}個")

                for additional_path in additional_paths:
                    additional_path = additional_path.strip()
                    additional_prim = self._stage.GetPrimAtPath(additional_path)
                    if not additional_prim.IsValid():
                        carb.log_warn(f"[item_setting] 追加proxyオブジェクトが見つかりません: {additional_path}")
                        continue

                    # 表示する
                    additional_imageable = UsdGeom.Imageable(additional_prim)
                    additional_imageable.MakeVisible()
                    carb.log_info(f"[item_setting] ✓ 追加proxy再表示: {additional_path}")

                    # Collision有効化（CollisionAPIがあれば）
                    additional_collision_api = UsdPhysics.CollisionAPI(additional_prim)
                    if additional_collision_api:
                        collision_enabled_attr = additional_collision_api.GetCollisionEnabledAttr()
                        if collision_enabled_attr:
                            collision_enabled_attr.Set(True)
                            carb.log_info(f"[item_setting] ✓ 追加proxyCollision有効化: {additional_path}")
        else:
            carb.log_info("[item_setting] additional_proxy_paths属性なし、追加proxy処理をスキップ")

        # 3. proxyのCollision有効化
        proxy_collision_api = UsdPhysics.CollisionAPI(proxy_prim)
        if proxy_collision_api:
            proxy_collision_api.GetCollisionEnabledAttr().Set(True)
            carb.log_info("[item_setting] ✓ proxyのCollision有効化")

        # 4.proxyのplaced属性を無効化
        placed_attr = proxy_prim.GetAttribute("custom:placed")
        if placed_attr:
            placed_attr.Set(False)
            carb.log_info("[item_setting] ✓ proxy_object custom:placed=False")

        # 4. real_objectを非表示にしてCollision無効化
        carb.log_info(f"[item_setting] real_object非表示処理: {object_prim.GetPath()}")
        real_imageable = UsdGeom.Imageable(object_prim)
        real_imageable.MakeInvisible()
        carb.log_info(f"[item_setting] ✓ real_object非表示")

        real_collision_api = UsdPhysics.CollisionAPI(object_prim)
        if real_collision_api:
            real_collision_api.GetCollisionEnabledAttr().Set(False)
            carb.log_info("[item_setting] ✓ real_objectのCollision無効化")

        # 5. real_objectのplaced属性とtask属性をFalseに
        placed_attr = object_prim.GetAttribute("custom:placed")
        if placed_attr:
            placed_attr.Set(False)
            carb.log_info("[item_setting] ✓ real_object custom:placed=False")

        task_attr = object_prim.GetAttribute("custom:task")
        if task_attr:
            task_attr.Set(False)
            carb.log_info("[item_setting] ✓ real_object custom:task=False")

        # 6. proxyの親を元の位置に戻す
        carb.log_info("[item_setting] proxyの親を元の位置に戻す")
        parent_prim = proxy_prim.GetParent()
        if parent_prim.IsValid():
            # proxyオブジェクトから元の位置を取得
            original_pos_attr = proxy_prim.GetAttribute("custom:original_position")
            if original_pos_attr and original_pos_attr.HasValue():
                original_position = original_pos_attr.Get()
                carb.log_info(f"[item_setting] 元の位置: {original_position}")

                xformable = UsdGeom.Xformable(parent_prim)
                translate_op = None
                for xform_op in xformable.GetOrderedXformOps():
                    if xform_op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
                        translate_op = xform_op
                        break

                if not translate_op:
                    translate_op = xformable.AddTranslateOp()

                translate_op.Set(Gf.Vec3d(original_position[0], original_position[1], original_position[2]))
                carb.log_info(f"[item_setting] ✓ proxy位置リセット: {original_position}")

            # 7. proxyの親のRigidBody Enabledを有効化
            carb.log_info("[item_setting] proxyの親のRigidBody Enabled有効化")
            rb_api = UsdPhysics.RigidBodyAPI(parent_prim)
            if rb_api:
                rb_enabled_attr = rb_api.GetRigidBodyEnabledAttr()
                if not rb_enabled_attr:
                    rb_enabled_attr = rb_api.CreateRigidBodyEnabledAttr()
                rb_enabled_attr.Set(True)
                carb.log_info("[item_setting] ✓ proxyの親のRigidBody Enabled有効化")

        carb.log_info(f"[item_setting] プロキシアイテム取り外し完了: proxy={proxy_path}, real={object_prim.GetPath()}")

    def _remove_item_normal(self, object_prim: Usd.Prim):
        """
        通常アイテムの取り外し
        Args:
            object_prim: オブジェクトプリム
        """
        parent_prim = object_prim.GetParent()
        if not parent_prim.IsValid():
            carb.log_warn(f"[item_setting] 親プリムが取得できません: {object_prim.GetPath()}")
            return

        # 1. 元の位置に戻す
        original_pos_attr = object_prim.GetAttribute("custom:original_position")
        if original_pos_attr and original_pos_attr.HasValue():
            original_position = original_pos_attr.Get()

            xformable = UsdGeom.Xformable(parent_prim)
            translate_op = None
            for xform_op in xformable.GetOrderedXformOps():
                if xform_op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
                    translate_op = xform_op
                    break

            if not translate_op:
                translate_op = xformable.AddTranslateOp()

            translate_op.Set(Gf.Vec3d(original_position[0], original_position[1], original_position[2]))

        # 2. 親のRigidBodyを再有効化
        rb_api = UsdPhysics.RigidBodyAPI(parent_prim)
        if rb_api:
            rb_api.CreateRigidBodyEnabledAttr().Set(True)

        # 3. placed属性とtask属性をFalseに
        placed_attr = object_prim.GetAttribute("custom:placed")
        if placed_attr:
            placed_attr.Set(False)

        task_attr = object_prim.GetAttribute("custom:task")
        if task_attr:
            task_attr.Set(False)

        carb.log_info(f"[item_setting] 通常アイテム取り外し: {object_prim.GetPath()}")
