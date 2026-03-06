# Item Placement System - 完全仕様書

## 📋 概要

### システムの目的
PhysX Triggerを使用して、フライス盤シミュレーションにおけるアイテムの自動配置・検証・状態管理を行う拡張機能。

### 主要機能
1. **トリガーベース検知**: PhysX Triggerによるアイテム侵入検知
2. **Number属性判定**: アイテムのNumber属性で正誤を判定
3. **自動配置**: 正解アイテムを指定座標に配置、不正解アイテムを原点にリセット
4. **プロキシ/実オブジェクトシステム**: RigidBodyを持たないオブジェクト用の代理配置機能
5. **タスクシステム**: 配置後にタスク完了を要求し、完了後にVR取り外しを許可
6. **状態管理**: アイテムの配置状態（IDLE/PLACED/DETACHABLE/DETACHED）を管理

---

## 🏗️ アーキテクチャ

### ファイル構成

```
item_placement_system/
├── config/
│   └── extension.toml              # 拡張機能設定
├── item_placement_system/
│   ├── __init__.py                 # モジュール初期化
│   ├── extension.py                # エントリーポイント（extension_triggerをインポート）
│   ├── extension_trigger.py        # メイン拡張機能クラス
│   ├── trigger_manager.py          # トリガー管理
│   ├── placement_state_manager.py  # 配置状態管理
│   ├── task_manager.py             # タスクシステム管理
│   ├── trigger_placement_script.py # PhysX物理スクリプト（廃止）
│   └── task_scripts/
│       ├── base_task.py            # タスク基底クラス
│       ├── voxel_mesh_task.py      # Voxel Mesh用タスク
│       ├── plug_task.py            # Plug用タスク
│       └── __init__.py
├── docs/
│   ├── TRIGGER_SYSTEM_GUIDE.md     # 使い方ガイド
│   └── IMPLEMENTATION_GUIDE.md     # 実装ガイド
└── README_TRIGGER.md               # クイックスタート
```

### クラス構成図

```
ItemPlacementTriggerExtension (メイン拡張機能)
├─ TriggerManager (トリガー管理)
│  └─ TriggerSlot[] (各トリガーの設定)
│     └─ ProxyMapping (プロキシマッピング、オプション)
├─ TaskManager (タスク管理)
│  └─ BaseTask[] (タスクインスタンス)
│     ├─ VoxelMeshTask
│     ├─ PlugTask
│     └─ NoTask
└─ PlacementStateManager (状態管理)
   └─ ObjectPlacementState[] (各オブジェクトの状態)
```

---

## 🔧 主要コンポーネント

### 1. ItemPlacementTriggerExtension
**ファイル**: `extension_trigger.py`

**役割**: 拡張機能のメインコントローラー

**主要メソッド**:
```python
def on_startup(self, ext_id)
    # TriggerManager、TaskManager、PlacementStateManagerを初期化
    # タイムラインイベント購読
    # UI構築

def _on_timeline_event(self, event)
    # CURRENT_TIME_TICKED: _update_trigger_detection()を呼び出し
    # PLAY: 処理済みアイテムリストをクリア
    # STOP: _cleanup_on_simulation_stop()を呼び出し

def _update_trigger_detection(self)
    # 各トリガースロットをループ
    # PhysxTriggerStateAPI.Get() → GetTriggeredCollisionsRel().GetTargets()
    # 各colliderのNumber属性を取得
    # correct_numbersと比較して正誤判定
    # 正解: _handle_correct_item_*()
    # 不正解: _handle_incorrect_item()

def _cleanup_on_simulation_stop(self)
    # 全real_objectを非表示＆コリジョン無効化
    # プロキシ配置アイテムをクリーンアップ
    # 標準配置アイテムのRigidBody再有効化
```

**タイムラインイベント処理フロー**:
```
PLAY
  └─> _processed_items.clear()

CURRENT_TIME_TICKED (毎フレーム)
  └─> _update_trigger_detection()
       ├─ TriggerStateAPI.GetTriggeredCollisionsRel()
       ├─ collider_paths から Number 属性取得
       ├─ correct_numbers と比較
       ├─ 正解 → _handle_correct_item_*()
       │   ├─ proxy_mapping 有り → _handle_correct_item_with_proxy()
       │   └─ proxy_mapping 無し → _handle_correct_item_no_proxy()
       └─ 不正解 → _handle_incorrect_item()

STOP
  └─> _cleanup_on_simulation_stop()
       ├─ 全 real_object を非表示＆コリジョン無効化
       ├─ custom:proxy_placed=True のアイテムをクリーンアップ
       └─ custom:placed=True のアイテムを RigidBody 再有効化
```

---

### 2. TriggerManager
**ファイル**: `trigger_manager.py`

**役割**: トリガースロットの設定と PhysX Trigger の初期化

**主要クラス**:

#### TriggerSlot
```python
class TriggerSlot:
    slot_id: str                           # スロットID
    trigger_path: str                      # トリガーPrimパス
    correct_numbers: List[int]             # 正解Number値リスト
    placement_translate: Tuple[float]      # 配置先座標
    placement_rotate: Tuple[float]         # 配置時の回転（度）
    placement_path: Optional[str]          # 配置先の親パス
    proxy_mapping: Optional[ProxyMapping]  # プロキシマッピング
    proxy_reset_position: Tuple[float]     # プロキシ隠し位置（デフォルト: (0,100,0)）
    proxy_original_position: Tuple[float]  # プロキシ元の位置（デフォルト: (0,0,0)）
    task_type: str                         # タスクタイプ ('voxel_mesh', 'plug', 'none')
    scenario_id: int                       # シナリオID
    display_name: str                      # UI表示名
```

#### ProxyMapping
```python
class ProxyMapping:
    proxy_path: str        # RigidBody有りのダミーオブジェクトパス
    real_path: str         # 実際に表示するオブジェクトパス
    initial_hidden: bool   # 初期状態で非表示にするか
```

**主要メソッド**:
```python
def initialize(self)
    # 各 TriggerSlot に対して _setup_trigger() を実行

def _setup_trigger(self, slot: TriggerSlot)
    # CollisionAPI.Apply(trigger_prim)
    # PhysxTriggerAPI.Apply(trigger_prim)
    # PhysxTriggerStateAPI.Apply(trigger_prim)
    # _set_trigger_attributes() でカスタム属性設定

def get_trigger_status(self) -> Dict
    # 各トリガーの状態を取得
    # trigger_state_api.GetTriggeredCollisionsRel().GetTargets()
```

**デフォルトスロット設定例**:
```python
DEFAULT_SLOTS = [
    TriggerSlot(
        slot_id="trigger_slot_1",
        trigger_path="/World/New_MillingMachine/Table/Set_Base/Trigger_Table",
        correct_numbers=[1],
        placement_translate=(10.0, 5.0, 0.0),
        task_type='none',
        display_name="スロット1 (Number=1)"
    ),
]
```

---

### 3. PlacementStateManager
**ファイル**: `placement_state_manager.py`

**役割**: プロキシ/実オブジェクトの状態管理（表示/非表示切り替え）

**状態定義**:
```python
class PlacementState(Enum):
    IDLE = "idle"              # 待機中（プロキシ表示）
    PLACED = "placed"          # 設置済み（実オブジェクト表示）
    DETACHABLE = "detachable"  # 取り外し可能（タスク完了後）
    DETACHED = "detached"      # 取り外し済み（プロキシに戻る）
```

**主要メソッド**:
```python
def register_object(slot_id, proxy_path, real_path)
    # オブジェクトを登録

def on_placement(slot_id, stage, proxy_path, real_path, proxy_reset_position)
    # ステップ1: プロキシを proxy_reset_position に移動（遠くに隠す）
    # ステップ2: 実オブジェクトを表示、コリジョン有効化
    # ステップ3: 状態を PLACED に更新
    # ステップ4: タスク開始（task.on_task_start()）

def on_detachment(slot_id, stage, real_path, proxy_path, proxy_original_position)
    # ステップ1: 実オブジェクトを非表示、コリジョン無効化
    # ステップ2: プロキシを proxy_original_position に戻す
    # ステップ3: プロキシを再表示
    # ステップ4: 状態を IDLE にリセット
    # ステップ5: タスクリセット

def check_detachment_allowed(slot_id, stage) -> bool
    # タスク完了状態をチェック
    # task_manager.check_task_completion()
```

**状態遷移図**:
```
IDLE (プロキシ表示)
  ↓ アイテムがトリガーに侵入（正解）
  ↓ on_placement()
PLACED (実オブジェクト表示、タスク開始)
  ↓ タスク完了
DETACHABLE (取り外し可能)
  ↓ VR Grip で取り外し
  ↓ on_detachment()
DETACHED (プロキシに戻る)
  ↓
IDLE (再び待機)
```

---

### 4. TaskManager
**ファイル**: `task_manager.py`

**役割**: タスクスクリプトのインスタンス管理

**主要メソッド**:
```python
def _register_task_classes(self)
    # 利用可能なタスククラスを登録
    # 'voxel_mesh' → VoxelMeshTask
    # 'plug' → PlugTask
    # 'none' → NoTask

def create_task(slot_id, task_type, real_object_path) -> BaseTask
    # タスクインスタンスを生成
    # _tasks[slot_id] に保存

def check_task_completion(slot_id, stage) -> bool
    # タスク完了状態をチェック
    # task.check_completion(stage)

def reset_task(slot_id)
    # タスクをリセット
```

---

### 5. BaseTask (タスクスクリプト基底クラス)
**ファイル**: `task_scripts/base_task.py`

**抽象メソッド**:
```python
@abstractmethod
def check_completion(stage: Usd.Stage) -> bool
    # タスク完了条件をチェック（サブクラスで実装）
```

**共通メソッド**:
```python
def on_task_start(stage)
    # タスク開始時の処理

def on_task_complete(stage)
    # タスク完了時の処理

def reset()
    # タスクをリセット
```

**具体的なタスク実装例**:

#### VoxelMeshTask
```python
class VoxelMeshTask(BaseTask):
    target_rotation = -100.0  # 目標回転角度（度）
    handle_path = "/World/New_MillingMachine/Main/Handle_Dril"
    joint_path = f"{handle_path}/RevoluteJoint"

    def check_completion(stage) -> bool:
        # RevoluteJointのDriveAPI.GetTargetPositionAttr()を取得
        # current_position <= target_rotation であれば完了
        # 完了時に custom:task 属性を True に設定
```

#### PlugTask
```python
class PlugTask(BaseTask):
    target_position = (115.0, 5.0, 78.5)  # 目標位置（ワールド座標）
    threshold = 10.0  # 10cm以内であれば完了

    def check_completion(stage) -> bool:
        # real_object の world 座標を取得
        # 目標位置との距離を計算
        # 距離 <= threshold であれば完了
```

#### NoTask
```python
class NoTask(BaseTask):
    def check_completion(stage) -> bool:
        # 常に True（即座に取り外し可能）
```

---

## 🔄 処理フロー

### アイテム配置フロー（プロキシ無し）

```
1. アイテムがトリガーに侵入
   ↓
2. _update_trigger_detection()
   ├─ TriggerStateAPI.GetTriggeredCollisionsRel()
   ├─ collider_path から Number 属性取得
   └─ correct_numbers と比較
   ↓
3. 正解の場合: _handle_correct_item_no_proxy()
   ├─ 現在位置を custom:original_position に保存
   ├─ slot_id を custom:slot_id に保存
   ├─ placement_translate に移動
   ├─ RigidBody.velocity / angularVelocity をゼロに
   ├─ physics:rigidBodyEnabled = False（静的コライダー化）
   ├─ custom:placed = True を設定
   └─ custom:task = タスクありなら False、なしなら True
   ↓
4. 不正解の場合: _handle_incorrect_item()
   ├─ (0, 0, 0) に移動
   ├─ velocity / angularVelocity をゼロに
   └─ physics:rigidBodyEnabled = False
```

### アイテム配置フロー（プロキシ有り）

```
1. プロキシがトリガーに侵入
   ↓
2. _update_trigger_detection()
   ├─ 同様に Number 属性判定
   └─ proxy_mapping 有り
   ↓
3. 正解の場合: _handle_correct_item_with_proxy()
   ├─ プロキシの現在位置を proxy_original_pos として保存
   ├─ プロキシの RigidBody 無効化
   ├─ プロキシを proxy_reset_position (0, 100, 0) に移動
   ├─ 実オブジェクトを表示（visibility = inherited）
   ├─ 実オブジェクトのコリジョン有効化（collisionEnabled = True）
   ├─ 実オブジェクトに USD 属性設定:
   │  ├─ custom:task = タスクありなら False、なしなら True
   │  ├─ custom:proxy_placed = True
   │  ├─ custom:proxy_path = プロキシパス
   │  ├─ custom:original_position = プロキシ元の位置
   │  ├─ custom:slot_id = スロット ID
   │  └─ custom:placed = True
   └─ プロキシに USD 属性設定:
      ├─ custom:proxy_placed = True
      └─ custom:real_object_path = 実オブジェクトパス
```

### タスク完了チェックフロー

```
VR UI 拡張機能から毎フレーム:
  ↓
PlacementStateManager.check_detachment_allowed(slot_id, stage)
  ↓
TaskManager.check_task_completion(slot_id, stage)
  ↓
BaseTask.check_completion(stage)
  ├─ VoxelMeshTask: handle_drill 回転角度チェック
  ├─ PlugTask: プラグ位置チェック
  └─ NoTask: 常に True
  ↓
タスク完了時:
  ├─ custom:task = True を設定
  └─ VR UI で取り外し可能に
```

### シミュレーション停止時のクリーンアップ

```
STOP イベント
  ↓
_cleanup_on_simulation_stop()
  ↓
1. _cleanup_all_real_objects()
   ├─ trigger_manager から全 real_object パスを取得
   ├─ visibility = invisible
   └─ collisionEnabled = False
  ↓
2. _cleanup_proxy_placed_items()
   ├─ Stage.Traverse() で custom:proxy_placed=True を探す
   ├─ custom:real_object_path から実オブジェクトを取得
   ├─ visibility = invisible
   ├─ collisionEnabled = False
   └─ custom:proxy_placed = False
  ↓
3. _cleanup_standard_placed_items()
   ├─ Stage.Traverse() で custom:placed=True を探す
   ├─ physxRigidBody:disableSimulation = False
   ├─ kinematicEnabled = False
   ├─ 回転を (0, 0, 0) にリセット
   └─ custom:placed = False
```

---

## 📚 重要なライブラリとメソッド

### USD (Universal Scene Description)

#### インポート
```python
from pxr import Usd, UsdGeom, UsdPhysics, PhysxSchema, Sdf, Gf
import omni.usd
```

#### Stage 取得
```python
stage = omni.usd.get_context().get_stage()
```

#### Prim 操作
```python
# Prim 取得
prim = stage.GetPrimAtPath("/World/Object")

# 有効性チェック
if prim.IsValid():
    pass

# 属性取得
attr = prim.GetAttribute("Number")
value = attr.Get()

# 属性作成
from pxr import Sdf
new_attr = prim.CreateAttribute("custom:placed", Sdf.ValueTypeNames.Bool, False)
new_attr.Set(True)

# 親 Prim 取得
parent = prim.GetParent()

# 子 Prim を探索
for child in prim.GetChildren():
    pass

# Stage 全体を探索
for prim in stage.Traverse():
    pass
```

#### Transform 操作
```python
from pxr import UsdGeom, Gf

# Xformable として取得
xformable = UsdGeom.Xformable(prim)

# ワールド座標取得
world_transform = xformable.ComputeLocalToWorldTransform(0)
world_position = world_transform.ExtractTranslation()

# XformOp 取得（ローカル座標）
ordered_ops = xformable.GetOrderedXformOps()
for op in ordered_ops:
    if op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
        local_position = op.Get()
        op.Set(Gf.Vec3f(10.0, 5.0, 0.0))
        break

# XformOp 追加
translate_op = xformable.AddTranslateOp()
translate_op.Set(Gf.Vec3f(10.0, 5.0, 0.0))
```

#### Visibility 操作
```python
from pxr import UsdGeom

imageable = UsdGeom.Imageable(prim)

# 取得
visibility_attr = imageable.GetVisibilityAttr()

# 作成（存在しない場合）
if not visibility_attr:
    visibility_attr = imageable.CreateVisibilityAttr()

# 設定
visibility_attr.Set(UsdGeom.Tokens.invisible)  # 非表示
visibility_attr.Set(UsdGeom.Tokens.inherited)  # 表示
```

### PhysX

#### CollisionAPI
```python
from pxr import UsdPhysics

# CollisionAPI 適用
UsdPhysics.CollisionAPI.Apply(prim)

# CollisionAPI 取得
collision_api = UsdPhysics.CollisionAPI.Get(stage, prim_path)

# collisionEnabled 設定
collision_enabled_attr = collision_api.GetCollisionEnabledAttr()
if not collision_enabled_attr:
    collision_enabled_attr = collision_api.CreateCollisionEnabledAttr()
collision_enabled_attr.Set(True)
```

#### RigidBodyAPI
```python
from pxr import UsdPhysics, Gf

# RigidBodyAPI 取得
rb_api = UsdPhysics.RigidBodyAPI.Get(stage, prim_path)

# velocity 設定
velocity_attr = rb_api.GetVelocityAttr()
if velocity_attr:
    velocity_attr.Set(Gf.Vec3f(0, 0, 0))

# angularVelocity 設定
angular_velocity_attr = rb_api.GetAngularVelocityAttr()
if angular_velocity_attr:
    angular_velocity_attr.Set(Gf.Vec3f(0, 0, 0))

# RigidBody 無効化（静的コライダー化）
rb_enabled_attr = prim.GetAttribute("physics:rigidBodyEnabled")
if not rb_enabled_attr:
    rb_enabled_attr = prim.CreateAttribute("physics:rigidBodyEnabled", Sdf.ValueTypeNames.Bool, False)
rb_enabled_attr.Set(False)
```

#### PhysxTriggerAPI / PhysxTriggerStateAPI
```python
from pxr import PhysxSchema

# PhysxTriggerAPI 適用
trigger_api = PhysxSchema.PhysxTriggerAPI.Apply(trigger_prim)

# PhysxTriggerStateAPI 適用
trigger_state_api = PhysxSchema.PhysxTriggerStateAPI.Apply(trigger_prim)

# トリガー内のコライダー取得（毎フレーム）
trigger_state_api = PhysxSchema.PhysxTriggerStateAPI.Get(stage, trigger_path)
if trigger_state_api:
    colliders_rel = trigger_state_api.GetTriggeredCollisionsRel()
    if colliders_rel:
        collider_paths = colliders_rel.GetTargets()
        for collider_path in collider_paths:
            print(f"Collider in trigger: {collider_path}")
```

#### DriveAPI（RevoluteJoint/PrismaticJoint）
```python
from pxr import UsdPhysics

# RevoluteJoint の DriveAPI 取得
joint_prim = stage.GetPrimAtPath("/World/Handle/RevoluteJoint")
drive_api = UsdPhysics.DriveAPI.Get(joint_prim, "angular")

if drive_api:
    # targetPosition 取得
    target_position = drive_api.GetTargetPositionAttr().Get()
    print(f"Current angle: {target_position}°")
```

### Omniverse Kit

#### Timeline イベント
```python
import omni.timeline

timeline = omni.timeline.get_timeline_interface()
self._timeline_subscription = timeline.get_timeline_event_stream().create_subscription_to_pop(
    self._on_timeline_event
)

def _on_timeline_event(self, event):
    if event.type == int(omni.timeline.TimelineEventType.CURRENT_TIME_TICKED):
        # 毎フレーム
        pass
    elif event.type == int(omni.timeline.TimelineEventType.PLAY):
        # シミュレーション開始
        pass
    elif event.type == int(omni.timeline.TimelineEventType.STOP):
        # シミュレーション停止
        pass
```

#### UI (omni.ui)
```python
import omni.ui as ui

self._ui_window = ui.Window("Item Placement System", width=450, height=600)
with self._ui_window.frame:
    with ui.VStack(spacing=10):
        ui.Label("Title", height=30, style={"font_size": 18})
        ui.Separator()
        ui.Button("Click Me", clicked_fn=self._on_button_click)
```

---

## 🐛 既知の問題と注意点

### 1. PhysxTriggerStateAPI メソッド名
**問題**: ドキュメントとAPIが一致しない

**正しいメソッド名**:
```python
# ❌ 誤り
trigger_state_api.GetTriggeredBodiesRel()
trigger_state_api.GetTriggeredCollidersRel()

# ✅ 正しい
trigger_state_api.GetTriggeredCollisionsRel()
```

### 2. USD 変更のタイミング
**問題**: PhysX スクリプトコールバック内で USD 変更すると mutex エラーでクラッシュ

**解決策**: タイムラインの `CURRENT_TIME_TICKED` イベント内で USD 変更を行う

```python
# ❌ 誤り: PhysX コールバック内
def handle_enter_event(stage_id, prim_path):
    stage = UsdUtils.StageCache.Get().Find(stage_id)
    prim.CreateAttribute(...)  # クラッシュ！

# ✅ 正しい: Timeline イベント内
def _on_timeline_event(self, event):
    if event.type == int(omni.timeline.TimelineEventType.CURRENT_TIME_TICKED):
        self._update_trigger_detection()  # ここで USD 変更
```

### 3. RigidBody 無効化方法
**問題**: `disableSimulation` 属性は存在しない（Unreal Engine の属性）

**正しい方法**:
```python
# ❌ 誤り
prim.GetAttribute("physxRigidBody:disableSimulation").Set(True)

# ✅ 正しい
# 方法1: physics:rigidBodyEnabled = False（静的コライダー化）
rb_enabled_attr = prim.CreateAttribute("physics:rigidBodyEnabled", Sdf.ValueTypeNames.Bool, False)
rb_enabled_attr.Set(False)

# 方法2: kinematicEnabled = True（キネマティック化）
rb_api = UsdPhysics.RigidBodyAPI.Get(stage, prim_path)
kinematic_attr = rb_api.GetKinematicEnabledAttr()
if not kinematic_attr:
    kinematic_attr = rb_api.CreateKinematicEnabledAttr()
kinematic_attr.Set(True)
```

### 4. 座標系の混同
**問題**: ワールド座標とローカル座標の混同

**注意点**:
```python
# ワールド座標取得（読み取り専用、親の変換を含む）
world_transform = xformable.ComputeLocalToWorldTransform(0)
world_position = world_transform.ExtractTranslation()

# ローカル座標取得/設定（親に対して相対的）
for op in xformable.GetOrderedXformOps():
    if op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
        local_position = op.Get()  # ローカル読み取り
        op.Set(new_position)       # ローカル書き込み
        break
```

---

## 📝 カスタマイズガイド

### 新しいトリガースロットを追加

**trigger_manager.py の DEFAULT_SLOTS に追加**:
```python
TriggerSlot(
    slot_id="trigger_slot_5",
    trigger_path="/World/MyTrigger/Trigger5",
    correct_numbers=[5, 6],  # Number=5 または 6 を正解とする
    placement_translate=(50.0, 10.0, 5.0),
    placement_rotate=(0, 45.0, 0),  # Y軸を45度回転
    task_type='none',
    display_name="カスタムスロット (Number=5,6)"
),
```

### 新しいタスクを作成

**1. task_scripts/my_task.py を作成**:
```python
from .base_task import BaseTask
from pxr import Usd
import carb

class MyTask(BaseTask):
    def __init__(self, slot_id: str, real_object_path: str):
        super().__init__(slot_id, real_object_path)
        self.completion_threshold = 100  # カスタムパラメータ

    def check_completion(self, stage: Usd.Stage) -> bool:
        # タスク完了条件を実装
        # 例: 特定の属性値をチェック
        try:
            prim = stage.GetPrimAtPath(self.real_object_path)
            value_attr = prim.GetAttribute("custom:progress")
            if value_attr:
                progress = value_attr.Get()
                return progress >= self.completion_threshold
        except:
            return False
        return False
```

**2. task_manager.py に登録**:
```python
def _register_task_classes(self):
    from .task_scripts.my_task import MyTask
    self._task_classes['my_task'] = MyTask
```

**3. TriggerSlot で使用**:
```python
TriggerSlot(
    slot_id="custom_slot",
    trigger_path="/World/MyTrigger",
    correct_numbers=[10],
    placement_translate=(100.0, 0.0, 0.0),
    task_type='my_task',  # ← 新しいタスクを指定
    display_name="Custom Task Slot"
)
```

---

## 🔌 外部拡張機能との連携

### VR UI 拡張機能との連携

**VR UI 側のコード**:
```python
from item_placement_system.extension import get_extension_instance

# 拡張機能インスタンス取得
item_placement_ext = get_extension_instance()
if item_placement_ext:
    # PlacementStateManager 取得
    state_mgr = item_placement_ext.get_placement_state_manager()

    # VR Grip ボタンで取り外し可能かチェック
    can_detach = state_mgr.check_detachment_allowed("voxel_mesh_slot", stage)

    if can_detach:
        # 取り外し実行
        state_mgr.on_detachment(
            slot_id="voxel_mesh_slot",
            stage=stage,
            real_path="/World/Table/VoxelMesh",
            proxy_path="/World/Items/VoxelMesh_Proxy",
            proxy_original_position=(0, 0, 0)
        )
```

---

## 📖 参考資料

### Omniverse ドキュメント
- [Triggers — Omniverse Developer Guide](https://docs.omniverse.nvidia.com/dev-guide/latest/programmer_ref/physics/triggers.html)
- [PhysxSchemaPhysxTriggerStateAPI Class Reference](https://docs.omniverse.nvidia.com/kit/docs/omni_usd_schema_physics/106.1/class_physx_schema_physx_trigger_state_a_p_i.html)

### USD ドキュメント
- [USD API Documentation](https://openusd.org/release/api/index.html)
- [UsdGeom](https://openusd.org/release/api/usd_geom_page_front.html)
- [UsdPhysics](https://openusd.org/release/api/usd_physics_page_front.html)

---

## 📞 まとめ

この仕様書は、Item Placement System 拡張機能を一から再構築するために必要な全ての情報を含んでいます。

**主要な設計原則**:
1. **PhysX Trigger ベース検知**: スクリプトコールバックではなく、TriggerStateAPI.GetTriggeredCollisionsRel() をポーリング
2. **タイムラインイベントで USD 変更**: PhysX スレッドではなく、メインスレッドで USD 変更
3. **プロキシ/実オブジェクト分離**: RigidBody を持たないオブジェクト用の代理配置システム
4. **タスクシステム**: 配置後にタスク完了を要求し、VR 取り外しを制御
5. **USD 属性による状態永続化**: 実行コンテキスト間で状態を共有

この仕様に従えば、クラッシュを回避しながら堅牢な拡張機能を再実装できます。
