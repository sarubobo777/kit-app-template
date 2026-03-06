import omni.ext
import omni.usd
import omni.timeline
import carb
from pxr import Usd, Sdf, Gf

# ... (_original_prim_properties_state と _timeline_event_subscription のグローバル変数宣言はそのまま) ...

class SimulationResetExtension(omni.ext.IExt):
    def on_startup(self, ext_id):
        carb.log_info(f"[SimulationResetExtension] {ext_id} startup")

        self._timeline = omni.timeline.get_timeline_interface()
        
        # --- ここを修正 ---
        # self._timeline.set_timeline_event_stream_enabled(True) # この行を削除またはコメントアウト
        
        # タイムラインイベントを購読 (修正なし、ただし上記行を削除した前提)
        global _timeline_event_subscription
        _timeline_event_subscription = self._timeline.get_timeline_event_stream().create_subscription_to_pop(
            self._on_timeline_event_callback
        )
        
        carb.log_info("Timeline event listener registered.")

    # 拡張機能のシャットダウン時に呼び出されるメソッド
    def on_shutdown(self):
        carb.log_info("[SimulationResetExtension] shutdown")
        global _timeline_event_subscription
        if _timeline_event_subscription:
            # イベント購読を解除し、リソースを解放
            _timeline_event_subscription = None 
            carb.log_info("Timeline event listener unregistered.")

        # 保存しておいた状態をクリア
        _original_prim_properties_state.clear()
        carb.log_info("Cleared saved property states.")

    def _on_timeline_event_callback(self, e):
        """タイムラインイベントが発生したときに呼び出されるコールバック関数"""
        # --- ここを修正 ---
        # event_type = e.get_type() # この行を削除
        event_type = e.type # <-- この行に修正。イベントオブジェクトの 'type' 属性に直接アクセス

        if event_type == omni.timeline.TimelineEventType.PLAY:
            carb.log_info("Timeline Event: PLAY (Simulation Started). Saving current properties.")
            self._save_current_properties_state() # シミュレーション開始時に現在のプロパティを保存

        elif event_type == omni.timeline.TimelineEventType.STOP:
            carb.log_info("Timeline Event: STOP (Simulation Stopped). Restoring properties.")
            self._restore_original_properties() # シミュレーション停止時にプロパティをリセット
        
        # carb.log_info(f"Unhandled Timeline Event: {event_type}") # デバッグ用

    def _save_current_properties_state(self):
        """シミュレーション開始時に、変更される可能性のあるプロパティの現在の値を保存する"""
        global _original_prim_properties_state
        _original_prim_properties_state.clear() # 前回の状態をクリア

        stage = omni.usd.get_context().get_stage()
        
        # --- ここで、リセットしたいオブジェクトとプロパティを特定するロジック ---
        # 例1: 特定のオブジェクトの翻訳属性を保存
        target_prim_path = "/World/Workpiece" # <-- あなたの対象オブジェクトのパスに修正
        prim = stage.GetPrimAtPath(Sdf.Path(target_prim_path))

        if prim and prim.IsValid():
            attr_name = "xformOp:translation"
            attr = prim.GetAttribute(attr_name)
            if attr and attr.IsValid():
                _original_prim_properties_state[f"{target_prim_path}.{attr_name}"] = attr.Get()
                carb.log_info(f"Saved original {attr_name} for {target_prim_path}: {attr.Get()}")
            else:
                carb.log_warn(f"Attribute {attr_name} not found or invalid on {target_prim_path}. Skipping save.")
        else:
            carb.log_warn(f"Target prim '{target_prim_path}' not found or invalid. Skipping save.")

        # 例2: シーン内の全ての剛体の位置を保存 (物理シミュレーション対象を広くカバーする場合)
        # from pxr import UsdPhysics
        # for p in Usd.PrimRange(stage.GetPseudoRoot()):
        #     if p.HasAPI(UsdPhysics.RigidBodyAPI):
        #         prim_path = str(p.GetPath())
        #         attr_name = "xformOp:translation"
        #         attr = p.GetAttribute(attr_name)
        #         if attr and attr.IsValid():
        #             _original_prim_properties_state[f"{prim_path}.{attr_name}"] = attr.Get()
        #             # carb.log_info(f"Saved {attr_name} for {prim_path}: {attr.Get()}")
        #         else:
        #             carb.log_warn(f"RigidBody prim '{prim_path}' has no {attr_name}.")
        #             # RigidBodyだがtranslateがない場合も考慮 (例: 変換が親に継承されているなど)

    def _restore_original_properties(self):
        """シミュレーション停止時に、保存しておいた元のプロパティ値を復元する"""
        global _original_prim_properties_state
        if not _original_prim_properties_state:
            carb.log_warn("No original properties saved to restore.")
            return

        stage = omni.usd.get_context().get_stage()
        
        for prop_full_path, original_value in _original_prim_properties_state.items():
            prim_path_str, attr_name = prop_full_path.rsplit('.', 1)
            prim_path = Sdf.Path(prim_path_str)

            prim = stage.GetPrimAtPath(prim_path)
            if prim and prim.IsValid():
                attr = prim.GetAttribute(attr_name)
                if attr and attr.IsValid():
                    # 属性の値を元に戻す
                    attr.Set(original_value)
                    carb.log_info(f"Restored {attr_name} for {prim_path}: {original_value}")
                else:
                    carb.log_warn(f"Attribute {attr_name} not found or invalid on {prim_path} during restore.")
            else:
                carb.log_warn(f"Prim not found at path: {prim_path_str} during restore.")

        _original_prim_properties_state.clear() # 復元後、保存データをクリア