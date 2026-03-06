# check_item_script.py
import sys
import carb
from pxr import Usd, UsdUtils, Sdf

LOG_PREFIX = "[my_extension][trigger_script]"

def handle_enter_event(stage, trigger_path, other_path):
    """
    アイテムがトリガーに入ったときに、正誤判定を行う関数
    """
    try:
        trigger_prim = stage.GetPrimAtPath(trigger_path)
        if not trigger_prim: return

        # トリガーに設定された「正解アイテムのパス」を取得
        correct_item_attr = trigger_prim.GetAttribute("custom:correct_item")
        if not correct_item_attr.IsValid():
            # "custom:correct_item" がなければ、"correct_item" を試す
            correct_item_attr = trigger_prim.GetAttribute("correct_item")

        if not correct_item_attr.IsValid():
            carb.log_warn(f"{LOG_PREFIX} Trigger '{trigger_path}' has no 'correct_item' attribute.")
            return

        correct_item_path = correct_item_attr.Get()

        # 入ってきたアイテムのパスと比較
        if str(other_path) == correct_item_path:
            carb.log_info(f"{LOG_PREFIX} Correct item '{other_path}' entered trigger '{trigger_path}'. get correct_item.")
        else:
            # 間違ったアイテムが入った場合もログを出す（デバッグ用）
            carb.log_warn(f"{LOG_PREFIX} Wrong item entered trigger '{trigger_path}'. Expected '{correct_item_path}', but got '{other_path}'.")

    except Exception as e:
        carb.log_error(f"{LOG_PREFIX} Error in handle_enter_event: {e}")

def main():
    """
    物理エンジンから呼び出されるメイン関数
    """
    try:
        # コマンドライン引数から必要な情報を取得
        stage_id = int(sys.argv[1])
        trigger_path_str = sys.argv[2]
        other_path_str = sys.argv[3]
        event_name = sys.argv[4]
    except (ValueError, IndexError):
        # 引数が足りない場合は何もしない
        return

    # イベントが "EnterEvent" の場合のみ処理を実行
    if event_name == "EnterEvent":
        cache = UsdUtils.StageCache.Get()
        stage = cache.Find(Usd.StageCache.Id.FromLongInt(stage_id))
        if not stage: return

        trigger_path = Sdf.Path(trigger_path_str)
        other_path = Sdf.Path(other_path_str)

        handle_enter_event(stage, trigger_path, other_path)

# スクリプトが直接実行されたらmain関数を呼び出す
if __name__ == "__main__":
    main()