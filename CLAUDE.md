# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

このファイルは、Claude Code (claude.ai/code) がこのリポジトリのコードを扱う際のガイダンスを提供します。

## リポジトリ概要

これは物理シミュレーションと産業機械制御に焦点を当てたNVIDIA Omniverse Kit SDKアプリケーションテンプレートリポジトリです。このプロジェクトは、RevoluteJointとPhysX物理演算を通じて制御されるインタラクティブなハンドルを持つ包括的なフライス盤シミュレーションを実装しています。システムは、高度な角度追跡、協調制御、堅牢な物理制約管理を特徴としています。

## 開発コマンド

### ビルドと実行
- **アプリケーションのビルド**: `./repo.sh build` (Linux) または `.\repo.bat build` (Windows)
- **アプリケーションの起動**: `./repo.sh launch` (Linux) または `.\repo.bat launch` (Windows) - プロンプトが表示されたら"my_milling_machine.project"を選択
- **テストの実行**: `./repo.sh test` (Linux) または `.\repo.bat test` (Windows)
- **アプリケーションのパッケージ化**: `./repo.sh package` (Linux) または `.\repo.bat package` (Windows)
- **UTF-8環境 (Windows)**: 日本語テキストの適切なUTF-8エンコーディングのために`.\repo_utf8.bat`ラッパーを使用

### テスト
- **すべてのテストを実行**: `./repo.sh test` (Linux) または `.\repo.bat test` (Windows)
- **フレームワーク**: async/awaitサポート付きの`omni.kit.test`を使用
- **構造**: 各拡張機能は`{extension_name}/tests/`ディレクトリにテストを持つ
- **基底クラス**: テストは`omni.kit.test.AsyncTestCaseFailOnLogError`を継承

## コアアーキテクチャ

### Kit アプリケーション構造
- **アプリケーションエントリーポイント**: `source/apps/my_milling_machine.project.kit` - millingMachineアプリケーションを定義するメインkitファイル
- **カスタム拡張機能**: `source/extensions/`ディレクトリに配置
- **ビルド設定**: `premake5.lua`がビルドするアプリを定義、現在は"my_milling_machine.project.kit"をビルド

### 物理拡張機能 (handle_angle)
物理ベースのハンドル制御を実装するメインカスタム拡張機能：

- **拡張機能の場所**: `source/extensions/handle_angle/handle_angle/extension.py`
- **コアクラス**: `EnhancedHandleController` - 個別ハンドルの物理演算と制御を管理
- **メイン拡張機能**: `EnhancedHandleDriveExtension` - 複数のハンドルと物理シミュレーションを調整

#### 物理実装戦略
この拡張機能は、Articulationの競合を避けるために、JointStateAPIの代わりに**Transform監視アプローチ**を使用：
- ハンドルオブジェクトのTransform行列の変化を監視
- ジンバルロック回避を使用してクォータニオンの差から回転角度を計算
- 回転方向追跡による安定化された角度デルタ計算を実装
- 物理制約（剛性、減衰、摩擦）にPhysX DriveAPIを使用
- 複数ハンドルの自動軸補正と協調制御を特徴とする

#### ハンドルコントローラーアーキテクチャ
各ハンドルは以下を持つ：
- Jointパス（RevoluteJoint）
- ハンドルオブジェクトパス（回転する視覚オブジェクト）
- ターゲットオブジェクトパス（移動するオブジェクト）
- 物理パラメータ（剛性、減衰、最大力、摩擦）
- **設定可能な回転角度**: `rotation_angle_per_movement`パラメータ（デフォルト360°）は、何度のハンドル回転で1つの移動単位をトリガーするかを制御
- 移動制約と累積回転追跡
- 同じオブジェクトをターゲットとする複数ハンドルの協調制御サポート
- 自動位置リセット機能
- 強化された診断機能

### 拡張機能開発パターン
拡張機能は以下の構造に従う：
```
source/extensions/{extension_name}/
├── config/extension.toml          # 拡張機能の設定と依存関係
├── {extension_name}/
│   ├── extension.py              # メイン拡張機能エントリーポイント（omni.ext.IExtを実装）
│   └── tests/                    # 拡張機能のテスト
└── docs/                         # 拡張機能のドキュメント
```

## 主要な設定ファイル

- **repo.toml**: リポジトリ設定、ビルド設定、パッケージングルール
- **source/apps/my_milling_machine.project.kit**: アプリケーションの依存関係と設定
- **source/extensions/handle_angle/config/extension.toml**: 拡張機能のメタデータと依存関係

## 物理実装ノート

### 重要な物理パラメータ
RevoluteJoint物理演算を扱う際：
- **Stiffness（剛性）**: 回転への抵抗を制御（1e6 - 1e7範囲）
- **Damping（減衰）**: 運動減衰を制御（1e4 - 1e5範囲）
- **Max Force（最大力）**: 適用される力を制限（5000-10000範囲）
- **Friction Torque（摩擦トルク）**: 回転抵抗を追加（15-50範囲）

### Transform監視システム
この拡張機能がTransform行列監視を使用する理由：
- JointStateAPIがArticulationシステムと競合する
- Articulation内のKinematic bodyが物理エラーを引き起こす
- TransformアプローチはArticulation制約なしで安定した角度追跡を提供

### 角度計算の安定性
システムは複数の安定化措置を実装：
- 誤った方向変化を防ぐための回転方向追跡
- 境界ジャンプ補正を伴う角度デルタ平滑化
- 異常検出のためのサンプル履歴分析
- 精密な移動制御のための累積回転追跡
- 軸投影法を使用したジンバルロック回避
- 自動軸設定補正（大文字小文字を区別しない）
- ±180°遷移の境界処理
- 自動累積リセット付きの制限検出

## 拡張機能の依存関係

millingMachineアプリケーションには以下のカスタム拡張機能が含まれる：
- `handle_angle`: メインの物理ベースハンドル制御システム
- `handle_controller`: シーン作成とオブジェクト制御の調整
- `physical_button`: ランタイム中のシミュレーション制御用の物理ボタンシステム
- `voxel_carver`: ワールド座標追跡を使用したボクセルベースのアプローチによる材料除去シミュレーション
- `observer_system`: 中央状態監視とオブジェクト管理システム
- `item_setting`: PhysX Triggerベースの自動アイテム配置・検証システム（Update Loop方式）
- `vr_ui`: VRコントローラー入力監視、3D UI表示、およびVR物理インタラクション
- `trigger_observation`: オブジェクト状態監視と観察
- `my.object.follower`: オブジェクト追従動作システム
- `my_reset_extension`: シーンとオブジェクトのリセット機能
- UI、物理演算、レンダリング用の各種Omniverse SDK拡張機能

## 開発環境

- **ターゲットプラットフォーム**: Windows 10/11、Linux Ubuntu 22.04+
- **GPU要件**: NVIDIA RTX対応GPU（RTX 3070+推奨）
- **依存関係**: Git、Git LFS、Visual Studio（Windows C++）、build-essentials（Linux）
- **物理エンジン**: USD統合を持つNVIDIA PhysX
- **シーンフォーマット**: PhysXスキーマ拡張を持つOpenUSD

## テンプレートシステム

リポジトリには迅速な開発のための包括的なテンプレート機能が含まれる：

### 拡張機能テンプレート
- **Basic Python**: 最小限のPython拡張機能テンプレート
- **Python UI**: omni.uiを使用したUIベースのPython拡張機能
- **Basic C++**: 最小限のC++拡張機能テンプレート
- **Python Binding**: Pybind11を介したPythonバインディングを持つC++拡張機能
- **Setup Extensions**: アプリケーション固有のセットアップと設定拡張機能

テンプレート作成は`templates/templates.toml`設定からの変数置換を使用します。

## 高度な機能

### 協調制御システム
洗練されたマルチハンドル協調を実装：
- **ターゲットグルーピング**: 同じオブジェクトを制御するハンドルを自動的にグループ化
- **累積移動追跡**: 複数のハンドル間の競合を防止
- **絶対位置決め**: 精密な制御のために累積移動値を使用
- **競合解決**: 同じ軸をターゲットとする複数のハンドルを処理

### 強化された角度追跡
高度な角度計算方法：
- **ジンバルロック回避**: オイラー角の代わりに軸投影を使用
- **クォータニオンから軸角変換**: 堅牢な回転解析
- **境界ジャンプ補償**: ±180°の折り返しを正しく処理
- **方向安定性**: 正/負の角度間の振動を防止

### 診断と自動補正
- **軸不一致検出**: Jointと設定された軸の自動補正
- **詳細なTransformログ**: 包括的な状態監視
- **制限境界処理**: オブジェクトが移動制限に達したときの自動リセット
- **パフォーマンス監視**: 計算の安定性とパフォーマンスを追跡

### 位置リセットシステム
- **初期状態保存**: 起動時にオブジェクトの位置を保存
- **シミュレーション終了リセット**: オブジェクトを初期位置に自動的に戻す
- **拡張機能シャットダウンリセット**: 拡張機能無効化時のクリーンアップ
- **協調リセット**: 複数のリンクされたオブジェクトを正しく処理

## 一般的な開発パターン

### 物理システム開発
物理システムを拡張する際：
1. 追加ハンドル用の新しい`EnhancedHandleController`インスタンスを作成
2. 望ましい動作に基づいて物理パラメータを設定（パラメータ有効性分析を参照）
3. ジンバルロック回避を伴う角度追跡にTransform監視を使用
4. 無効なUSDパスに対する適切なエラー処理を実装
5. 物理動作のデバッグのための診断出力を追加
6. 同じオブジェクトをターゲットとするハンドルの協調制御を検討
7. 軸設定の互換性を確認するために異なるUSDファイルでテスト

### 拡張機能間通信パターン
拡張機能間の調整のために：
1. グローバルレジストリにアクセスするために`ExtensionRegistry.get_instance()`を使用
2. `on_startup()`で`register_extension(name, self)`を使用して拡張機能を登録
3. `on_shutdown()`で`unregister_extension(name)`を使用して登録解除
4. `call_extension_method(ext_name, method_name, *args)`を使用してリモートメソッドを呼び出し
5. グローバルインスタンス変数を使用してフォールバックメカニズムを提供
6. オプションの依存関係に対してtry-catchブロックを使用した安全なインポート処理を実装

### 座標系の扱い
USDトランスフォームとPhysXを扱う際：
1. 常にY-up座標系の規約を使用（Omniverseのデフォルト）
2. **ワールド座標 vs ローカル座標**:
   - ワールド座標の読み取りには`ComputeLocalToWorldTransform()`を使用（完全な親階層を含む）
   - ローカル座標の読み取り/書き込みには`XformOp.Get()/Set()`を使用（親に対して相対的）
   - **重要**: ワールド座標とローカル座標操作を混在させない（例：`ComputeLocalToWorldTransform()`で読み取り、`TranslateOp.Set()`で書き込みをしない）
3. **ローカル座標の取得**: `GetOrderedXformOps()`を反復してTranslateOpを見つける：
   ```python
   ordered_ops = xformable.GetOrderedXformOps()
   for op in ordered_ops:
       if op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
           local_position = op.Get()  # ローカル読み取り
           op.Set(new_position)       # ローカル書き込み
           break
   ```
4. 適切なXformOpを使用して回転を適用（例：X軸回転の場合は`AddRotateXOp()`）
5. PrismaticJointとRevoluteJointの軸を座標変換に合わせて設定
6. 正しい軸方向でボタンのインタラクションと物理制約をテスト

### 物理パラメータ調整ガイドライン
異なるハンドル設定は異なるパラメータ値を必要とする場合がある：
- **質量と慣性**: 重いオブジェクトはより高い剛性値を必要とする
- **Articulation vs RigidBody**: Articulationシステムは力を異なる方法で減衰させる可能性がある
- **Transform階層**: ネストされたトランスフォームは制約の有効性に影響を与える可能性がある
- **PhysXソルバー設定**: グローバル物理設定は個々の制約に影響を与える

システムは、独立した物理パラメータ、協調移動制御、包括的な診断機能を持つ複数のハンドルを同時に処理するように設計されています。

## 物理ボタンシステム (physical_button)

### アーキテクチャと実装
物理ボタン拡張機能はPhysX駆動のボタンを通じてインタラクティブなシミュレーション制御を提供：

- **拡張機能の場所**: `source/extensions/physical_button/physical_button/extension.py`
- **コアクラス**: `PhysicalButton` - 個別ボタンの物理演算とインタラクションを管理
- **メイン拡張機能**: `PhysicalButtonExtension` - ボタンシステムと拡張機能間通信を調整

### ボタン物理設定
システムは既存のフライス盤スイッチオブジェクト（Switch1/Switch2）をインタラクティブボタンとして使用：
- **Switch2（開始ボタン）**: ワールド座標(-2.0, 0.09, 0.3)に配置
- **Switch1（停止ボタン）**: ワールド座標(-2.0, -0.24, 0.0)に配置
- **検出方法**: Z軸の絶対変位監視（0.5ユニット閾値）
- **物理統合**: スイッチオブジェクト上の既存のRigidBodyとColliderコンポーネントを使用

### ボタン検出システム
- **押下検出**: `TranslateOp.Get()`を介してローカル座標を使用してX軸変位を監視
- **アクティベーション閾値**: 初期位置から0.07ユニットのX軸変位
- **状態管理**: 視覚的フィードバックを伴う押下/解放状態を追跡
- **物理統合**: X軸移動を持つPrismaticJoint（0から1.0の範囲）
- **ドライブ設定**: スプリングバック動作のための剛性5000.0、減衰500.0
- **リアルタイム監視**: 即座の応答のためのフレームごとの位置チェック

### Inter-Extension Communication
Uses `ExtensionRegistry` pattern for coordinated control:
- **Registration System**: Extensions register themselves with weak references
- **Method Invocation**: Remote method calls across extensions with error handling
- **Primary Target**: voxel_carver extension start/stop simulation control
- **Fallback Mechanisms**: Direct module access when registry calls fail

### Visual Feedback System

#### Material-Based Visual Feedback
The system provides visual feedback by modifying shader parameters of button materials:

**Approach**: Direct shader parameter modification (not material swapping)
- Modifies `emissiveColor`, `diffuseColor`, and `roughness` of existing material's shader
- Preserves original material bindings and settings
- RTX renderer automatically detects parameter changes and re-renders

**Button Visual States**:
- **START (Green)**: emissive `(0, 100, 0)`, diffuse `(0, 1, 0)`, roughness `0.1`
- **STOP (Red)**: emissive `(50, 0, 0)`, diffuse `(1, 0, 0)`, roughness `0.1`

**Why this works better than material swapping**:
- Real-time parameter change detection by RTX renderer
- Preserves existing material properties (textures, etc.)
- Simpler state management (save/restore parameter values)

#### Shared Material Handling
**Critical Issue**: Buttons may share materials with other objects

**Solution**: Create button-specific material copies on initialization
```python
# Creates independent material copy for each button
button_material_path = f"/World/Materials/{self.button_type}_ButtonMaterial"
# Deep copy: Material → Shader → All Inputs (emissive, diffuse, roughness, etc.)
```

**Fallback**: If no material exists, create default UsdPreviewSurface material

**Implementation Details**:
- `_create_button_material_copy()`: Deep copies existing material structure
- `_create_default_material()`: Creates fallback material if none exists
- Manual deep copy (not `CopyPrim`) for better reliability
- All shader inputs copied with correct types and values

### Integration Notes
- **Coordinate System**: Uses local coordinates via `TranslateOp.Get()/Set()` for accurate position tracking
- **Material Independence**: Each button gets its own material copy to avoid affecting other objects
- **Physics Setup**: Creates invisible kinematic base and PrismaticJoint for spring-back behavior
- **Extension Communication**: Uses global instance pattern to trigger voxel_carver start/stop

## Build System Details

### Repository Configuration (`repo.toml`)
- **Build System**: Premake5-based with Kit-friendly tooling
- **Packaging**: Supports both "fat" (self-contained) and "thin" (registry-dependent) package variants
- **Extension Precaching**: Automatically precaches extensions for faster startup
- **Registry Support**: Multiple extension registries (kit/default, kit/sdk, kit/community)

### Package Management
- **Fat Packages**: Include all dependencies, suitable for distribution
- **Thin Packages**: Rely on Kit registry, smaller size for development
- **Precaching**: Extensions are pre-downloaded and cached during build process

## Voxel Carver Implementation Notes

### Extension Location
- **Main File**: `source/extensions/voxel_carver/voxel_carver/extension.py`
- **Carver Tool Path**: `/World/New_MillingMachine/Main/Doril/Drill/CarverTool`
- **Colliders Root**: `/World/New_MillingMachine/Table/VoxelColliders` (created as child of Table)
- **Global Instance**: Provides `_extension_instance` for inter-extension communication

### Collision Detection Methods

The extension supports **two collision detection modes** selectable via UI:

#### 1. PhysX-Based Collision Detection (Recommended)
- **Method**: Creates PhysX collider primitives for surface voxels, uses `ComputeLocalToWorldTransform()` for accurate world coordinates
- **Advantages**: Parent transform-independent, handles complex hierarchies correctly, immune to scale/rotation issues
- **Implementation**:
  - Surface voxels get invisible Cube colliders with CollisionAPI
  - Colliders created as children of Table with proper coordinate transformation
  - Parent scale compensation applied via inverse scale transform
  - AABB collision check in world coordinate space
- **Key Functions**: `_create_voxel_colliders()` (568-699), `_check_physx_collision()` (701-799)

#### 2. Coordinate-Based Collision Detection (Legacy)
- **Method**: Direct coordinate calculation using transform matrices
- **Advantages**: Faster, lower memory overhead
- **Disadvantages**: Susceptible to parent transform issues if not carefully managed
- **Key Function**: `_on_update()` with coordinate mode (801-928)

### Parent Transform Handling (Critical)

**Problem**: Parent prim scale/rotation affects child collider size and position

**Solution**: Inverse scale compensation
```python
# Extract parent scale from world transform
parent_x_scale = Vec3d(transform[0][0:3]).GetLength()

# Calculate inverse scale to cancel parent's effect
inverse_scale = (1/parent_x_scale, 1/parent_y_scale, 1/parent_z_scale)

# Apply to collider to maintain uniform size
collider.AddScaleOp().Set(inverse_scale)
```

This ensures all colliders remain uniform size regardless of Table's transform hierarchy.

### Coordinate Transformation Pipeline

1. **Voxel Grid Coordinates**: Integer indices (x, y, z) in grid space
2. **Grid-to-World**: `grid_origin + (x + 0.5, y + 0.5, z + 0.5) × voxel_size`
3. **World-to-Parent-Local**: `parent_world_to_local.Transform(world_pos)`
4. **Set Position**: Store as local coordinate under parent prim

**Key Point**: When moving VoxelColliders manually in hierarchy, coordinates become invalid. Always create colliders programmatically in correct parent from the start.

### Collision Detection Algorithm Details

**AABB (Axis-Aligned Bounding Box) Check**:
```python
diff = voxel_world_pos - carver_world_pos
collision = (abs(diff[0]) < half_width + voxel_size/2 and
             abs(diff[1]) < half_height + voxel_size/2 and
             abs(diff[2]) < half_depth + voxel_size/2)
```

**CarverTool Effective Size**:
- Extract scale from world transform matrix (vector length method)
- Calculate: `effective_half_extent = (cube_size / 2.0) × axis_scale`
- Accounts for full transform hierarchy automatically

### Alternative Collision Detection Methods
Game industry collision approaches (for reference):
- **Sphere**: Single distance check, rotation-independent, simple
- **Capsule**: Line segment + radius, ideal for characters
- **OBB**: Oriented bounding box, handles rotation better than AABB
- **Mesh**: Triangle-level precision, very expensive
- **Spatial Partitioning**: Octree/BVH for large-scale optimization

### Debug Tools (UI Buttons)

- **Visualize Colliders**: Makes invisible colliders visible (pink=standalone, yellow=child of Table)
- **Collider Info**: Shows sample collider positions, PhysX API status
- **CarverTool Info**: Displays position, scale, nearby colliders with simulated collision results

Debug functions: `visualize_colliders()` (147-168), `debug_colliders()` (170-208), `debug_carver()` (210-302)

### Integration with Physical Buttons
- **Start/Stop Control**: Physical buttons can trigger voxel carving simulation
- **Method Interfaces**: `on_start_simulation()` and `on_stop_simulation()` for external control
- **Extension Registry**: Registered as "voxel_carver" for remote method calls

### Voxel Grid Management
- **Grid Resolution**: Configurable voxel size (0.5-5.0 units), affects precision vs. performance
- **Memory Structure**: NumPy uint8 array (1=solid, 0=carved)
- **Collider Strategy**: Creates colliders for ALL voxels upfront (simpler and more reliable than surface-only approach)
  - Previous surface-only approach had issues with missing colliders when voxels were carved
  - All-voxel approach: ~1,105 colliders for typical workpiece, negligible performance impact
  - Simplifies code by eliminating dynamic collider addition logic
- **Mesh Generation**: Greedy meshing algorithm - only generates faces adjacent to empty space
- **Coordinate Conversion**: Workpiece defined in world coordinates, VoxelMesh placed as child of Table with proper local coordinate conversion

## Japanese Text Support

### Character Encoding
- **UTF-8 Wrapper**: Use `repo_utf8.bat` on Windows for proper Japanese character handling
- **Environment Variables**: Sets `PYTHONUTF8=1` and `PYTHONIOENCODING=utf-8`
- **Extension Descriptions**: Supports Japanese text in extension.toml descriptions and UI labels

## Testing and Development Workflow

### Single Extension Testing
- **Test specific extension**: Use Kit's test runner to target individual extensions
- **Extension test structure**: Tests located in `{extension_name}/tests/` follow `omni.kit.test.AsyncTestCaseFailOnLogError` pattern
- **Async testing**: Full async/await support for USD and physics operations

### Physics System Testing
- **Manual testing**: Use physical button interactions or UI manual controls for real-time testing
- **Parameter validation**: Physics parameter effectiveness can be tested by adjusting stiffness, damping ranges
- **Coordinate system validation**: Use debug output to verify world vs local coordinate transformations

### Inter-Extension Communication Testing
- **Registry testing**: Verify extension registration/unregistration through startup/shutdown cycles
- **Method invocation testing**: Test remote method calls and fallback mechanisms
- **Extension isolation**: Each extension should handle graceful failure when dependencies are unavailable

## Current Extension Architecture Summary

The milling machine application (`my_milling_machine.project.kit`) currently includes these key functional extensions:

### Core Physics and Control
- `handle_angle`: Primary physics simulation with RevoluteJoint control and transform monitoring
- `physical_button`: Interactive control system using existing Switch1/Switch2 objects
- `voxel_carver`: Material removal simulation with world coordinate tracking
- `observer_system`: Central state monitoring and object management system
- `item_placement_system`: PhysX Trigger-based item placement with proxy/real object system, per-object task scripts, and VR detachment support

### Support and Utility Extensions
- `handle_controller`: Scene creation and object coordination
- `trigger_tracking` / `trigger_observation`: Physics tracking and state monitoring
- `doril_clear`, `drill_boolean`, `drill_cut`: Drilling operation mechanics
- `my.object.follower`: Object following behavior system
- `my_reset_extension`: Scene and object reset functionality

All extensions follow the standard Omniverse extension structure with `config/extension.toml`, main `extension.py` implementing `omni.ext.IExt`, and `tests/` directory for validation.

## Observer System Extension (observer_system)

### Core Functionality
The observer_system extension provides centralized state monitoring and object management:

- **Extension Location**: `source/extensions/observer_system/observer_system/extension.py`
- **Core Class**: `ObserverSystemExtension` - Central system state manager
- **Global Access**: Provides `get_extension_instance()` for inter-extension communication

### System Configuration
Pre-configured trigger and system paths for the milling machine:
- **Drill Trigger**: `/World/New_MillingMachine/Main/Doril/Trigger_Drill` (expected number: 1)
- **Table Trigger**: `/World/New_MillingMachine/Table/Trigger_Table` (expected number: 2)
- **Plug Trigger**: `/World/Industrial/Industrial/Trigger_Plug` (expected number: 3)
- **System Paths**: Ground collider, item tray, and stock locations

### State Management API
Public methods for system state control:
- `set_power_connected(bool)`: Manage power connection state
- `get_current_scenario_step()`: Track scenario progression
- `set_scenario_step(int)`: Update scenario step
- `set_object_removable(path, bool)`: Control object detachment permissions
- `show_message(message, type)`: Display system messages

### Integration Pattern
Designed for future enhancement with:
- PhysX Trigger API integration for object detection
- Real-time UI components for status display
- Scenario-based progression system
- Force monitoring and object detachment mechanics

## 一般的なトラブルシューティングパターン

### 座標系の問題
**問題**: トランスフォームを設定するとオブジェクトが予期しない位置に移動する
- **原因**: ワールド座標（`ComputeLocalToWorldTransform()`から）とローカル座標操作（`TranslateOp.Set()`）を混在させている
- **解決策**: 一貫した座標系を使用 - `TranslateOp.Get()/Set()`を介して両方をローカル座標として読み書き
- **よくある間違い**: `TranslateOp.Set(base_position)`で位置を設定してから`ComputeLocalToWorldTransform()`で読み戻す - これは座標系の不一致を生む
- **ベストプラクティス**: ローカル座標で設定した場合は、ローカル座標で読み戻す；`base_position`を`initial_position`として直接保存
- **デバッグ**: ワールド座標とローカル座標の両方をログして不一致を特定

### ボクセルシステムでのコライダー欠落
**問題**: 一部のボクセル、特に内部ボクセルにコライダーがない
- **原因**: 表面のみのコライダー生成は動的な彫刻をうまく処理できない
- **解決策**: 表面のみの最適化ではなく、すべてのボクセルに対して事前にコライダーを作成
- **トレードオフ**: メモリが若干多め（約1,100コライダー vs 600）だが、はるかに信頼性が高く、コードがシンプル

## プラットフォーム互換性ノート

### Linux ビルド要件
プロジェクトはクロスプラットフォーム互換性のために設定されている：
- **バージョンロック除外**: `omni.kit.window.modifier.titlebar`のようなWindows専用拡張機能はLinuxビルドから除外
- **プラットフォームフィルター**: プラットフォーム固有の除外に`[settings.app.extensions."filter:platform"."linux-x86_64"]`を使用
- **UTF-8サポート**: Linuxビルドは環境設定を通じて日本語テキストを適切に処理

### ビルドトラブルシューティング
一般的なビルド問題と解決策：
- **Windows専用依存関係**: Linux上でバージョンロックからWindows固有の拡張機能が除外されていることを確認
- **拡張機能の依存関係**: 拡張機能の`config/extension.toml`を最小限に保つ - 必要でない限り複雑な依存関係を避ける
- **プラットフォーム固有のコマンド**: 適切な行末処理で`./repo.sh`（Linux） vs `.\repo.bat`（Windows）を使用

## 拡張機能開発のベストプラクティス

### 新しい拡張機能の作成
このプロジェクト用の拡張機能を作成する際：
1. **テンプレートシステムを使用**: `./repo.sh template new`で開始し、"Extension" > "Basic Python"を選択
2. **最小限の依存関係**: ビルド競合を避けるために`config/extension.toml`の依存関係を最小限に保つ
3. **グローバルインスタンスパターン**: 拡張機能間通信のために`get_extension_instance()`関数を提供
4. **適切なクリーンアップ**: リソースリークを避けるために`on_shutdown()`で適切なシャットダウンを実装
5. **エラー処理**: USD操作と物理API呼び出しにtry-catchブロックを使用

### 既存システムとの統合
フライス盤と統合する新しい拡張機能の場合：
- **命名規則に従う**: 小文字、アンダースコア区切りの名前を使用
- **Kitファイルに追加**: `source/apps/my_milling_machine.project.kit`の依存関係に拡張機能を含める
- **Premakeでリンク**: 拡張機能がビルドシステム統合を必要とする場合は`premake5.lua`を更新
- **拡張機能レジストリを検討**: 他の拡張機能との通信にレジストリパターンを使用

### 物理演算とUSD統合
物理シミュレーションを扱う際：
- **ワールド座標**: 位置追跡には常に`ComputeLocalToWorldTransform()`を使用
- **Transform監視**: Articulation競合を避けるためにJointStateAPIではなくTransform行列を監視
- **軸規約**: Y-up座標系に従い、軸設定を徹底的にテスト
- **パラメータ調整**: 確立されたパラメータ範囲から開始（剛性：1e6-1e7、減衰：1e4-1e5）

## Item Placement System (item_placement_system)

### System Overview
The item placement system has been migrated to a **PhysX Trigger-based architecture** for robust, physics-integrated item validation and placement. The system uses PhysX Trigger enter/leave events to automatically detect, validate, and place or reset items based on their `Number` attribute.

### Architecture Components

#### Core Files
- **Extension Entry**: `source/extensions/item_placement_system/item_placement_system/extension.py` - Routes to trigger-based system
- **Main Extension**: `source/extensions/item_placement_system/item_placement_system/extension_trigger.py` - UI and control
- **Trigger Manager**: `source/extensions/item_placement_system/item_placement_system/trigger_manager.py` - Configuration and setup
- **Trigger Script**: `source/extensions/item_placement_system/item_placement_system/trigger_placement_script.py` - PhysX callback handler
- **Task Manager**: `source/extensions/item_placement_system/item_placement_system/task_manager.py` - Task system coordination
- **Placement State Manager**: `source/extensions/item_placement_system/item_placement_system/placement_state_manager.py` - Proxy/real object state management
- **Task Scripts**: `source/extensions/item_placement_system/item_placement_system/task_scripts/` - Per-object task implementations
- **Legacy System**: `extension_backup.py` - Original proximity-based system (deprecated)

#### Key Classes
- **`ItemPlacementTriggerExtension`** - Main extension providing UI and system control
- **`TriggerManager`** - Manages trigger slots, applies PhysxTriggerAPI to prims
- **`TriggerSlot`** - Configuration dataclass for individual trigger slots with proxy/task support
- **`TaskManager`** - Manages task script instances and completion checking
- **`PlacementStateManager`** - Controls proxy/real object visibility and placement lifecycle
- **`BaseTask`** - Abstract base class for per-object task scripts
- **Trigger Script Functions** - `handle_enter_event()`, `place_item_correct()`, `handle_proxy_placement()`

### PhysX Trigger Integration

#### Trigger Configuration
The system uses `PhysxSchema.PhysxTriggerAPI` to configure collision-based triggers:
- **CollisionAPI**: Applied to trigger prims for physics detection
- **PhysxTriggerAPI**: Configures enter/leave script callbacks
- **TriggerStateAPI**: Monitors active collisions in real-time
- **Script Callbacks**: Points to `trigger_placement_script.py` for event handling

#### Default Trigger Slots
Configured in `trigger_manager.py` DEFAULT_SLOTS:
```python
TriggerSlot(
    slot_id="trigger_slot_1",
    trigger_path="/World/New_MillingMachine/Table/Set_Base/Trigger_Table",
    correct_numbers=[1],
    placement_translate=(10.0, 5.0, 0.0),
    display_name="スロット1 (Number=1)"
),
TriggerSlot(
    slot_id="trigger_slot_3",
    trigger_path="/World/Industrial/Industrial/Trigger_Plug",
    correct_numbers=[3],
    placement_translate=(115.0, -0.63, 78.5),
    placement_path="/World/Industrial/Industrial",
    display_name="スロット3 (Number=3)"
)
```

### Proxy/Real Object System

#### Purpose and Design
The system supports objects that cannot have RigidBody components (e.g., voxel meshes) by using a proxy pattern:
- **Proxy Object**: Dummy object with RigidBody for physics detection
- **Real Object**: Actual functional object, initially hidden
- **State Machine**: `IDLE → PLACED → DETACHABLE → DETACHED`

#### State Lifecycle
1. **IDLE**: Proxy is visible and detectable in trigger
2. **PLACED**: Proxy moved to reset position (hidden), real object becomes visible, task starts
3. **DETACHABLE**: Task completed, object can be removed via VR controller
4. **DETACHED**: Real object hidden, proxy returns to original position

#### ProxyMapping Configuration
```python
from item_placement_system.trigger_manager import ProxyMapping

proxy_mapping = ProxyMapping(
    proxy_path="/World/Items/VoxelMesh_Proxy",  # Dummy with RigidBody
    real_path="/World/Table/VoxelMesh",         # Actual object
    initial_hidden=True                         # Real object starts hidden
)
```

#### PlacementStateManager Methods
- **`on_placement()`**: Called when correct item enters trigger
  - Moves proxy to `proxy_reset_position` (e.g., (0, 100, 0))
  - Shows real object via `UsdGeom.Imageable.MakeVisible()`
  - Starts associated task
- **`on_detachment()`**: Called when user removes object (VR Grip + 15cm pull)
  - Hides real object
  - Moves proxy back to `proxy_original_position`
  - Shows proxy again
  - Resets task state
- **`check_detachment_allowed()`**: Checks if task is completed before allowing detachment

### Task System

#### Architecture
Per-object scriptable tasks that must be completed before item detachment:
- **Plugin Pattern**: Tasks inherit from `BaseTask` abstract class
- **Dynamic Loading**: TaskManager registers and instantiates task classes
- **Completion Gating**: `check_completion(stage) -> bool` called every frame

#### Available Task Types
1. **VoxelMeshTask** (`task_type="voxel_mesh"`):
   - Requires handle_drill rotation to -100° or less
   - Monitors `/World/New_MillingMachine/Main/Handle_Dril/RevoluteJoint`
   - Reads `DriveAPI.targetPosition` attribute

2. **PlugTask** (`task_type="plug"`):
   - Requires object movement to within 10cm of target position
   - Target: (115.0, 5.0, 78.5) in world coordinates
   - Uses `ComputeLocalToWorldTransform()` for distance calculation

3. **NoTask** (`task_type="none"`):
   - No completion requirement
   - Immediately detachable after placement

#### Creating Custom Tasks
```python
from item_placement_system.task_scripts.base_task import BaseTask

class CustomTask(BaseTask):
    def __init__(self, slot_id: str, real_object_path: str):
        super().__init__(slot_id, real_object_path)
        # Initialize custom parameters

    def check_completion(self, stage: Usd.Stage) -> bool:
        # Implement completion logic
        return True  # or False

    def on_task_start(self, stage: Usd.Stage):
        super().on_task_start(stage)
        # Custom start logic

    def on_task_complete(self, stage: Usd.Stage):
        super().on_task_complete(stage)
        # Custom completion logic
```

Register in `task_manager.py`:
```python
def _register_task_classes(self):
    from .task_scripts.custom_task import CustomTask
    self._task_classes['custom'] = CustomTask
```

### Item Validation System

#### Number Attribute Detection
Items must have integer `Number` attribute:
```python
item_prim.CreateAttribute("Number", Sdf.ValueTypeNames.Int).Set(item_number)
```

#### Validation Logic
When an item enters a trigger:
1. Extract item's `Number` attribute
2. Compare against trigger's `correct_numbers` list
3. **Correct (Standard)**: Call `place_item_correct()` - place at target position, disable RigidBody
4. **Correct (Proxy System)**: Call `handle_proxy_placement()` - switch proxy to real object, start task
5. **Incorrect**: Call `reset_item_incorrect()` - reset to origin (0,0,0)

### Item Placement Mechanism

#### Coordinate Transformation Strategy
**Critical**: Uses coordinate transformation rather than prim reparenting to avoid simulation crashes

```python
# Calculate world position from target parent's coordinate system
target_world_pos = target_parent_world_tf.Transform(target_translate)

# Convert to current parent's local coordinate system
current_world_to_local = current_parent_xform.ComputeLocalToWorldTransform().GetInverse()
final_translate = current_world_to_local.Transform(target_world_pos)

# Set position without changing hierarchy
translate_op.Set(final_translate)
```

**Why this approach?**
- **USD Mutex Error**: Using `Sdf.BatchNamespaceEdit()` during PhysX simulation causes "m_recursive assertion failed" crash
- **Safe Alternative**: Transform coordinates between different parent spaces without modifying USD hierarchy
- **Hierarchy Independence**: Item can appear to be placed at target location without actually reparenting

#### RigidBody Deactivation
Correct approach for fixing objects in place:
```python
# Set kinematicEnabled to fix object (no physics simulation, but still detectable)
kinematic_attr = rb_api.GetKinematicEnabledAttr()
if not kinematic_attr:
    kinematic_attr = rb_api.CreateKinematicEnabledAttr()
kinematic_attr.Set(True)

# Reset velocities
rb_api.GetVelocityAttr().Set(Gf.Vec3f(0, 0, 0))
rb_api.GetAngularVelocityAttr().Set(Gf.Vec3f(0, 0, 0))
```

### Configuration and Customization

#### Adding New Trigger Slots

**Standard Slot** (no proxy system):
```python
TriggerSlot(
    slot_id="trigger_slot_new",
    trigger_path="/World/Path/To/Trigger",
    correct_numbers=[5, 6],
    placement_translate=(50.0, 10.0, 5.0),
    placement_path="/World/Optional/Parent",
    scenario_id=1,
    display_name="New Slot (Number=5,6)"
)
```

**Proxy/Task System Slot** (for objects without RigidBody):
```python
from item_placement_system.trigger_manager import ProxyMapping

TriggerSlot(
    slot_id="voxel_mesh_slot",
    trigger_path="/World/Table/Trigger_Table",
    correct_numbers=[1],

    # Proxy/Real object configuration
    proxy_mapping=ProxyMapping(
        proxy_path="/World/Items/VoxelMesh_Proxy",
        real_path="/World/Table/VoxelMesh",
        initial_hidden=True
    ),

    # Task configuration
    task_type="voxel_mesh",  # or "plug", "none"

    # Proxy position management
    placement_translate=(10.0, 5.0, 0.0),      # Where proxy originally sits
    proxy_original_position=(0, 0, 0),         # Return position after detachment
    proxy_reset_position=(0, 100, 0),          # Hide position during use

    display_name="Voxel Mesh Slot"
)
```

#### Placement Coordinate Systems
- **placement_translate**: Local coordinates relative to `placement_path` parent (or current parent if not specified)
- **placement_path**: Optional parent prim path - if provided, calculates world position from this parent's transform
- **Coordinate Conversion**: Automatically handles transform hierarchy using `ComputeLocalToWorldTransform()`

### UI Features

#### Status Display
- **Trigger Detection Status**: Enabled/disabled indicator
- **Slot Monitoring**: Real-time display of active collisions per slot
- **Trigger Paths**: Shows configured USD paths for each slot
- **Expected Numbers**: Displays correct_numbers for each trigger

#### Control Functions
- **状態更新** (Refresh Status): Update trigger status display manually
- **トリガー診断** (Diagnose): Output detailed system state to console
- **トリガー有効化/無効化** (Enable/Disable): Toggle trigger detection
- **トリガー再セットアップ** (Reinitialize): Reapply PhysxTriggerAPI to all slots

### Critical Lessons Learned

#### ⚠️ PhysX Simulation Crashes
**Problem**: Using `Sdf.BatchNamespaceEdit()` to reparent prims during PhysX simulation causes mutex recursion crash:
```
'm_recursive' assertion failed at carb.tasking.Mutex.lock()
"Recursion not allowed"
```

**Root Cause**: USD structure modifications are not thread-safe during PhysX simulation updates

**Solution**: Use coordinate transformation instead of reparenting:
- Calculate target position in world coordinates
- Convert to item's current parent's local coordinates
- Update position without modifying USD hierarchy
- This achieves the same visual result without USD structure changes

#### RigidBody Disabling Requirements
**Critical**: `disableSimulation` does NOT exist in Omniverse (it's an Unreal Engine feature)

**Correct Approach**: Use `kinematicEnabled` to fix objects in place:
1. Set `kinematicEnabled = True` to fix object (no physics simulation)
2. Zero out all velocities: `velocity` and `angularVelocity` to (0, 0, 0)
3. To restore dynamic behavior: Set `kinematicEnabled = False`

**Why Kinematic?**: Kinematic objects remain in the scene and can be raycast/detected, but don't respond to forces or gravity.

#### Trigger Script Execution Context
- **Invoked by PhysX Engine**: Script runs in PhysX thread context
- **Stage Access**: Use `UsdUtils.StageCache.Get().Find()` with stage_id parameter
- **Error Handling**: All exceptions must be caught - uncaught errors crash simulation
- **Debug Logging**: Use `DEBUG_MODE` flag to control verbose output

#### ⚠️ PhysX Direct Interface Required for Runtime Position Changes
**Problem**: Setting USD attributes alone (e.g., `translate_op.Set()`) during PhysX simulation does not immediately update object positions.

**Root Cause**: USD attribute changes are not synchronized to PhysX simulation state in real-time during trigger callbacks.

**Solution**: Use PhysX simulation interface to directly update physics state:
```python
import omni.physx

# Update position
physx_interface = omni.physx.get_physx_simulation_interface()
position_carb = carb.Float3(float(x), float(y), float(z))
physx_interface.set_rigidbody_position(prim_path, position_carb)

# Reset velocities
zero_velocity = carb.Float3(0.0, 0.0, 0.0)
physx_interface.set_rigidbody_linear_velocity(prim_path, zero_velocity)
physx_interface.set_rigidbody_angular_velocity(prim_path, zero_velocity)
```

**Best Practice**: Always update both USD attributes AND PhysX state:
1. Set USD attribute (for persistence): `translate_op.Set(position)`
2. Set PhysX state (for immediate effect): `physx_interface.set_rigidbody_position()`
3. Zero velocities to prevent residual momentum
4. This pattern applies to: position, velocity, angular velocity, and kinematic state changes

**Implementation**: See `trigger_placement_script.py` functions:
- `set_translate()` (lines 186-228) - Position updates
- `reset_velocities()` (lines 231-266) - Velocity zeroing
- `handle_incorrect_item()` (lines 348-375) - Complete reset sequence

### Development Integration

#### Creating Trigger Prims in USD
1. Create Cube/Sphere/Capsule geometry at trigger location
2. Right-click → Add → Physics → Collider
3. Extension automatically applies PhysxTriggerAPI on startup
4. No manual PhysX configuration needed

#### Item Setup Requirements
```python
from pxr import Sdf

# Add Number attribute to items
item_prim = stage.GetPrimAtPath("/World/Items/Item1")
number_attr = item_prim.CreateAttribute("Number", Sdf.ValueTypeNames.Int)
number_attr.Set(1)  # This item's identification number

# Ensure item has RigidBody for physics interaction
from pxr import UsdPhysics
UsdPhysics.RigidBodyAPI.Apply(item_prim)
```

#### Accessing the System from Other Extensions
```python
from item_placement_system.extension import get_extension_instance

ext = get_extension_instance()
if ext:
    # Get managers
    trigger_mgr = ext.get_trigger_manager()
    task_mgr = ext.get_task_manager()
    state_mgr = ext.get_placement_state_manager()

    # Check if object can be detached
    can_detach = state_mgr.check_detachment_allowed("voxel_mesh_slot", stage)

    # Manually trigger detachment (e.g., from VR UI)
    if can_detach:
        state_mgr.on_detachment(
            slot_id="voxel_mesh_slot",
            stage=stage,
            real_path="/World/Table/VoxelMesh",
            proxy_path="/World/Items/VoxelMesh_Proxy",
            proxy_original_position=(0, 0, 0)
        )

    # Add new slot dynamically
    ext.add_trigger_slot(
        slot_id="dynamic_1",
        trigger_path="/World/NewTrigger",
        correct_numbers=[10],
        placement_translate=(100.0, 0.0, 0.0),
        display_name="Dynamic Slot"
    )
```

### Documentation
- **Quick Start**: `README_TRIGGER.md` - 5-minute setup guide
- **User Guide**: `docs/TRIGGER_SYSTEM_GUIDE.md` - Complete usage documentation
- **Implementation**: `docs/IMPLEMENTATION_GUIDE.md` - Developer reference

### VR Detachment Integration

The item_placement_system is integrated with VR Grip button for object detachment:

**Implementation**: `vr_ui` extension (`source/extensions/vr_ui/vr_ui/extension.py`)

**Detection Flow**:
1. **Grip Button Press** → Attempt detachment detection
2. **First try Raycast** (50cm forward ray) - works for Dynamic objects
3. **Fallback to Overlap Sphere** (50cm forward center, 30cm radius) - detects Kinematic objects
4. **Check USD Attributes**: `custom:placed=True` AND `custom:task=True`
5. **Execute Detachment**: Set `custom:placed=False`, restore object to dynamic state
6. **Grab Object**: Allow VR Trigger button to grab and move the detached object

**Why Overlap Detection?**: Kinematic objects (fixed with `kinematicEnabled=True`) are invisible to PhysX raycast. `overlap_sphere()` detects all physics bodies including Kinematic.

**Implementation** (`_attempt_detachment()` in vr_ui/extension.py, lines 1762-1853):
```python
# Try raycast first (for Dynamic objects)
hit = scene_query.raycast_closest(tuple(controller_pos), tuple(forward_vec), 200.0)

# Fallback to overlap sphere (for Kinematic objects)
if not hit_prim_path:
    target_pos = controller_pos + forward_vec * 50.0  # 50cm forward
    overlaps = scene_query.overlap_sphere(
        carb.Float3(float(target_pos[0]), float(target_pos[1]), float(target_pos[2])),
        30.0  # 30cm radius
    )
    # Select closest object from overlaps

# Check detachment conditions
if custom:placed == True and custom:task == True:
    # For proxy items: call PlacementStateManager.on_detachment()
    # For normal items: set kinematicEnabled=False
```

**Detachment Actions**:
- **Proxy System Items**: Calls `PlacementStateManager.on_detachment()` → hides real object, restores proxy
- **Standard Items**: Sets `kinematicEnabled=False` → object becomes dynamic and grabbable

### Simulation Stop Cleanup

**Critical**: The system implements automatic cleanup when simulation stops to restore objects to their initial state.

#### Implementation Strategy
Uses **USD attributes** to persist placement information across different execution contexts:
- Placement info saved to USD during trigger event (PhysX thread)
- Cleanup reads from USD during simulation stop (extension thread)
- Avoids PlacementStateManager instance separation issues

#### Cleanup Process

**For Proxy System Items**:
```python
# Saved during placement (trigger_placement_script.py)
proxy_prim.CreateAttribute("custom:proxy_placed", Sdf.ValueTypeNames.Bool).Set(True)
proxy_prim.CreateAttribute("custom:real_object_path", Sdf.ValueTypeNames.String).Set(real_path)
proxy_prim.CreateAttribute("custom:slot_id", Sdf.ValueTypeNames.String).Set(slot_id)

# Cleanup on simulation stop (extension_trigger.py)
for prim in stage.Traverse():
    if prim.GetAttribute("custom:proxy_placed").Get():
        real_path = prim.GetAttribute("custom:real_object_path").Get()
        # Set visibility=invisible, collisionEnabled=False
```

**For Standard Placed Items**:
```python
# Cleanup on simulation stop
if prim.GetAttribute("custom:placed").Get():
    # Re-enable RigidBody: kinematicEnabled=False (restore dynamic behavior)
```

**Timeline Event Detection**:
```python
def _on_timeline_event(self, event):
    if event.type == int(omni.timeline.TimelineEventType.STOP):
        self._cleanup_on_simulation_stop()
```

#### Cleanup Actions

| Item Type | Action on Simulation Stop |
|-----------|---------------------------|
| Proxy System (Real Object) | visibility → invisible, collisionEnabled → False |
| Standard Placed Items | kinematicEnabled → False (restore dynamic behavior) |
| All Items | Clear placement flags (custom:proxy_placed, custom:placed) |

**Why USD Attributes?**: PhysX trigger script and extension run in different execution contexts with separate PlacementStateManager instances. USD provides persistent storage accessible from both contexts.

### Future Enhancements
- Scenario-based progression system integration
- Dynamic slot configuration via UI
- Multi-step placement sequences
- Item combination validation
- Visual placement preview
- VR controller detachment UI feedback

## VR/XR統合機能

### 概要
NVIDIA Omniverse Kit SDKには、没入型学習およびトレーニングアプリケーションを作成するための`omni.kit.xr.core`拡張機能と関連ツールを通じた包括的なVR/XRサポートが含まれています。

### 主要なXR拡張機能
- **`omni.kit.xr.core`**: コアXRランタイム管理、ヘッドセット検出、コントローラー入力
- **`omni.kit.xr.profile.vr`**: VR固有のプロファイルと設定
- **SceneUIフレームワーク**: 3D VR空間でUI要素を直接表示

### 利用可能なVR機能

#### 1. UI Display in VR
Use SceneUI to create 3D UI elements visible in VR headsets:
```python
import omni.kit.xr.ui as xr_ui
from omni.kit.xr.core import XRCore

# Create UI in VR space
with xr_ui.scene_ui():
    with xr_ui.VStack():
        xr_ui.Label("Instructions for VR User")
        xr_ui.Button("Start Training", clicked_fn=on_start)
```

**Features**:
- Floating panels in 3D space
- Hand-trackable UI elements
- Context-sensitive help overlays
- Progress indicators and feedback

#### 2. Controller Input Detection
Access VR controller state through XRCore singleton:
```python
from omni.kit.xr.core import XRCore

xr_core = XRCore.get_singleton()

# Get controller states
left_controller = xr_core.get_controller_state(0)  # Left hand
right_controller = xr_core.get_controller_state(1)  # Right hand

# Check button presses
if left_controller.trigger_pressed:
    # Handle trigger press
    pass

# Get controller position and orientation
position = left_controller.position
rotation = left_controller.rotation
```

**Available Inputs**:
- Trigger buttons
- Grip buttons
- Thumbstick/trackpad
- System buttons
- Controller position and rotation in world space

#### 3. Learning Application Pattern
Combine VR capabilities for training applications:
```python
class VRTrainingExtension:
    def __init__(self):
        self.xr_core = XRCore.get_singleton()
        self._setup_vr_ui()
        self._setup_controller_handlers()

    def _setup_vr_ui(self):
        # Display instructions in VR
        with xr_ui.scene_ui():
            self._create_instruction_panel()
            self._create_progress_display()

    def _on_update(self):
        # Track controller interactions with machine parts
        left_state = self.xr_core.get_controller_state(0)
        right_state = self.xr_core.get_controller_state(1)

        # Detect tool grabbing
        if right_state.grip_pressed:
            self._grab_tool_at_position(right_state.position)
```

### Integration with Milling Machine Simulation
VR can enhance the milling machine training by:
- **Immersive Training**: Users manipulate handles and controls in VR
- **Safety Training**: Practice in safe virtual environment
- **Guided Tutorials**: Step-by-step instructions in VR space
- **Assessment**: Track user performance and interactions
- **Remote Collaboration**: Multiple users can observe training sessions

### XR Configuration
Enable XR in application kit file:
```toml
[dependencies]
"omni.kit.xr.core" = {}
"omni.kit.xr.profile.vr" = {}

[settings]
rtx.sceneDb.ambientLightIntensity = 0.5  # Optimize for VR
```

## VR UI拡張機能 (vr_ui)

### 概要
`vr_ui`拡張機能は、フライス盤シミュレーション用のVRコントローラー入力監視、VR空間での3D UI表示、VRベースの物理インタラクションを提供します。

### 拡張機能の場所
- **メインファイル**: `source/extensions/vr_ui/vr_ui/extension.py`
- **Prim UI System**: `source/extensions/vr_ui/vr_ui/prim_ui_system.py` - Prim選択追従3D UI
- **VR UI System**: `source/extensions/vr_ui/vr_ui/vr_ui_system.py` - HMD追従画像ビューアーUI
- **コアクラス**: `VRTestUIExtension` - VR機能を実装するメイン拡張機能
- **グローバルアクセス**: 拡張機能間通信のための`get_extension_instance()`

### 主要機能

#### 1. VRコントローラー入力監視
すべてのVRコントローラー入力を監視（Meta Quest互換）：
- **Trigger（トリガー）**: 主要なインタラクションボタン（物理インタラクション）
- **Grip（グリップ）**: 二次的な掴みボタン（アイテム取り外し）
- **A/Bボタン**（右手）: アクションボタン（Aボタン：UI表示切り替え）
- **X/Yボタン**（左手）: アクションボタン
- **Thumbstick（サムスティック）**: アナログ入力

デスクトップUIウィンドウとVR空間の両方でリアルタイムボタン状態表示。

#### 2. HMD追従画像ビューアーUI (NEW - Kit 106.4+ API)
**アーキテクチャ**: `omni.kit.xr.scene_view.utils` APIベースの実装

**機能**:
- **Aボタントグル**: 右手Aボタンで表示/非表示切り替え
- **HMD位置追従**: HMDの前方50cm、下方20cmに固定表示
- **画像ビューアー**: 指定フォルダ内のjpg/png画像を表示
- **ナビゲーション**: 「進む」「戻る」ボタンで画像切り替え
- **タスク表示**: 上部にタスク情報表示（将来の拡張用）
- **カメラ向きビルボード**: UIが常にユーザーを向く

**実装コンポーネント**:
```python
# ImageViewerWidget - 画像ビューアーUIコンテンツ
class ImageViewerWidget(ui.Frame):
    - タスク表示エリア（上部）
    - 画像表示エリア（中央・400px）
    - 進む/戻るボタン（下部）
    - 画像ファイル管理（jpg/jpeg/png自動検索）

# VRUISystem - HMD追従UI管理
class VRUISystem:
    - HMD位置取得（get_virtual_world_pose()）
    - UIの表示/非表示切り替え
    - UiContainer + WidgetComponent + SpatialSource
```

**SpatialSourceスタック**:
```python
space_stack = [
    SpatialSource.new_translation_source(hmd_position + offset),  # HMD位置
    SpatialSource.new_look_at_camera_source()                     # ビルボード
]
# offset = Gf.Vec3d(0, -20, -50)  # Y:-20cm(下), Z:-50cm(前)
```

**画像フォルダ設定**:
- デフォルト: `source/extensions/vr_ui/data/images/`
- 対応形式: .jpg, .jpeg, .png
- ソート順: ファイル名順

**使い方**:
1. 画像を`data/images/`フォルダに配置
2. VRでAボタンを押してUI表示
3. 「進む」「戻る」ボタンで画像切り替え
4. もう一度AボタンでUI非表示

#### 3. Prim選択追従3D UI (NEW - Kit 106.4+ API)
**アーキテクチャ**: `omni.kit.xr.scene_view.utils` APIベースの実装

**機能**:
- **自動Prim追従**: 選択されたPrimの上部に3D UIを表示
- **バウンディングボックス計算**: `UsdGeom.BBoxCache`でUI表示位置を決定
- **カメラ向きビルボード**: UIが常にカメラを向く
- **ステージイベント監視**: `StageEventType.SELECTION_CHANGED`で自動表示/非表示

**実装パターン**:
```python
# WidgetComponent + UiContainer + SpatialSource
widget_component = WidgetComponent(
    widget_type=PrimInfoWidget,
    width=600, height=200,
    resolution_scale=2.0
)

space_stack = [
    SpatialSource.new_prim_path_source(prim_path),      # Prim追従
    SpatialSource.new_look_at_camera_source(),          # ビルボード
    SpatialSource.new_translation_source(Gf.Vec3d(0, y_offset, 0))  # オフセット
]

container = UiContainer(
    widget_component=widget_component,
    space_stack=space_stack,
    scene_view_type=XRSceneView
)
```

**重要なAPI変更** (Kit 106.4+ vs 旧API):
- `SceneViewUtils.startup()/shutdown()` → **不要**（UiContainerが自動管理）
- `create_widget_factory()` → `WidgetComponent + UiContainer`パターン
- `with_transform()` → `SpatialSource`スタック

#### 4. VR物理インタラクション (Trigger Button)

#### 3. VR Mouse Interaction (Trigger Button)
Implements VR controller-based object grabbing using **Force-at-Point method** (identical to PhysX Mouse Interaction):

**Critical Implementation Details**:
- **Does NOT use Kinematic mode** - objects remain Dynamic with full physics simulation
- **Applies force to specific point** where raycast hits, not to object center
- **Works with Joints** - RevoluteJoint/PrismaticJoint constrained objects can be manipulated
- **Visual feedback** - Green line (BasisCurves) shows grab point → controller direction

**Press Trigger** (right hand only):
- Raycasts from controller forward direction (200cm range)
- Finds nearest Dynamic RigidBody prim (Kinematic objects are rejected)
- Saves **grab point** in both world and local coordinates
- Creates green debug line for visual feedback

**Hold Trigger** (updates every frame):
- Calculates current grab point world position from local coordinates
- Computes point velocity (includes rotational component: `v = linear_v + angular_v × r`)
- Applies Spring-Damper force: `F = k(target - current) - damping * velocity`
- Uses `apply_force_at_pos()` to apply force at grab point (generates torque automatically)
- Updates green line to show force direction

**Release Trigger**:
- Stops force application (object continues with inertia)
- Deletes green debug line
- Object remains Dynamic throughout

### Implementation Details

#### Controller Detection
Uses dual-method approach for reliability:
```python
def _get_right_controller(self):
    # Method 1: Search device list for "right" in name
    for device in self._xr_devices:
        if 'right' in device.get_name().lower():
            return device

    # Method 2: Fallback to get_input_device("right")
    return self._xr_core.get_input_device("right")
```

#### Force Application Implementation
```python
# Key state variables
self._grab_point_world = hit_position  # Initial hit position
self._grab_point_local = world_to_local.Transform(hit_position)  # Relative to object
self._target_position = controller_pos  # Updated every frame

# Every frame update:
# 1. Calculate current grab point in world space
current_grab_point = local_to_world.Transform(self._grab_point_local)

# 2. Calculate point velocity (critical for damping)
r = grab_point - object_center  # Radius vector
point_velocity = linear_velocity + angular_velocity.Cross(r)

# 3. Compute Spring-Damper force
displacement = target_position - current_grab_point
spring_force = displacement * strength  # k = 100000.0
damping_force = -point_velocity * damping * strength  # damping = 0.8

# 4. Apply force at specific point
apply_force_at_pos(prim_path, spring_force + damping_force, current_grab_point, "Force")
```

#### Why This Works for Jointed Objects
- **Force at point generates torque**: `τ = r × F` automatically
- **Joints constrain motion**: Force/torque respect Joint limits
- **RevoluteJoint example**: Pulling handle → torque around joint axis → rotation
- **Unlike Kinematic approach**: Which sets position directly and ignores constraints

#### Common Errors to Avoid
1. **Don't apply force to object center** - Won't work for jointed objects
2. **Don't use Kinematic mode** - Disables physics, can't apply forces
3. **Don't mix coordinate spaces** - Always track grab point in local coords, convert to world for force application
4. **Don't forget rotational velocity** - Point velocity ≠ object velocity when rotating
5. **Ensure right-hand only** - Left hand trigger value (0) will immediately cancel grab

### Common Issues and Solutions

#### Issue: Object doesn't move when grabbed
**Cause 1**: Object is Kinematic (force-based interaction requires Dynamic)
**Solution**: Check `kinematicEnabled` attribute, must be `False`

**Cause 2**: `apply_force_at_pos()` not being called every frame
**Solution**: Verify `_handle_trigger_mouse_interaction()` is called for right hand only (`hand == 'right'`)

**Cause 3**: Force magnitude too weak
**Solution**: Increase `_grab_force_strength` (default: 100000.0)

#### Issue: Grabbed object oscillates/vibrates
**Cause**: Damping too low or force too high
**Solution**: Adjust `_grab_damping` (0.0-1.0, default: 0.8) or reduce `_grab_force_strength`

#### Issue: Green line not visible
**Cause**: BasisCurves creation failed or line too thin
**Solution**: Check console for "Error creating debug line", ensure Stage is loaded

#### Issue: RevoluteJoint object doesn't respond
**Cause**: Force applied to object center instead of grab point
**Solution**: Verify `_grab_point_local` is correctly calculated and `apply_force_at_pos()` uses `current_grab_point_world`, not object center

### VR Experience API Patterns
The extension follows patterns from NVIDIA's VR Experience extension:

**HMD Position Tracking**:
```python
hmd = xr_core.get_input_device("displayDevice")
device_pose = hmd.get_virtual_world_pose()
device_pose_upright = xr_core.reorient_transform_matrix_up_right(
    device_pose,
    coord_system.up_axis == "y"
)
```

**Controller Access**:
```python
# Get controller device
controller = xr_core.get_input_device("right")  # or "left"

# Get button state
value = controller.get_input_gesture_value(input_name, 'click')

# Get controller world pose
pose = controller.get_virtual_world_pose()
```

### VR Mouse Interaction Design Pattern

This implementation represents the **correct approach** for VR object manipulation in PhysX:

**Key Principles**:
1. **Point-based force application** - Always apply force at raycast hit point, not object pivot
2. **Dynamic physics maintained** - Never switch to Kinematic mode during interaction
3. **Respect physical constraints** - Joints, collisions, gravity all remain active
4. **Visual feedback essential** - Green line shows force direction (like desktop Mouse Interaction)

**Architecture Flow**:
```
User Action          Controller State        Physics State           Visual Feedback
────────────         ────────────────        ─────────────           ───────────────
Trigger Press   →    Raycast
                     Find hit point     →    Save local coords
                     Cache controller        Create debug line   →   Green line appears

Trigger Hold    →    Update controller  →    Calc current point
(every frame)        position                Apply force at point →  Line tracks movement
                                             (generates torque)

Trigger Release →    Clear state        →    Stop force              Green line disappears
                                             (inertia continues)
```

**Type Conversion Notes**:
- `hit["position"]` returns `carb.Float3` - must convert element-wise to `Gf.Vec3d`:
  ```python
  hit_pos = hit["position"]
  world_pos = Gf.Vec3d(hit_pos[0], hit_pos[1], hit_pos[2])
  ```
- `apply_force_at_pos()` requires `carb.Float3` - convert from `Gf.Vec3d`:
  ```python
  force_carb = carb.Float3(float(force[0]), float(force[1]), float(force[2]))
  ```

### Three VR Control Modes (CRITICAL)

The VR UI extension implements **three distinct control modes** based on object type. Understanding these modes is essential for working with VR interactions:

#### Control Mode Selection Logic

```python
if grabbed_joint_path:
    # Mode 1: Angle-Based Control (DriveAPI targetPosition)
elif has_joint_constraint:
    # Mode 2: Y-Axis Velocity Control (NEW)
else:
    # Mode 3: Velocity-Based Control (default)
```

#### Mode 1: Angle-Based Control (DriveAPI targetPosition)

**When**: RevoluteJoint detected AND `custom:disable_drive` = False (or not set)

**Behavior**:
- Calculates controller's circular motion around joint axis
- Sets DriveAPI targetPosition in degrees
- High precision control with joint limits respected
- Parameters: stiffness=200000, damping=20000, maxForce=500000

**Use Case**: Default mode for RevoluteJoint handles (e.g., handle_front, handle_right)

#### Mode 2: Y-Axis Velocity Control (RevoluteJoint with disable_drive=True)

**When**: RevoluteJoint detected AND `custom:disable_drive` = True

**Critical Discovery**: RevoluteJoint objects respond to **Y-axis linear velocity** as rotational input
- Positive Y velocity → Clockwise rotation
- Negative Y velocity → Counter-clockwise rotation

**Implementation** (source/extensions/vr_ui/vr_ui/extension.py:1537-1576):
```python
# Calculate Y-axis displacement
y_displacement = controller_y - grab_point_y

# Convert to Y-axis velocity (100x multiplier)
target_y_velocity = (y_displacement / dt) * 100.0

# Apply Spring-Damper control
velocity_error = target_y_velocity - current_y_velocity
new_y_velocity = current_y_velocity + (velocity_error * 0.5)

# Set ONLY Y-axis velocity (X and Z are 0)
rb_api.GetVelocityAttr().Set(Gf.Vec3f(0, new_y_velocity, 0))
```

**Why This Works**:
- RevoluteJoint constraints prevent X/Z translation
- Y-axis velocity is interpreted as rotational input by PhysX
- Distance from controller to grab point affects rotation speed

**Use Case**: Handle_Dril with `custom:disable_drive=True` - allows grabbing edge of triangular handle and pulling up/down to rotate

**Setup Requirements**:
1. RevoluteJoint with Y-axis rotation
2. Add `custom:disable_drive` attribute = True to RevoluteJoint prim
3. Grab handle edge in VR
4. Move controller up/down (Y direction)

#### Mode 3: Velocity-Based Control (Normal Objects)

**When**: No RevoluteJoint OR no joint constraints

**Behavior**:
- Calculates 3D displacement vector
- Sets linear velocity in all axes
- 100x velocity multiplier for responsiveness
- Max velocity: 500 m/s

**Use Case**: Free-moving objects without joint constraints

#### Control Mode Flags

**`has_joint_constraint`**: Set to True when:
- RevoluteJoint is detected
- `custom:disable_drive = True` attribute exists

**Purpose**: Routes to Y-axis velocity control instead of angle-based control

**Detection Flow** (source/extensions/vr_ui/vr_ui/extension.py:1274-1280):
```python
disable_drive_attr = stage_prim.GetAttribute("custom:disable_drive")
if disable_drive_attr and disable_drive_attr.Get() == True:
    print(f"[VR Test UI] custom:disable_drive=True → Y軸速度制御を使用します")
    grab_data['has_joint_constraint'] = True  # Flag set here
    break  # Don't set grabbed_joint_path
```

#### Debugging Control Modes

Log output shows which mode is active:
```
[VR Test UI] [right] 制御方式: 角度ベース制御（DriveAPI targetPosition）
[VR Test UI] [right] 制御方式: Y軸速度制御（RevoluteJoint制約用）
[VR Test UI] [right] 制御方式: 速度ベース制御（通常オブジェクト用）
```

### Future Enhancements
- Adjustable force strength via UI slider
- Bi-manual interaction (both hands grab simultaneously)
- Grip button for additional interaction modes
- Distance-based force scaling
- Audio feedback on grab/release

### Advanced: Angle-Based Control for RevoluteJoint Objects (Mode 1 Details)

#### Overview
The VR UI extension implements a sophisticated **angle-based control system** for RevoluteJoint-connected handles, enabling intuitive rotation by tracking the controller's circular motion around the joint axis.

#### Why Angle-Based Control?
The original force-based approach had critical issues:
- **Y-axis rotation handles**: Barely moved despite controller input
- **X-axis rotation handles**: Rotation direction randomly reversed during interaction
- **Root cause**: Force-to-torque conversion produced unstable torque vectors that didn't align with joint axes

#### Angle-Based Control Algorithm

**Step 1: Determine Rotation Plane**
The rotation plane is automatically determined as **perpendicular to the RevoluteJoint axis**:
```python
# Joint軸に垂直な平面に投影
vec = controller_position - joint_center
projection_along_axis = vec.GetDot(axis)
vec_projected = vec - axis * projection_along_axis  # Remove axis component
```

**Step 2: Create 2D Coordinate System**
Two orthogonal basis vectors are constructed in the rotation plane:
```python
# basis1: Perpendicular to axis (X or Y depending on axis)
basis1 = (1, 0, 0) if abs(axis[0]) < 0.9 else (0, 1, 0)
basis1 = (basis1 - axis * basis1.Dot(axis)).Normalized()

# basis2: axis × basis1 (right-hand rule)
basis2 = axis.Cross(basis1).Normalized()
```

**Step 3: Calculate Angle with atan2**
Project controller position onto the 2D plane and compute angle:
```python
x = vec_projected.Dot(basis1)
y = vec_projected.Dot(basis2)
angle = math.atan2(y, x)  # Returns -π to +π
```

**Step 4: Compute Rotation Amount**
Calculate angle difference and normalize for shortest path:
```python
angle_delta = current_angle - initial_angle

# Normalize to -π ~ +π (shortest rotation)
if angle_delta > math.pi:
    angle_delta -= 2 * math.pi
elif angle_delta < -math.pi:
    angle_delta += 2 * math.pi
```

**Step 5: Convert to Angular Velocity**
Apply gain and damping, then set angular velocity:
```python
target_angular_velocity = angle_delta * angular_velocity_gain  # Default gain: 5.0

# Apply damping
damping_factor = 1.0 - grab_damping  # grab_damping = 0.2
final_velocity = target_angular_velocity * 0.2 + current_velocity * 0.8

# Clamp to max velocity (20 rad/s ≈ 1146°/s)
final_velocity = clamp(final_velocity, -20.0, 20.0)

# Set angular velocity along joint axis
rb_api.GetAngularVelocityAttr().Set(joint_axis * final_velocity)
```

#### Key Parameters

| Parameter | Default | Location | Effect |
|-----------|---------|----------|--------|
| `_angular_velocity_gain` | 5.0 | Line 138 | Higher = more sensitive rotation |
| `_grab_damping` | 0.2 | Line 125 | Higher = smoother but slower response |
| `max_angular_vel` | 20.0 rad/s | Line 1404 | Maximum rotation speed limit |

**Gain Formula**: `target_velocity (rad/s) = angle_delta (rad) × gain`

**Example**:
- Controller rotates 30° (0.52 rad) around handle
- With gain 5.0: target velocity = 0.52 × 5.0 = 2.6 rad/s (149°/s)
- With damping 0.2: actual velocity blends 20% target + 80% current

#### Rotation Direction Handling
The system automatically handles rotation direction:
- **atan2** returns signed angles (-180° to +180°)
- **Positive angle_delta** → Counter-clockwise rotation
- **Negative angle_delta** → Clockwise rotation
- **±180° boundary** → Normalized to shortest path

#### Implementation Details

**Initialization** (when object is grabbed):
```python
# Store joint center and initial angle
self._joint_center = object_center  # Handle's world position
self._initial_angle = _calculate_angle_around_axis(
    hit_position,      # Where controller grabbed
    self._joint_center,
    self._joint_axis
)
```

**Update Loop** (every frame while holding):
```python
current_angle = _calculate_angle_around_axis(
    controller_position,  # Current controller pos
    self._joint_center,
    self._joint_axis
)
angle_delta = normalize_angle(current_angle - self._initial_angle)
apply_angular_velocity(angle_delta * gain)
```

#### Debugging
The extension outputs debug information for the first 5 frames:
```
[VR Test UI] [debug translate] Controller Position: X=50.0662, Y=97.1417, Z=-114.7307
[VR Test UI] 初期角度: -13.5°
[VR Test UI] 現在角度: 45.0°
[VR Test UI] 角度差: 58.5°
[VR Test UI] 目標角速度: 2.93 rad/s
```

#### Advantages Over Force-Based Method
1. **Axis-independent**: Works equally well for X, Y, Z rotation axes
2. **Direction stable**: No random reversals - rotation follows controller motion
3. **Intuitive**: Circular controller motion = handle rotation
4. **Predictable**: Direct angle-to-velocity mapping

#### Critical: Parent Transform Coordinate System

**⚠️ IMPORTANT**: RevoluteJoint axis definitions are in **local coordinates** but require conversion to **world coordinates** for VR controller angle calculations.

**Problem Discovered**:
- Joint axis from USD (e.g., Y-axis) may not match world coordinate axis due to parent transform hierarchy
- `handle_right`: Joint defined as Y-axis, but rotates around X-axis in world space
- `handle_front`: Joint defined as X-axis, but rotates around Z-axis in world space

**Root Cause**: Parent prim has 90-degree rotation transformation that affects child joint axes

**Solution Implemented** (lines 1111-1127 in vr_ui/extension.py):
```python
# Fixed coordinate transformation: X→Z, Y→X, Z→Y
if axis_str.upper() == "X":
    self._joint_axis = Gf.Vec3d(0, 0, 1)  # X軸 → Z軸
elif axis_str.upper() == "Y":
    self._joint_axis = Gf.Vec3d(1, 0, 0)  # Y軸 → X軸
elif axis_str.upper() == "Z":
    self._joint_axis = Gf.Vec3d(0, 1, 0)  # Z軸 → Y軸
```

**Why Not Use Matrix Transformation?**: `ComputeLocalToWorldTransform()` on the Joint prim did not correctly propagate parent rotations. The hardcoded mapping above reflects the specific parent coordinate system in this project.

**Debug Verification**:
- Compare Joint axis definition with actual rotation behavior in viewport
- Check debug output: `[VR Test UI] Joint軸（ローカル、変換前）` vs `Joint軸（ワールド、変換後）`
- Verify angle calculation plane matches expected rotation (X-axis → Y-Z plane, etc.)

#### Angular Velocity Application

**Critical**: Use `omni.physx.get_physx_simulation_interface().set_rigidbody_angular_velocity()` instead of `RigidBodyAPI.GetAngularVelocityAttr().Set()`

**Reason**: USD attribute setting does not immediately affect PhysX simulation state. Direct PhysX API calls provide real-time angular velocity control.

**Implementation** (lines 1442-1475):
```python
import omni.physx
physx_interface = omni.physx.get_physx_simulation_interface()
physx_interface.set_rigidbody_angular_velocity(prim_path, carb.Float3(...))
```

#### Common Issues

**Issue**: Handle rotates in opposite direction
**Cause**: Basis vector handedness mismatch with joint axis
**Solution**: System uses right-hand rule consistently; verify joint axis direction

**Issue**: Handle barely rotates despite controller motion
**Cause**: Gain too low or controller moving along axis (not around it)
**Solution**: Increase `_angular_velocity_gain` or move controller in circular path around handle

**Issue**: Rotation overshoots/oscillates
**Cause**: Gain too high or damping too low
**Solution**: Decrease gain (try 3.0) or increase damping (try 0.4)

**Issue**: Joint axis doesn't match actual rotation
**Cause**: Parent transform hierarchy affects local-to-world conversion
**Solution**: Verify coordinate transformation mapping (X→Z, Y→X, Z→Y) matches your scene hierarchy. Use debug output to compare Joint definition vs world behavior.

## PhysX Joint Driveトラブルシューティング

### 重要：DriveAPIパラメータが効果を発揮しない

**問題**: Property UIで`stiffness`、`damping`、`targetPosition`、または`targetVelocity`を調整してもJointの動作に影響がない。

**根本原因と解決策**：

#### 1. Drive Type属性の欠落
`drive:angular:physics:type`または`drive:linear:physics:type`を明示的に`"force"`または`"acceleration"`に設定する必要があります。

**解決策**（Property UI）：
- Joint選択 → Raw USD Properties
- `drive:angular:physics:type` = `"force"`（または`"acceleration"`）を追加/設定

**解決策**（Python）：
```python
drive = UsdPhysics.DriveAPI.Apply(joint_prim, "angular")  # または "linear"
drive.CreateTypeAttr("force")  # 必須 - これがないとドライブは機能しない
```

#### 2. maxForceが不十分
ドライブ力は重力やその他の力を克服する必要があります。デフォルトまたは小さい値（< 10000）は通常不十分です。

**推奨値**：
- RevoluteJoint（ハンドル）: `maxForce = 50000 - 100000`
- PrismaticJoint（垂直移動）: `maxForce = 50000+`

#### 3. Articulation vs 通常Jointの混同
**警告**: `Joint friction attribute is only applied for joints in articulations`

- **Joint Friction**はArticulation階層（ロボットアームなど）内でのみ機能
- **通常のJoint**は`physxJoint:jointFriction`属性を無視
- **解決策**: 摩擦属性を削除するか、`UsdPhysics.ArticulationRootAPI.Apply(root_prim)`を使用してArticulationに変換

#### 4. 分離したボディトランスフォーム
**警告**: `PhysicsUSD: CreateJoint - found a joint with disjointed body transforms`

**意味**: Body0とBody1が離れすぎており、シミュレーションの不安定性とオブジェクトのスナップを引き起こす。

**解決策**:
- Body0とBody1を近づける（< 1ユニット離れた位置）
- `physics:localPos0`と`physics:localPos1`を設定してジョイント接続点を整列
- Physics Debug Visualizationを使用してジョイントフレーム位置を確認

#### 5. 重力抵抗のためのドライブパラメータ範囲

シミュレーション開始時にオブジェクトが重力で垂れ下がるのを防ぐために：

**RevoluteJoint（ドリルを制御するハンドル）**：
```python
drive.CreateStiffnessAttr(50000.0)   # 重力トルクに抵抗するのに十分な高さ
drive.CreateDampingAttr(5000.0)      # 剛性の約10%
drive.CreateTargetPositionAttr(0.0)  # 初期位置に戻る
drive.CreateMaxForceAttr(100000.0)   # 重力によるトルクを超える必要がある
```

**PrismaticJoint（垂直ドリル移動）**：
```python
drive.CreateStiffnessAttr(100000.0)  # ドリルの重量に抵抗
drive.CreateDampingAttr(10000.0)
drive.CreateTargetPositionAttr(0.0)  # 初期高さ
drive.CreateMaxForceAttr(50000.0)    # 重量 × 重力を超える
```

### Joint Driveセットアップのための Property UIワークフロー

1. **Joint primを選択** Stage階層で
2. **Raw USD Propertiesを有効化**: ⚙️ Settings → `Show Raw USD Properties`
3. **Drive属性を確認/追加**：
   - `drive:angular:physics:type`（RevoluteJoint）または`drive:linear:physics:type`（PrismaticJoint）
   - `drive:*:physics:stiffness`
   - `drive:*:physics:damping`
   - `drive:*:physics:maxForce`
   - `drive:*:physics:targetPosition`
4. **テスト**: シミュレーションを停止して再起動（Play → Stop → Play）

### VR UI角度計算 (vr_ui拡張機能)

RevoluteJoint操作のためのVRコントローラー角度計算は、joint_centerではなく**grab_point_worldを回転中心として**使用します。これにより、ユーザーがハンドルを掴んだ場所に基づいた、より直感的な制御を提供します。

**実装** (`vr_ui/extension.py` 1165-1233行)：
```python
def _calculate_angle_around_axis(self, point, center, axis):
    # centerパラメータはgrab_point_world（ユーザーが掴んだ場所）
    # joint_center（ハンドルのピボットポイント）ではない
    vec = point - center  # 掴んだ点からコントローラーへのベクトル
```

**主要な場所**：
- 初期角度計算（1138行）: `grab_point_world`を中心として使用
- 現在の角度計算（1405行）: `grab_point_world`を中心として使用
- ハンドル中心ではなく、ユーザーの手の位置に相対的な回転を提供

## Item Setting Extension (item_setting)

### Overview
The `item_setting` extension provides **Update Loop-based PhysX Trigger detection** for automatic item placement and validation. Unlike `item_placement_system` which uses script callbacks, this extension polls trigger states every frame using PhysX Scene Query.

### Architecture

**Location**: `source/extensions/item_setting/item_setting/extension.py`

**Detection Method**: PhysX Scene Query `overlap_sphere()` instead of PhysxTriggerStateAPI
- Reason: PhysxTriggerStateAPI requires script callbacks; Update Loop polling needs Scene Query
- `overlap_sphere()` detects all RigidBody objects within trigger bounds
- Detects **both Dynamic and Kinematic** RigidBody objects

### Core Components

#### TriggerSlot Configuration
```python
@dataclass
class TriggerSlot:
    slot_id: str                    # Unique identifier
    trigger_path: str               # USD path to trigger prim
    correct_number: int             # Expected custom:Number value
    placement_translate: Tuple[float, float, float]
    placement_rotate: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    proxy: bool = False             # Use proxy/real object system
    real_path: str = ""             # Path to real object (if proxy=True)
    task: bool = False              # Whether task completion required
    task_path: str = ""             # Optional task script path
    display_name: str = ""          # UI display name
```

#### Detection Flow (Update Loop)

1. **Trigger Setup** (`_setup_triggers()`):
   - Apply CollisionAPI to trigger prims
   - Apply PhysxTriggerAPI (but clear script paths)
   - Apply PhysxTriggerStateAPI for compatibility

2. **Frame-by-Frame Detection** (`_on_update()`):
   - Get trigger center and bounding box
   - Call `overlap_sphere(radius * 1.2, trigger_center, report_hit)`
   - Collect RigidBody paths from hits
   - Compare with previous frame to detect **new entries**
   - Call `handle_trigger_entry()` for new objects

3. **Object Validation**:
   - Extract `custom:Number` attribute from detected object
   - Compare with `TriggerSlot.correct_number`
   - Route to appropriate placement method

### Placement Methods

#### 1. Normal Placement (`_place_item_normal`)
For objects with `proxy=False`:

**Actions**:
- Set parent's `rigidBodyEnabled = False` (completely disable physics)
- Set position/rotation via XformOps
- Set `custom:placed = True` on object
- Set `custom:task` based on slot configuration

**Critical**: Uses `rigidBodyEnabled` NOT `kinematicEnabled`

#### 2. Proxy System Placement (`_place_item_with_proxy`)
For objects with `proxy=True` (e.g., VoxelMesh that cannot have RigidBody):

**Actions on Proxy**:
- Set parent's `rigidBodyEnabled = False`
- Make proxy invisible
- Disable proxy collision
- Save `custom:real_path` attribute (for cleanup)
- Set `custom:placed = True` (for cleanup detection)

**Actions on Real Object**:
- Make real object visible
- Enable real object collision
- Set `custom:placed = True`
- Set `custom:task` based on slot

**Critical**: Both proxy AND real object must have `custom:placed = True`

#### 3. Incorrect Number Reset (`_reset_item_to_original`)
When `custom:Number` doesn't match:

**Actions**:
- Set parent's `rigidBodyEnabled = False`
- Read `custom:original_position` attribute
- Reset position to original
- Object remains disabled

### Simulation Stop Cleanup (`_cleanup_on_simulation_stop`)

**Timeline Event**: Listens for `TimelineEventType.STOP`

**For Normal Objects** (`proxy=False`):
- Set `rigidBodyEnabled = True` (re-enable physics)

**For Proxy System** (`proxy=True`):
- **Proxy Object**:
  - Make visible
  - Enable collision
  - Set parent's `rigidBodyEnabled = True`
  - Set `custom:placed = False`
- **Real Object** (found via `custom:real_path`):
  - Make invisible
  - Disable collision
  - Set `custom:placed = False`
  - Set `custom:task = False`

### Critical Implementation Details

#### RigidBody Disable Pattern
```python
# CORRECT - Completely disable RigidBody
rb_api = UsdPhysics.RigidBodyAPI(parent_prim)
rb_enabled_attr = rb_api.GetRigidBodyEnabledAttr()
if not rb_enabled_attr:
    rb_enabled_attr = rb_api.CreateRigidBodyEnabledAttr()
rb_enabled_attr.Set(False)  # Object becomes static, no physics

# WRONG - Don't use kinematicEnabled
# kinematicEnabled keeps RigidBody active but ignores forces
```

#### Overlap Sphere Detection
```python
detected_hits = []

def report_hit(hit):
    detected_hits.append(hit)
    return True  # Continue searching

hit_count = scene_query.overlap_sphere(
    float(radius * 1.2),  # radius
    carb.Float3(float(x), float(y), float(z)),  # center
    report_hit  # callback
)

# Extract RigidBody paths (usually parent Xform)
for hit in detected_hits:
    if hasattr(hit, 'rigid_body') and hit.rigid_body:
        collider_path = hit.rigid_body
        # Search for Mesh children with custom:Number
```

#### Hierarchy Pattern
```
Xform (RigidBodyAPI)          <- Detected by overlap_sphere
└── Mesh (CollisionAPI)       <- Has custom:Number attribute
```

### VR Detachment Integration

**Challenge**: Proxy system real objects (e.g., VoxelMesh) have NO RigidBodyAPI
- VR raycast/overlap only detects RigidBody objects
- Real objects are invisible to VR detection

**Solution Required**: VR UI must implement special detection for proxy system:
1. Detect real object by other means (spatial query, custom attribute scan)
2. Check `custom:placed = True` AND `custom:task = True`
3. Call `item_setting` extension's detachment method
4. Or implement manual cleanup: hide real, show proxy, reset positions

**Not Currently Implemented**: VR detachment for proxy system objects

### Common Issues

#### Issue: "proxyシステム0個を復元"
**Cause**: Proxy object missing `custom:placed = True`
**Solution**: Ensure `_place_item_with_proxy()` sets placed attribute on BOTH proxy and real objects

#### Issue: Objects fall through floor after placement
**Cause**: Using `kinematicEnabled` instead of `rigidBodyEnabled`
**Solution**: Use `rigidBodyEnabled = False` to completely disable physics

#### Issue: Cleanup doesn't find real object
**Cause**: Missing `custom:real_path` attribute on proxy object
**Solution**: Ensure `_place_item_with_proxy()` saves real_path before completion

#### Issue: Trigger not detecting objects
**Cause**: Object RigidBody too far from trigger center
**Solution**: Increase overlap_sphere radius multiplier (e.g., `radius * 1.5`)

### Comparison: item_setting vs item_placement_system

| Feature | item_setting | item_placement_system |
|---------|--------------|----------------------|
| Detection Method | Update Loop + overlap_sphere | PhysX Script Callbacks |
| Performance | Polls every frame (higher overhead) | Event-driven (efficient) |
| Complexity | Simpler architecture | Complex state machine |
| Task System | Boolean flag only | Plugin-based task scripts |
| VR Integration | Not implemented | Full detachment support |
| Coordinate Transform | Direct XformOp setting | Transform calculation to avoid reparenting |
| USD Mutex Safety | Safe (no reparenting) | Requires coordinate math to avoid crash |

**Recommendation**: Use `item_placement_system` for production; `item_setting` for simpler use cases or debugging.

# 重要な指示リマインダー
要求されたことを実行する；それ以上でも以下でもない。
目的達成に絶対に必要な場合を除き、ファイルを作成しない。
常に新しいファイルを作成するよりも、既存のファイルを編集することを優先する。
ドキュメントファイル（*.md）やREADMEファイルを積極的に作成しない。ユーザーから明示的に要求された場合にのみドキュメントファイルを作成する。