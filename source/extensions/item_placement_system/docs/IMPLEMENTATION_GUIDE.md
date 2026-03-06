# Item Placement System - 実装ガイド

## 📋 目次
1. [システムアーキテクチャ](#システムアーキテクチャ)
2. [実装の詳細](#実装の詳細)
3. [データフロー](#データフロー)
4. [拡張方法](#拡張方法)
5. [ベストプラクティス](#ベストプラクティス)

---

## 🏗️ システムアーキテクチャ

### コンポーネント図

```
┌─────────────────────────────────────────────────────────────┐
│                  ItemPlacementExtension                      │
│  - UI管理                                                     │
│  - タイムラインイベント処理                                   │
│  - ユーザーインタラクション                                   │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│                    TriggerManager                            │
│  - トリガースロット管理                                       │
│  - PhysxTriggerAPI設定                                       │
│  - カスタム属性設定                                           │
│  - 状態監視                                                   │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   │ セットアップ時
                   ▼
┌─────────────────────────────────────────────────────────────┐
│                USD Stage (トリガーPrim)                       │
│  Prim: /World/Triggers/TriggerSlot1                         │
│  - PhysxTriggerAPI                                           │
│  - CollisionAPI                                              │
│  - OnEnterScript: trigger_placement_script.py               │
│  - Custom Attributes:                                        │
│    - custom:correct_numbers: [1]                            │
│    - custom:placement_translate: (10, 5, 0)                 │
│    - custom:scenario_id: 0                                  │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   │ トリガーイベント発生時
                   ▼
┌─────────────────────────────────────────────────────────────┐
│            trigger_placement_script.py                       │
│  - PhysXエンジンから呼び出される                              │
│  - アイテムのNumber属性を取得                                 │
│  - トリガー設定と照合                                         │
│  - 正解 → place_item_correct()                              │
│  - 不正解 → reset_item_incorrect()                          │
└─────────────────────────────────────────────────────────────┘
```

### クラス構成

#### TriggerSlot
```python
class TriggerSlot:
    """個別のトリガースロット設定"""
    - slot_id: str              # 一意識別子
    - trigger_path: str         # USDパス
    - correct_numbers: List[int] # 正解Number値
    - placement_translate: Tuple # 配置先座標
    - placement_path: Optional[str] # 配置先親パス
    - scenario_id: int          # シナリオID
    - display_name: str         # 表示名
```

#### TriggerManager
```python
class TriggerManager:
    """トリガーシステムの管理"""
    - _slots: List[TriggerSlot]
    - _trigger_state_apis: Dict[str, PhysxTriggerStateAPI]
    - _script_path: str
    - _enabled: bool

    + initialize()
    + get_trigger_status() -> Dict
    + enable_trigger_detection(enabled: bool)
    + diagnose_trigger_system()
    + add_slot(slot: TriggerSlot)
    + remove_slot(slot_id: str) -> bool
```

---

## 💻 実装の詳細

### 1. トリガーのセットアップフロー

```python
# trigger_manager.py

def _setup_trigger(self, stage: Usd.Stage, slot: TriggerSlot) -> bool:
    """
    ステップ1: Primの取得と検証
    """
    trigger_prim = stage.GetPrimAtPath(slot.trigger_path)
    if not trigger_prim.IsValid():
        return False

    """
    ステップ2: CollisionAPIの適用
    """
    if not trigger_prim.HasAPI(UsdPhysics.CollisionAPI):
        UsdPhysics.CollisionAPI.Apply(trigger_prim)

    """
    ステップ3: PhysxTriggerAPIの適用とスクリプト設定
    """
    trigger_api = PhysxSchema.PhysxTriggerAPI.Apply(trigger_prim)
    trigger_api.CreateEnterScriptTypeAttr().Set(PhysxSchema.Tokens.scriptFile)
    trigger_api.CreateOnEnterScriptAttr().Set(self._script_path)

    """
    ステップ4: TriggerStateAPIの適用（状態監視用）
    """
    trigger_state_api = PhysxSchema.PhysxTriggerStateAPI.Apply(trigger_prim)
    self._trigger_state_apis[slot.slot_id] = trigger_state_api

    """
    ステップ5: カスタム属性の設定
    """
    self._set_trigger_attributes(trigger_prim, slot)

    return True
```

### 2. カスタム属性の設定

```python
def _set_trigger_attributes(self, trigger_prim: Usd.Prim, slot: TriggerSlot):
    """
    トリガースクリプトが参照する属性を設定
    """

    # 正解Number値リスト（IntArray型）
    correct_numbers_attr = trigger_prim.CreateAttribute(
        "custom:correct_numbers",
        Sdf.ValueTypeNames.IntArray,  # [1, 2, 3] のような配列
        False
    )
    correct_numbers_attr.Set(slot.correct_numbers)

    # 配置先座標（Float3型）
    placement_translate_attr = trigger_prim.CreateAttribute(
        "custom:placement_translate",
        Sdf.ValueTypeNames.Float3,  # (x, y, z)
        False
    )
    placement_translate_attr.Set(Gf.Vec3f(*slot.placement_translate))

    # 配置先パス（String型、オプション）
    if slot.placement_path:
        placement_path_attr = trigger_prim.CreateAttribute(
            "custom:placement_path",
            Sdf.ValueTypeNames.String,
            False
        )
        placement_path_attr.Set(slot.placement_path)

    # シナリオID（Int型）
    scenario_id_attr = trigger_prim.CreateAttribute(
        "custom:scenario_id",
        Sdf.ValueTypeNames.Int,
        False
    )
    scenario_id_attr.Set(slot.scenario_id)
```

### 3. トリガースクリプトの実行フロー

```python
# trigger_placement_script.py

def main():
    """
    PhysXエンジンから以下の引数で呼び出される:
    sys.argv[1]: stage_id (int)
    sys.argv[2]: trigger_path (string)
    sys.argv[3]: item_path (string)
    sys.argv[4]: event_name (string) - "EnterEvent" or "LeaveEvent"
    """

    # ステップ1: 引数の解析
    stage_id = int(sys.argv[1])
    trigger_path_str = sys.argv[2]
    item_path_str = sys.argv[3]
    event_name = sys.argv[4]

    # ステップ2: Stageの取得
    cache = UsdUtils.StageCache.Get()
    stage = cache.Find(Usd.StageCache.Id.FromLongInt(stage_id))

    # ステップ3: イベント処理
    if event_name == "EnterEvent":
        handle_enter_event(stage, trigger_path, item_path)
```

### 4. 正誤判定ロジック

```python
def handle_enter_event(stage, trigger_path, item_path):
    """
    ステップ1: アイテムのNumber属性を取得
    """
    item_number = get_item_number(stage, item_path)
    if item_number == -1:
        return  # Number属性なし

    """
    ステップ2: トリガー設定を取得
    """
    trigger_config = get_trigger_config(stage, trigger_path)
    correct_numbers = trigger_config.get("correct_numbers", [])

    """
    ステップ3: 正誤判定
    """
    if item_number in correct_numbers:
        # 正解処理
        place_item_correct(stage, item_path, trigger_config)
    else:
        # 不正解処理
        reset_item_incorrect(stage, item_path)
```

### 5. 正解時の処理

```python
def place_item_correct(stage, item_path, trigger_config):
    """
    ステップ1: アイテムの位置を設定
    """
    item_prim = stage.GetPrimAtPath(item_path)
    item_xform = UsdGeom.Xformable(item_prim)
    translate_op = item_xform.GetTranslateOp()

    if not translate_op:
        translate_op = item_xform.AddTranslateOp()
        item_xform.SetXformOpOrder([translate_op])

    target_translate = trigger_config.get("placement_translate")
    translate_op.Set(target_translate)

    """
    ステップ2: RigidBodyを無効化
    """
    rb_api = UsdPhysics.RigidBodyAPI.Get(stage, item_path)
    if rb_api:
        # シミュレーションを無効化
        disable_sim_attr = item_prim.CreateAttribute(
            "physxRigidBody:disableSimulation",
            Sdf.ValueTypeNames.Bool,
            False
        )
        disable_sim_attr.Set(True)

        # 速度をゼロに
        rb_api.GetVelocityAttr().Set(Gf.Vec3f(0, 0, 0))
        rb_api.GetAngularVelocityAttr().Set(Gf.Vec3f(0, 0, 0))

    """
    ステップ3: 配置完了フラグを設定
    """
    item_prim.CreateAttribute(
        "custom:placed",
        Sdf.ValueTypeNames.Bool,
        False
    ).Set(True)
```

---

## 📊 データフロー

### トリガーイベント発生時のデータフロー

```
1. アイテムがトリガーに侵入
   ↓
2. PhysXエンジンがEnterEventを検知
   ↓
3. trigger_placement_script.pyを呼び出し
   引数: (stage_id, trigger_path, item_path, "EnterEvent")
   ↓
4. スクリプト内でアイテムのNumber属性を取得
   item_prim.GetAttribute("Number").Get()
   ↓
5. トリガーのcustom属性から設定を取得
   - custom:correct_numbers
   - custom:placement_translate
   - custom:placement_path
   ↓
6. 正誤判定
   item_number in correct_numbers?
   ↓
7a. 正解の場合:              7b. 不正解の場合:
    - placement_translateに配置    - translate=(0,0,0)にリセット
    - RigidBody無効化               - 速度リセット
    - custom:placed=True設定        - コンソール警告出力
    ↓                               ↓
8. コンソールにログ出力
   ✅ CORRECT または ❌ INCORRECT
```

### 状態監視のデータフロー

```
1. タイムラインイベント発生（毎フレーム）
   ↓
2. Extension._on_timeline_event()
   ↓
3. 30フレームごとにUI更新
   ↓
4. TriggerManager.get_trigger_status()
   ↓
5. 各トリガーのTriggerStateAPIから情報取得
   trigger_state_api.GetTriggeredCollisionsRel().GetTargets()
   ↓
6. UI表示を更新
   - 検知数
   - コライダーパス
   - スロット情報
```

---

## 🔧 拡張方法

### カスタム判定ロジックの追加

#### 例: 複数条件の正誤判定

`trigger_placement_script.py`に追加:

```python
def check_advanced_condition(stage, item_path, trigger_config) -> bool:
    """
    高度な正誤判定（Number以外の条件も含む）
    """
    item_prim = stage.GetPrimAtPath(item_path)

    # Number属性チェック
    item_number = get_item_number(stage, item_path)
    if item_number not in trigger_config["correct_numbers"]:
        return False

    # カスタム属性チェック（例: Color属性）
    color_attr = item_prim.GetAttribute("custom:Color")
    if color_attr.IsValid():
        required_color = trigger_config.get("required_color")
        if required_color and color_attr.Get() != required_color:
            return False

    # 位置チェック（例: 特定範囲内）
    item_xform = UsdGeom.Xformable(item_prim)
    world_tf = item_xform.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
    world_pos = world_tf.ExtractTranslation()

    valid_region = trigger_config.get("valid_region")
    if valid_region:
        if not is_in_region(world_pos, valid_region):
            return False

    return True


def handle_enter_event(stage, trigger_path, item_path):
    """修正版"""
    trigger_config = get_trigger_config(stage, trigger_path)

    # 高度な判定を使用
    if check_advanced_condition(stage, item_path, trigger_config):
        place_item_correct(stage, item_path, trigger_config)
    else:
        reset_item_incorrect(stage, item_path)
```

### シナリオ連携の実装

#### ScenarioControllerインターフェース

```python
# scenario_controller.py (別途実装)

class ScenarioController:
    """シナリオ進行管理"""

    def __init__(self):
        self._current_scenario = 0
        self._scenario_configs = {}

    def get_slot_config(self, slot_id: str, scenario_id: int) -> Dict:
        """
        シナリオIDに応じたスロット設定を返す
        """
        config = self._scenario_configs.get((slot_id, scenario_id), {})
        return {
            "correct_numbers": config.get("numbers", []),
            "placement_translate": config.get("translate", (0, 0, 0)),
            "placement_path": config.get("path"),
        }

    def advance_scenario(self):
        """シナリオを次に進める"""
        self._current_scenario += 1
        self._update_all_triggers()

    def _update_all_triggers(self):
        """すべてのトリガーを現在のシナリオに更新"""
        tm = get_trigger_manager()
        for slot in tm._slots:
            config = self.get_slot_config(slot.slot_id, self._current_scenario)
            tm.update_slot_from_scenario(slot.slot_id, config)
```

#### TriggerManagerの拡張

```python
def update_slot_from_scenario(self, slot_id: str, scenario_data: Dict):
    """
    シナリオデータでスロットを更新
    """
    stage = self._usd_context.get_stage()
    if not stage:
        return

    # スロットを探す
    slot = next((s for s in self._slots if s.slot_id == slot_id), None)
    if not slot:
        return

    # 設定を更新
    slot.correct_numbers = scenario_data.get("correct_numbers", slot.correct_numbers)
    slot.placement_translate = scenario_data.get("placement_translate", slot.placement_translate)
    slot.placement_path = scenario_data.get("placement_path", slot.placement_path)

    # トリガーPrimの属性を更新
    trigger_prim = stage.GetPrimAtPath(slot.trigger_path)
    if trigger_prim.IsValid():
        self._set_trigger_attributes(trigger_prim, slot)

    carb.log_info(f"{LOG_PREFIX} Slot updated from scenario: {slot_id}")
```

### UI拡張

#### カスタムステータス表示の追加

```python
# extension_trigger.py

def _update_custom_status_display(self):
    """カスタムステータス表示"""
    with self._custom_status_container:
        # 配置完了アイテムのリスト
        placed_items = self._get_placed_items()

        ui.Label(f"配置完了: {len(placed_items)} 個", height=20)

        for item_path in placed_items:
            with ui.HStack(height=18):
                ui.Spacer(width=12)
                ui.Label(f"✓ {item_path}",
                        style={"color": 0xFF00AA00, "font_size": 11})

def _get_placed_items(self) -> List[str]:
    """custom:placed=True のアイテムを取得"""
    stage = omni.usd.get_context().get_stage()
    if not stage:
        return []

    placed = []
    for prim in stage.Traverse():
        placed_attr = prim.GetAttribute("custom:placed")
        if placed_attr.IsValid() and placed_attr.Get():
            placed.append(str(prim.GetPath()))

    return placed
```

---

## ✅ ベストプラクティス

### 1. エラーハンドリング

```python
def safe_trigger_setup(stage, slot):
    """安全なトリガーセットアップ"""
    try:
        trigger_prim = stage.GetPrimAtPath(slot.trigger_path)
        if not trigger_prim.IsValid():
            carb.log_warn(f"Trigger prim not found: {slot.trigger_path}")
            return False

        # 処理...
        return True

    except Exception as e:
        carb.log_error(f"Setup error for {slot.trigger_path}: {e}")
        import traceback
        traceback.print_exc()
        return False
```

### 2. パフォーマンス最適化

```python
# UI更新頻度の制御
self._ui_update_interval = 30  # 30フレームごと

# 大量のトリガーがある場合
if len(self._slots) > 20:
    self._ui_update_interval = 60  # 更新頻度を下げる
```

### 3. デバッグ支援

```python
# デバッグモードの活用
DEBUG_MODE = True

def debug_log(message: str):
    """条件付きログ出力"""
    if DEBUG_MODE:
        carb.log_info(f"{LOG_PREFIX} [DEBUG] {message}")

# 詳細なログ出力
debug_log(f"Item Number: {item_number}, Expected: {correct_numbers}")
debug_log(f"JUDGMENT: {'CORRECT' if is_correct else 'INCORRECT'}")
```

### 4. テスト駆動開発

```python
# tests/test_trigger_system.py

import omni.kit.test
from item_placement_system.trigger_manager import TriggerSlot

class TestTriggerSystem(omni.kit.test.AsyncTestCase):
    async def test_slot_creation(self):
        """スロット作成のテスト"""
        slot = TriggerSlot(
            slot_id="test_slot",
            trigger_path="/World/Test/Trigger",
            correct_numbers=[1, 2],
            placement_translate=(5.0, 0.0, 0.0)
        )

        self.assertEqual(slot.slot_id, "test_slot")
        self.assertEqual(slot.correct_numbers, [1, 2])

    async def test_trigger_setup(self):
        """トリガーセットアップのテスト"""
        # USD Stageを作成
        # トリガーをセットアップ
        # 検証
        pass
```

---

## 🎓 まとめ

このシステムは以下の設計思想に基づいています:

✅ **モジュール性**: 各コンポーネントが独立して動作
✅ **拡張性**: シナリオシステムなど将来の機能追加が容易
✅ **デバッグ性**: 詳細なログと診断機能
✅ **パフォーマンス**: 必要最小限のUI更新
✅ **保守性**: 明確な責任分離と命名規則

拡張や改修の際は、このアーキテクチャを維持することを推奨します。
