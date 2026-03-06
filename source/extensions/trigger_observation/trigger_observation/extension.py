# extension.py (セットアップ担当)
import omni.ext
import omni.log
import omni.usd
import os
from pxr import Usd, PhysxSchema

LOG_PREFIX = "[my_extension][trigger_observation]"

class TriggerObservationExtension(omni.ext.IExt):

    def on_startup(self, ext_id: str):
        omni.log.info(f"{LOG_PREFIX} PhysX Trigger Setup Extension startup.")
        self._ext_id = ext_id
        self._setup_all_triggers()

    def on_shutdown(self):
        omni.log.info(f"{LOG_PREFIX} Extension shutdown.")

    def _get_script_path(self):
        """
        'check_item_script.py' の絶対パスを直接指定します。
        """
        # ▼▼▼【重要】ご自身の環境に合わせて、このパスを正確に修正してください ▼▼▼
        # これまでのログから、おそらく以下のパスになります。
        # 文字列の前の 'r' は、Windowsのパス区切り文字'\'を正しく扱うためのおまじないです。
        script_path = r"C:\Users\nryou\Documents\Omniverse\zemiProject\kit-app-template\source\extensions\trigger_observation\trigger_observation\check_item_script.py"

        # ▲▲▲ ここまで ▲▲▲

        return script_path

    def _setup_all_triggers(self):
        """
        シーン内の全てのトリガーを探し出し、スクリプト実行の設定を行います。
        """
        stage = omni.usd.get_context().get_stage()
        if not stage:
            omni.log.warn(f"{LOG_PREFIX} Stage not found.")
            return

        script_path_to_run = self._get_script_path()
        if not os.path.exists(script_path_to_run):
            omni.log.error(f"{LOG_PREFIX} Logic script not found at '{script_path_to_run}'!")
            return

        omni.log.info(f"{LOG_PREFIX} Using logic script: {script_path_to_run}")

        # シーン全体をスキャン
        for prim in stage.Traverse():
            # "correct_item" 属性を持つプリムをトリガーとみなす
            # 属性名の揺れを考慮 ("custom:correct_item" または "correct_item")
            if prim.HasAttribute("custom:correct_item") or prim.HasAttribute("correct_item"):
                trigger_path = str(prim.GetPath())
                omni.log.info(f"{LOG_PREFIX} Setting up trigger: {trigger_path}")
                try:
                    # PhysxTriggerAPIを適用し、Enterイベントにスクリプトを設定
                    trigger_api = PhysxSchema.PhysxTriggerAPI.Apply(prim)
                    trigger_api.CreateEnterScriptTypeAttr().Set(PhysxSchema.Tokens.scriptFile)
                    trigger_api.CreateOnEnterScriptAttr().Set(script_path_to_run)

                    # Leaveイベントは今回は不要なため設定しない
                    # trigger_api.CreateLeaveScriptTypeAttr().Set(PhysxSchema.Tokens.scriptFile)
                    # trigger_api.CreateOnLeaveScriptAttr().Set(script_path_to_run)

                except Exception as e:
                    omni.log.error(f"{LOG_PREFIX} Failed to setup trigger '{trigger_path}'. Error: {e}")