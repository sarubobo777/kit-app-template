# Item Placement System - Trigger版 使用ガイド

## 📋 目次
1. [概要](#概要)
2. [システム構成](#システム構成)
3. [セットアップ手順](#セットアップ手順)
4. [使い方](#使い方)
5. [カスタマイズ](#カスタマイズ)
6. [トラブルシューティング](#トラブルシューティング)

---

## 🎯 概要

**Item Placement System (Trigger版)** は、PhysX Triggerを使用してアイテムの自動配置と正誤判定を行うシステムです。

### 主な機能
✅ **自動判定**: トリガー領域にアイテムが入ると自動的に正誤を判定
✅ **Number属性ベース**: アイテムの`Number`属性で判定
✅ **自動配置**: 正解時は指定位置に配置、RigidBodyを無効化
✅ **リセット機能**: 不正解時は原点(0,0,0)に自動リセット
✅ **シナリオ対応**: 将来のシナリオコントローラー連携に対応
✅ **デバッグサポート**: 詳細なログ出力と診断機能

---

## 🏗️ システム構成

### ファイル構成

```
source/extensions/item_placement_system/
├── config/
│   └── extension.toml                    # 拡張機能設定
├── item_placement_system/
│   ├── __init__.py
│   ├── extension.py                      # メインエントリーポイント
│   ├── extension_trigger.py              # Trigger拡張機能本体
│   ├── trigger_manager.py                # Triggerマネージャー
│   ├── trigger_placement_script.py       # Triggerスクリプト
│   ├── extension_backup.py               # 旧システムバックアップ
│   └── tests/
└── docs/
    └── TRIGGER_SYSTEM_GUIDE.md           # このガイド
```

### コンポーネント

1. **TriggerManager** (`trigger_manager.py`)
   - トリガーの設定と管理
   - デフォルトスロット定義
   - PhysxTriggerAPIの適用

2. **TriggerScript** (`trigger_placement_script.py`)
   - PhysXから呼び出されるスクリプト
   - 正誤判定ロジック
   - 配置/リセット処理

3. **Extension** (`extension_trigger.py`)
   - UI提供
   - タイムラインイベント処理
   - システム制御

---

## 🛠️ セットアップ手順

### ステップ1: USDシーンにトリガーを配置

1. **トリガーPrimを作成**
   ```
   /World/Triggers/TriggerSlot1
   /World/Triggers/TriggerSlot2
   /World/Triggers/TriggerSlot3
   /World/Triggers/TriggerSlot4
   ```

2. **各トリガーにColliderを追加**
   - Cube, Sphere, Capsuleなどの形状を選択
   - 右クリック → **Add → Physics → Collider**

3. **サイズと位置を調整**
   - トリガーを配置したい場所に移動
   - スケールを調整（推奨: 1.0〜2.0 unit程度）

### ステップ2: アイテムにNumber属性を設定

アイテムオブジェクトに`Number`属性を追加:

```python
from pxr import Sdf

item_prim = stage.GetPrimAtPath("/World/Items/Item1")
number_attr = item_prim.CreateAttribute("Number", Sdf.ValueTypeNames.Int)
number_attr.Set(1)  # このアイテムのNumber値
```

またはProperty Panelから:
1. アイテムを選択
2. **Add → Custom Attribute**
3. Name: `Number`, Type: `Int`, Value: `1`

### ステップ3: 拡張機能を有効化

1. **Extension Manager**を開く（Window → Extensions）
2. `Item Placement System`を検索
3. **Enable**をクリック

### ステップ4: デフォルト設定を確認

`trigger_manager.py`の`DEFAULT_SLOTS`を確認:

```python
DEFAULT_SLOTS = [
    TriggerSlot(
        slot_id="trigger_slot_1",
        trigger_path="/World/Triggers/TriggerSlot1",  # ← あなたのパスに合わせる
        correct_numbers=[1],                           # ← 正解Number
        placement_translate=(10.0, 5.0, 0.0),         # ← 配置先座標
        display_name="スロット1 (Number=1)"
    ),
    # ... 他のスロット
]
```

**必要に応じて編集してください。**

### ステップ5: トリガーをセットアップ

UIウィンドウの「トリガー再セットアップ」ボタンをクリック、または拡張機能を再起動すると自動的にトリガーが設定されます。

---

## 📖 使い方

### 基本的な流れ

1. **シミュレーション開始前の準備**
   - トリガーが正しく配置されているか確認
   - 「トリガー診断」ボタンで状態をチェック

2. **シミュレーション開始**
   - Playボタンを押してシミュレーション開始
   - アイテムをトリガー領域に移動

3. **自動判定**
   - アイテムがトリガーに侵入すると自動的に判定
   - **正解**: 指定位置に配置、RigidBody無効化
   - **不正解**: 原点(0,0,0)にリセット

4. **コンソール確認**
   - 判定結果がコンソールに表示されます
   ```
   [ItemPlacement][TriggerScript] ✅ CORRECT! Item placed: /World/Items/Item1 -> (10, 5, 0)
   [ItemPlacement][TriggerScript] ❌ INCORRECT! Item reset to origin: /World/Items/Item2
   ```

### UIウィンドウの機能

#### トリガーシステム状態
- **トリガー検知**: 有効/無効の表示
- **監視スロット数**: 現在設定されているスロット数
- **各スロット情報**:
  - 📍 スロット名
  - 検知数: 現在トリガー内にあるオブジェクト数
  - Path: トリガーのUSDパス
  - 正解Number: 期待されるNumber値

#### 制御ボタン

| ボタン | 機能 |
|--------|------|
| **状態更新** | トリガー状態を手動で更新 |
| **トリガー診断** | 詳細な診断情報をコンソールに出力 |
| **トリガー有効化** | トリガー検知を有効化 |
| **トリガー無効化** | トリガー検知を無効化 |
| **トリガー再セットアップ** | すべてのトリガーを再設定 |

---

## 🎨 カスタマイズ

### 新しいトリガースロットを追加

#### 方法1: DEFAULT_SLOTSに追加（推奨）

`trigger_manager.py`を編集:

```python
DEFAULT_SLOTS = [
    # 既存のスロット...
    TriggerSlot(
        slot_id="trigger_slot_5",                    # 一意のID
        trigger_path="/World/Triggers/TriggerSlot5", # USDパス
        correct_numbers=[5, 6],                      # 複数の正解値も可能
        placement_translate=(50.0, 5.0, 0.0),       # 配置先
        display_name="スロット5 (Number=5,6)"       # 表示名
    ),
]
```

#### 方法2: 実行時に動的追加

```python
from item_placement_system.extension import get_extension_instance

ext = get_extension_instance()
ext.add_trigger_slot(
    slot_id="dynamic_slot_1",
    trigger_path="/World/Triggers/DynamicSlot",
    correct_numbers=[10],
    placement_translate=(100.0, 10.0, 5.0),
    display_name="動的スロット"
)
```

### 配置先のカスタマイズ

#### ローカル座標での配置（デフォルト）

```python
placement_translate=(10.0, 5.0, 0.0)  # 親Primからの相対座標
```

#### 特定の親Primを指定

```python
TriggerSlot(
    slot_id="slot_with_parent",
    trigger_path="/World/Triggers/Slot",
    correct_numbers=[1],
    placement_translate=(5.0, 0.0, 0.0),
    placement_path="/World/Containers/Container1",  # 配置先の親
    display_name="コンテナ1スロット"
)
```

### 正解条件のカスタマイズ

#### 複数の正解値を設定

```python
correct_numbers=[1, 2, 3]  # Number=1, 2, 3 のいずれかが正解
```

#### シナリオIDで管理（将来の拡張用）

```python
TriggerSlot(
    slot_id="scenario_slot",
    trigger_path="/World/Triggers/ScenarioSlot",
    correct_numbers=[1],
    placement_translate=(10.0, 5.0, 0.0),
    scenario_id=1,  # シナリオコントローラーから参照される
    display_name="シナリオ1用スロット"
)
```

### デバッグモードの切り替え

`trigger_placement_script.py`の先頭:

```python
# デバッグフラグ
DEBUG_MODE = True  # False にすると詳細ログを無効化
```

---

## 🔧 トラブルシューティング

### 問題: トリガーが反応しない

#### 確認事項
1. **CollisionAPIが適用されているか**
   - トリガーPrimを選択
   - Property Panelで`CollisionAPI`を確認

2. **PhysxTriggerAPIが適用されているか**
   - 「トリガー診断」ボタンをクリック
   - コンソール出力を確認

3. **スクリプトパスが正しいか**
   ```
   [ItemPlacement][TriggerManager] Using trigger script: C:\...\trigger_placement_script.py
   [ItemPlacement][TriggerManager] Script Exists: True
   ```

4. **アイテムにNumber属性があるか**
   - アイテムPrimを選択
   - Property Panelで`Number`属性を確認

#### 解決方法
- UIで「トリガー再セットアップ」をクリック
- 拡張機能を無効化→有効化

### 問題: 不正解時にリセットされない

#### 原因
- アイテムの親Primがない
- 親Primの階層が複雑

#### 解決方法
`trigger_placement_script.py`の`reset_item_incorrect()`を確認:
```python
# 親Primからの相対座標でリセット
translate_op.Set(Gf.Vec3f(0, 0, 0))
```

必要に応じてワールド座標を使う実装に変更可能。

### 問題: 正解だが配置位置がずれる

#### 原因
- 親Primのtransformが考慮されていない
- placement_translateがワールド座標だと思っている

#### 解決方法
`placement_translate`は**ローカル座標**です。親Primを基準とした相対座標で指定してください。

### 問題: コンソールにログが出ない

#### 確認事項
1. **DEBUG_MODEが有効か**
   ```python
   DEBUG_MODE = True
   ```

2. **Consoleウィンドウが開いているか**
   - Window → Console

3. **ログレベルが適切か**
   - Edit → Preferences → Log Level → Info以上

---

## 📊 デバッグ情報の読み方

### トリガー診断出力例

```
[ItemPlacement][TriggerManager] === Trigger System Diagnosis ===
[ItemPlacement][TriggerManager] Enabled: True
[ItemPlacement][TriggerManager] Script Path: C:\...\trigger_placement_script.py
[ItemPlacement][TriggerManager] Script Exists: True
[ItemPlacement][TriggerManager] Configured Slots: 4

[ItemPlacement][TriggerManager] --- Slot 1: スロット1 (Number=1) ---
[ItemPlacement][TriggerManager]   ID: trigger_slot_1
[ItemPlacement][TriggerManager]   Trigger Path: /World/Triggers/TriggerSlot1
[ItemPlacement][TriggerManager]   Expected Numbers: [1]
[ItemPlacement][TriggerManager]   Placement: (10.0, 5.0, 0.0)
[ItemPlacement][TriggerManager]   Prim Status: Valid ✅
[ItemPlacement][TriggerManager]   CollisionAPI: True
[ItemPlacement][TriggerManager]   PhysxTriggerAPI: True
[ItemPlacement][TriggerManager]   Enter Script: C:\...\trigger_placement_script.py
[ItemPlacement][TriggerManager]   Custom Attr 'correct_numbers': [1]
```

### スクリプト実行ログ例

```
[ItemPlacement][TriggerScript] [DEBUG] ============================================================
[ItemPlacement][TriggerScript] [DEBUG] ENTER EVENT: /World/Items/Item1 -> /World/Triggers/TriggerSlot1
[ItemPlacement][TriggerScript] [DEBUG] ============================================================
[ItemPlacement][TriggerScript] [DEBUG] Item /World/Items/Item1 has Number: 1
[ItemPlacement][TriggerScript] [DEBUG] Trigger config loaded: {'correct_numbers': [1], ...}
[ItemPlacement][TriggerScript] [DEBUG] Item Number: 1, Expected: [1]
[ItemPlacement][TriggerScript] [DEBUG] JUDGMENT: CORRECT ✅
[ItemPlacement][TriggerScript] [DEBUG] Placing item to: None, translate: (10, 5, 0)
[ItemPlacement][TriggerScript] [DEBUG] RigidBody disabled for /World/Items/Item1
[ItemPlacement][TriggerScript] ✅ CORRECT! Item placed: /World/Items/Item1 -> (10, 5, 0)
```

---

## 🚀 高度な使い方

### シナリオコントローラーとの連携（将来実装）

```python
# シナリオコントローラーからスロット設定を更新
scenario_data = {
    "correct_numbers": [5, 6],
    "placement_translate": (20.0, 10.0, 5.0)
}

trigger_manager = get_trigger_manager()
trigger_manager.update_slot_from_scenario("trigger_slot_1", scenario_data)
```

### Pythonから直接制御

```python
import omni.usd
from item_placement_system.trigger_manager import get_trigger_manager

# TriggerManagerを取得
tm = get_trigger_manager()

# トリガー状態を取得
status = tm.get_trigger_status()
print(f"Active triggers: {status['slot_count']}")

# トリガー検知を無効化
tm.enable_trigger_detection(False)

# 診断を実行
tm.diagnose_trigger_system()
```

---

## 📝 まとめ

このシステムを使用することで:
✅ アイテムの自動配置システムを簡単に構築
✅ PhysX Triggerによる物理ベースの検知
✅ Number属性による柔軟な正誤判定
✅ シナリオベースの学習アプリケーションに対応

ご質問やバグ報告は、プロジェクトのIssueトラッカーまでお願いします。
