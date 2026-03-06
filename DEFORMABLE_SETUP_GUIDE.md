# Deformable Bodies (Beta) セットアップガイド

CableにDeformable Bodies (Beta)を適用するための完全ガイド

## 問題の原因

1. **Physics Beta機能が実際には無効** - UIのチェックボックスがオンでも内部設定は無効
2. **メッシュがTriangle Meshではない** - Quad mesh (4頂点/面) はDeformable Bodiesに非対応
3. **Deprecated版APIが適用されていた** - 古いTetmesh方式を使用していた

## 解決方法: 2つのオプション

### オプション1: 自動スクリプト (推奨)

**すべてのステップを自動実行:**

```python
# Script Editorで実行:
exec(open('apply_deformable_complete_guide.py').read())
```

このスクリプトは以下を自動で行います:
- 前提条件チェック
- Beta機能確認
- 既存Deformable設定削除
- メッシュTriangle化
- Surface Deformable適用

**注意:** Beta機能が無効の場合、先に`enable_beta_physics.py`を実行してアプリ再起動が必要です。

### オプション2: 手動実行 (ステップバイステップ)

#### ステップ1: Beta機能を有効化

```python
# Script Editorで実行:
exec(open('enable_beta_physics.py').read())
```

**実行後:**
- アプリケーションを再起動
- 設定が永続化されます

#### ステップ2: 既存設定を削除

```python
# Script Editorで実行:
exec(open('remove_deformable_from_cable.py').read())
```

**結果:**
- PhysxDeformableBodyAPI削除
- RigidBodyAPI削除 (存在する場合)
- Deformable Material削除

#### ステップ3: メッシュをTriangle化

```python
# Script Editorで実行:
exec(open('triangulate_cable_mesh.py').read())
```

**結果:**
- Quad面 → 2つのTriangle面に分割
- N角形面 → Fan triangulation
- 頂点座標は変更なし

#### ステップ4: Surface Deformableを適用

```python
# Script Editorで実行:
exec(open('apply_deformable_surface.py').read())
```

**結果:**
- PhysxDeformableBodyAPI適用
- SimulationMeshResolution = 0 (Triangle Mesh使用、Tetmesh変換なし)
- CollisionAPI適用
- Deformable Material作成とバインド

#### ステップ5: Stageを保存

- `Ctrl+S` または `File > Save`
- USDファイルに変更を保存

#### ステップ6: シミュレーション実行

- **Playボタン**を押す
- Cableが柔軟に動くか確認

## パラメータ調整

Surface Deformable Materialの設定:

**場所:** `/World/New_MillingMachine/Pulag/Cable/.../SurfaceDeformableMaterial`

### Young's Modulus (剛性)
- **デフォルト:** 5e6
- **柔らかくする:** 1e6 ~ 3e6
- **硬くする:** 7e6 ~ 1e7

### Poisson's Ratio (体積保存)
- **デフォルト:** 0.4
- **範囲:** 0.0 ~ 0.49 (0.5は非圧縮)

### Dynamic Friction (摩擦)
- **デフォルト:** 0.6
- **範囲:** 0.0 ~ 1.0

### Damping (減衰)
- **デフォルト:** 0.15
- **早く静止させる:** 0.3 ~ 0.5
- **より弾性的にする:** 0.05 ~ 0.1

## よくある問題と解決

### Q: UIでVolume/Surfaceがグレーアウトしている
**A:** Beta機能が実際には無効です。`enable_beta_physics.py`を実行してアプリ再起動。

### Q: Tetmesh cooking エラーが出る
**A:** メッシュがTriangle化されていない、またはSimulationMeshResolutionが正しく設定されていません。

### Q: Cableが動かない
**A:**
1. 重力が有効か確認 (Physics Scene設定)
2. Materialパラメータを調整 (Young's Modulusを下げる)
3. Cableが他のオブジェクトに固定されていないか確認

### Q: Cableが床を貫通する
**A:**
1. CollisionAPIが正しく適用されているか確認
2. 床にもCollisionAPIが必要
3. Physics Sceneの衝突設定を確認

### Q: Cableの端を固定したい
**A:** PhysxDeformableAttachmentAPIを使用してRigidBodyに固定

## スクリプトファイル一覧

- **enable_beta_physics.py** - Beta機能有効化
- **diagnose_deformable_version.py** - 状態診断ツール
- **remove_deformable_from_cable.py** - 既存設定削除
- **triangulate_cable_mesh.py** - メッシュTriangle化
- **apply_deformable_surface.py** - Surface Deformable適用
- **apply_deformable_complete_guide.py** - 全自動実行 (推奨)

## 技術詳細

### Surface Deformable vs Volume Deformable

**Surface Deformable (今回使用):**
- Triangle Mesh使用
- 薄いオブジェクト向け: ケーブル、布、紙
- Tetmesh変換なし

**Volume Deformable:**
- Tetrahedral/Hexahedral Mesh使用
- 厚みのあるオブジェクト向け: ゴム、肉、ゼリー
- Tetmesh自動生成が必要

### SimulationMeshResolution設定

- **0** = Triangle Meshをそのまま使用 (Surface Deformable)
- **1以上** = Tetmeshに変換 (Volume Deformable)

### なぜTriangle Meshが必要?

PhysX Deformable Bodies (Beta)のSurface Deformableモードは:
- Triangle面の辺をSpring-Mass Systemとして扱う
- Quad面は2つのTriangleに分解する必要がある
- 正確な物理シミュレーションのため

## 参考リンク

- [NVIDIA Omniverse Deformable Bodies Beta Documentation](https://docs.omniverse.nvidia.com/kit/docs/omni_physics/107.3/dev_guide/deformables_beta/deformable_authoring.html)
