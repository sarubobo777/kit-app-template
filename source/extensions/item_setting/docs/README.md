# Item Setting Extension

PhysX Triggerを使用して、フライス盤シミュレーションにおけるアイテムの自動配置・検証・状態管理を行う拡張機能。

## 概要

### システムの目的
- PhysX Triggerによるアイテム侵入検知
- Number属性による正誤判定
- プロキシ/実オブジェクトシステム（RigidBodyを持たないオブジェクト用）
- タスクシステムとVR取り外し機能

### 主要機能
1. **トリガーベース検知**: PhysX TriggerでアイテムのTrigger侵入を自動検知
2. **Number属性判定**: アイテムの`custom:Number`属性で正解/不正解を判定
3. **プロキシシステム**: RigidBodyを持たないオブジェクト（Voxel Meshなど）用の代理配置
4. **タスク管理**: 配置後にタスク完了を要求、完了後にVR取り外しを許可

---

## オブジェクト構造

設置するオブジェクトは以下の階層構造を持つ必要があります：

```
/World/(省略)/Xform/設置するObject
例: /World/Items/ItemXform/Cube_01
```

- **Xform**: `Xform`タイプ - `RigidBodyAPI`を適用
- **Object**: `Mesh`タイプ - `CollisionAPI`とカスタム属性を適用

---

## カスタム属性リスト

### オブジェクト（Mesh）に適用する属性

設置するオブジェクト（Mesh）に以下のカスタム属性を適用：

| 属性名 | 型 | 説明 | 必須/任意 |
|--------|-----|------|----------|
| `custom:Number` | `Int` | アイテムの識別番号（トリガーの`correct_number`と比較） | **必須** |
| `custom:placed` | `Bool` | 配置済みフラグ（True=配置済み、False=未配置） | **必須** |
| `custom:task` | `Bool` | タスク完了フラグ（True=タスク完了/取り外し可能） | **必須** |
| `custom:original_position` | `Float3` | 元の位置（X, Y, Z）- リセット時に使用 | **必須** |
| `custom:proxy` | `Bool` | プロキシシステム使用フラグ（True=プロキシ、False=通常） | **必須** |
| `custom:grab` | `Bool` | VR掴み可能フラグ（True=掴める、False=掴めない） | **必須** |
| `custom:slot_id` | `String` | 配置されたスロットID（トラッキング用） | 任意 |

### 親（Xform）に適用するコンポーネント

| コンポーネント | 説明 |
|---------------|------|
| `RigidBodyAPI` | 物理シミュレーション用（`UsdPhysics.RigidBodyAPI.Apply()`） |

### オブジェクト（Mesh）に適用するコンポーネント

| コンポーネント | 説明 |
|---------------|------|
| `CollisionAPI` | トリガー検知用（`UsdPhysics.CollisionAPI.Apply()`） |

---

## 属性設定例（Python）

```python
from pxr import Usd, UsdGeom, UsdPhysics, Sdf, Gf
import omni.usd

stage = omni.usd.get_context().get_stage()

# Xform（親）の取得
xform_prim = stage.GetPrimAtPath("/World/Items/ItemXform")

# RigidBodyを適用
rb_api = UsdPhysics.RigidBodyAPI.Apply(xform_prim)

# Object（子・Mesh）の取得
object_prim = stage.GetPrimAtPath("/World/Items/ItemXform/Cube_01")

# Colliderを適用
collision_api = UsdPhysics.CollisionAPI.Apply(object_prim)

# カスタム属性を作成・設定
object_prim.CreateAttribute("custom:Number", Sdf.ValueTypeNames.Int).Set(1)
object_prim.CreateAttribute("custom:placed", Sdf.ValueTypeNames.Bool).Set(False)
object_prim.CreateAttribute("custom:task", Sdf.ValueTypeNames.Bool).Set(False)
object_prim.CreateAttribute("custom:original_position", Sdf.ValueTypeNames.Float3).Set(Gf.Vec3f(0, 0, 0))
object_prim.CreateAttribute("custom:proxy", Sdf.ValueTypeNames.Bool).Set(False)
object_prim.CreateAttribute("custom:grab", Sdf.ValueTypeNames.Bool).Set(True)
object_prim.CreateAttribute("custom:slot_id", Sdf.ValueTypeNames.String).Set("")
```

---

## トリガースロット設定

`TriggerSlot`クラスでトリガーを設定：

```python
TriggerSlot(
    slot_id="slot_1",                           # スロットの一意識別子
    trigger_path="/World/Path/To/Trigger",      # トリガープリムのパス
    correct_number=1,                           # 正解となるNumber値
    placement_translate=(10.0, 5.0, 0.0),       # 配置位置（X, Y, Z）
    placement_rotate=(0.0, 0.0, 0.0),           # 配置時の回転角度（度）
    proxy=False,                                # プロキシシステム使用フラグ
    real_path="",                               # プロキシ使用時の実オブジェクトパス
    task=False,                                 # タスクシステム使用フラグ
    task_path="",                               # タスクスクリプトのパス
    display_name="スロット1 (Number=1)"         # UI表示用の名前
)
```

### 通常スロット（proxy=False）

```python
TriggerSlot(
    slot_id="drill_slot",
    trigger_path="/World/New_MillingMachine/Main/Doril/Trigger_Drill",
    correct_number=1,
    placement_translate=(0.0, 10.0, 0.0),
    placement_rotate=(0.0, 0.0, 0.0),
    proxy=False,
    display_name="ドリルスロット (Number=1)"
)
```

### プロキシスロット（proxy=True）

```python
TriggerSlot(
    slot_id="voxel_slot",
    trigger_path="/World/New_MillingMachine/Table/Set_Base/Trigger_Table",
    correct_number=2,
    placement_translate=(10.0, 5.0, 0.0),
    placement_rotate=(0.0, 0.0, 0.0),
    proxy=True,
    real_path="/World/New_MillingMachine/Table/VoxelMesh",
    task=True,
    display_name="テーブルスロット (Number=2, Proxy使用)"
)
```

---

## 動作フロー

### 設置フロー

1. **Trigger内にオブジェクトが侵入**
2. **`custom:Number`属性を確認** → `correct_number`と比較
3. **Number一致の場合**:
   - **proxy=False**: 親XformのRigidBody無効化 → 位置・回転設定 → `placed=True`, `task=設定値`
   - **proxy=True**: プロキシ非表示 → 実オブジェクト表示 → `placed=True`, `task=設定値`
4. **Number不一致の場合**: `custom:original_position`に戻す

### 取り外しフロー（VR）

1. **トリガーボタン押下** → raycastで物体検知
2. **`custom:grab`属性を確認**（なければスキップ）
3. **`grab=True`に設定**
4. **`custom:placed`属性を確認**:
   - **placed=False**: 通常の掴み処理
   - **placed=True**: 取り外し待機モードに入る
5. **右手ならBボタン、左手ならYボタンを押す**
6. **`item_setting.remove_item()`が実行される**:
   - **proxy=True**: プロキシ再表示、実オブジェクト非表示、元の位置に戻す
   - **proxy=False**: 元の位置に戻す、RigidBody再有効化、`placed=False`

---

## 属性の状態遷移

### 通常オブジェクト（proxy=False）

```
初期状態: placed=False, task=False, grab=True
　↓ トリガー侵入（Number一致）
配置状態: placed=True, task=(設定値), grab=True
　↓ タスク完了（task=True）
取り外し可能: placed=True, task=True, grab=True
　↓ VR取り外し（B/Yボタン）
リセット: placed=False, task=False, grab=True
```

### プロキシオブジェクト（proxy=True）

```
プロキシ: placed=False, proxy=True, grab=True
実オブジェクト: placed=False, task=False, visibility=invisible
　↓ トリガー侵入（Number一致）
プロキシ: visibility=invisible, collision=False
実オブジェクト: placed=True, task=(設定値), visibility=inherited
　↓ タスク完了
実オブジェクト: placed=True, task=True
　↓ VR取り外し（B/Yボタン）
プロキシ: visibility=inherited, collision=True
実オブジェクト: placed=False, task=False, visibility=invisible
```

---

## プロキシシステム詳細

### プロキシシステムが必要な理由

RigidBodyコンポーネントを持てないオブジェクト（例：Voxel Mesh）はトリガー検知ができないため、代理のプロキシオブジェクトを使用します。

### プロキシシステムの構成

- **プロキシオブジェクト**: RigidBody付きのダミーオブジェクト（トリガー検知用）
- **実オブジェクト**: 実際に使用する機能的なオブジェクト（初期状態で非表示）

### プロキシオブジェクトの属性設定

```python
# プロキシオブジェクト
proxy_prim.CreateAttribute("custom:Number", Sdf.ValueTypeNames.Int).Set(2)
proxy_prim.CreateAttribute("custom:proxy", Sdf.ValueTypeNames.Bool).Set(True)
proxy_prim.CreateAttribute("custom:placed", Sdf.ValueTypeNames.Bool).Set(False)
proxy_prim.CreateAttribute("custom:task", Sdf.ValueTypeNames.Bool).Set(False)
proxy_prim.CreateAttribute("custom:grab", Sdf.ValueTypeNames.Bool).Set(True)
proxy_prim.CreateAttribute("custom:original_position", Sdf.ValueTypeNames.Float3).Set(Gf.Vec3f(0, 0, 0))

# 実オブジェクト
real_prim.CreateAttribute("custom:placed", Sdf.ValueTypeNames.Bool).Set(False)
real_prim.CreateAttribute("custom:task", Sdf.ValueTypeNames.Bool).Set(False)

# 初期状態で実オブジェクトを非表示
UsdGeom.Imageable(real_prim).MakeInvisible()
```

---

## VR統合

### VR UIとの連携

`vr_ui`拡張機能と連携してVRコントローラーからの取り外しに対応：

```python
# vr_ui拡張機能内での使用例
import item_setting

ext_instance = item_setting.get_extension_instance()
if ext_instance:
    ext_instance.remove_item("/World/Items/ItemXform/Cube_01")
```

### VRボタンマッピング

- **右手コントローラー**: Bボタンで取り外し
- **左手コントローラー**: Yボタンで取り外し
- **前提条件**: `custom:placed=True` かつ `custom:task=True`

---

## APIリファレンス

### `ItemSettingExtension`

#### `remove_item(object_path: str)`

配置されたアイテムを取り外します（VR UIから呼ばれます）。

**引数**:
- `object_path` (str): 取り外すオブジェクトのパス

**動作**:
- `custom:proxy=True`: プロキシ再表示、実オブジェクト非表示
- `custom:proxy=False`: 元の位置に戻す、RigidBody再有効化

#### `handle_trigger_entry(object_path: str, trigger_path: str)`

トリガー侵入時の処理（内部使用）。

**引数**:
- `object_path` (str): 侵入したオブジェクトのパス
- `trigger_path` (str): トリガーのパス

---

## トラブルシューティング

### "ステージが取得できません" 警告

**原因**: ステージが開かれていない状態でトリガーを初期化しようとした

**解決策**: ステージを開いてから「トリガー再初期化」ボタンをクリック

### トリガーが反応しない

**確認項目**:
1. オブジェクトに`CollisionAPI`が適用されているか
2. 親Xformに`RigidBodyAPI`が適用されているか
3. `custom:Number`属性が設定されているか
4. トリガープリムに`PhysxTriggerAPI`と`PhysxTriggerStateAPI`が適用されているか

### VR取り外しができない

**確認項目**:
1. `custom:placed=True`になっているか
2. `custom:task=True`になっているか（タスク完了していない場合は取り外せない）
3. `custom:grab=True`になっているか

---

## 依存関係

- `omni.physx` - PhysX物理演算
- `omni.usd` - USD操作
- `omni.ui` - UIウィンドウ
- `omni.kit.commands` - Kitコマンド

---

## ライセンス

NVIDIA Proprietary License
