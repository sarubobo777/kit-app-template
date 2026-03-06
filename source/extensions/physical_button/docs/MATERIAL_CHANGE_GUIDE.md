# マテリアル変更の仕組み - 詳細解説

## 概要

Physical Button Systemでは、ボタンが押されたときにボタンの見た目を変更するために、**既存のマテリアルのシェーダーパラメータを直接変更する**方法を採用しています。

## マテリアル変更の実装方法

### 1. USD（Universal Scene Description）とマテリアルの構造

Omniverseのシーン内の全てのオブジェクトはUSDで記述されており、以下のような階層構造を持っています：

```
/World/New_MillingMachine/Main/Switch2  (ボタンオブジェクト)
  └─ __________001  (メッシュ)
       └─ [Material Binding] → /World/New_MillingMachine/_materials/________________004
```

マテリアル自体も階層構造を持ち、通常以下のような構成になっています：

```
/World/New_MillingMachine/_materials/________________004  (Material)
  └─ Shader  (Shader Prim)
       ├─ emissiveColor: (0.0, 0.0, 0.0)  ← 発光色
       ├─ diffuseColor: (0.5, 0.5, 0.5)   ← 基本色
       ├─ roughness: 0.5                   ← 表面の粗さ
       ├─ metallic: 0.0                    ← 金属性
       └─ その他のパラメータ...
```

### 2. マテリアル変更の手順

#### ステップ1: メッシュの検索

ボタンPrim（`/World/New_MillingMachine/Main/Switch2`）の階層内からメッシュを探します。

```python
def _find_mesh_in_prim(self, prim):
    """Prim階層内からメッシュを検索"""
    # 自分自身がメッシュかチェック
    if prim.IsA(UsdGeom.Mesh):
        return prim

    # 子要素を再帰的に探索
    for child in prim.GetChildren():
        mesh = self._find_mesh_in_prim(child)
        if mesh:
            return mesh

    return None
```

**結果**: `/World/New_MillingMachine/Main/Switch2/__________001` というメッシュが見つかります。

#### ステップ2: バインドされているマテリアルの取得

メッシュにバインド（関連付け）されているマテリアルを取得します。

```python
# MaterialBindingAPIを使ってバインディング情報を取得
binding_api = UsdShade.MaterialBindingAPI(mesh_prim)
bound_material, _ = binding_api.ComputeBoundMaterial()
```

**ComputeBoundMaterial()の役割**:
- メッシュに直接バインドされているマテリアルを探す
- 見つからない場合は親階層を遡ってマテリアルを探す
- マテリアルのPrimを返す

**結果**: `/World/New_MillingMachine/_materials/________________004` というマテリアルPrimが取得されます。

#### ステップ3: シェーダーの取得

マテリアルPrimの子要素からShaderを探します。

```python
material_prim = bound_material.GetPrim()

# マテリアル内のシェーダーを探す
shader = None
for prim in material_prim.GetChildren():
    if prim.IsA(UsdShade.Shader):
        shader = UsdShade.Shader(prim)
        break
```

**Shaderとは**:
- USDPreviewSurface、OmniPBR、OmniGlassなどのシェーダータイプ
- 実際の色、光沢、発光などのパラメータを持つ
- レンダラー（RTX）がこのパラメータを読み取って描画

#### ステップ4: シェーダーパラメータの変更

シェーダーの各パラメータ（Input）を取得して値を変更します。

```python
# emissiveColor（発光色）の取得と変更
emissive_input = shader.GetInput("emissiveColor")
if not emissive_input:
    # 存在しない場合は新規作成
    emissive_input = shader.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f)

# 元の値を保存（初回のみ）
if not hasattr(self, 'original_emissive'):
    self.original_emissive = emissive_input.Get()

# 新しい値を設定
if self.button_type == "start":
    emissive_color = Gf.Vec3f(0.0, 100.0, 0.0)  # 緑色、強度100
else:
    emissive_color = Gf.Vec3f(50.0, 0.0, 0.0)   # 赤色、強度50

emissive_input.Set(emissive_color)
```

### 3. 変更するパラメータの詳細

#### emissiveColor（発光色）

**役割**: オブジェクト自体が発する光の色と強度

**値の範囲**:
- RGB値（Gf.Vec3f）: (R, G, B)
- 通常は0.0〜1.0だが、1.0を超えると非常に明るく発光
- HDR（ハイダイナミックレンジ）レンダリングでは高い値が使用可能

**STARTボタン**: `(0.0, 100.0, 0.0)`
- R=0.0（赤なし）
- G=100.0（緑を非常に強く発光）
- B=0.0（青なし）
- 結果: 非常に明るい緑色に光る

**STOPボタン**: `(50.0, 0.0, 0.0)`
- R=50.0（赤を強く発光）
- G=0.0（緑なし）
- B=0.0（青なし）
- 結果: 明るい赤色に光る

#### diffuseColor（基本色）

**役割**: オブジェクト表面の基本的な色（反射光の色）

**値の範囲**: RGB値（Gf.Vec3f）、通常は0.0〜1.0

**押下時の設定**:
- STARTボタン: `(0.0, 1.0, 0.0)` → 緑色
- STOPボタン: `(1.0, 0.0, 0.0)` → 赤色

**効果**: emissiveColorと組み合わせることで、より鮮やかな色になる

#### roughness（表面の粗さ）

**役割**: 表面の滑らかさ（光沢）を制御

**値の範囲**: 0.0〜1.0
- 0.0: 完全に滑らか（鏡面反射）
- 1.0: 非常に粗い（マット）

**押下時の設定**: `0.1` → 光沢を出して反射を強調

**効果**: 光沢が出ることで発光色がより目立つ

### 4. 元に戻す処理

ボタンが離されたときは、保存しておいた元の値に戻します。

```python
def _remove_pressed_visual(self, stage):
    # ... メッシュとシェーダーを取得 ...

    # emissiveColorを元に戻す
    emissive_input = shader.GetInput("emissiveColor")
    if emissive_input and hasattr(self, 'original_emissive'):
        emissive_input.Set(self.original_emissive)

    # diffuseColorを元に戻す
    diffuse_input = shader.GetInput("diffuseColor")
    if diffuse_input and hasattr(self, 'original_diffuse'):
        diffuse_input.Set(self.original_diffuse)

    # roughnessを元に戻す
    roughness_input = shader.GetInput("roughness")
    if roughness_input and hasattr(self, 'original_roughness'):
        roughness_input.Set(self.original_roughness)
```

**重要**: 元の値は初回押下時に`original_emissive`、`original_diffuse`、`original_roughness`として保存されます。

## なぜこの方法を採用したか

### 他の方法との比較

#### 方法1: 新しいマテリアルを作成してバインドを変更（不採用）

```python
# 新しいマテリアルを作成
new_material = UsdShade.Material.Define(stage, "/World/Materials/pressed_material")
# メッシュにバインド
UsdShade.MaterialBindingAPI(mesh_prim).Bind(new_material)
```

**問題点**:
- レンダラーがマテリアル変更を即座に反映しないことがある
- 元のマテリアルの設定（テクスチャなど）が失われる
- マテリアルオブジェクトが増える

#### 方法2: 既存のマテリアルのパラメータを変更（採用）

```python
# 既存のシェーダーのパラメータだけを変更
emissive_input.Set(new_color)
```

**利点**:
- レンダラーがパラメータ変更を即座に検知・反映
- 元のマテリアル設定を保持
- マテリアルオブジェクトを増やさない
- 元に戻すのが簡単（値を保存しておくだけ）

### RTXレンダラーとの連携

NVIDIA RTXレンダラーは、シェーダーパラメータの変更を監視しており、値が変わると自動的に再レンダリングします。

**リアルタイム反映の流れ**:
1. `emissive_input.Set(new_color)` を実行
2. USDステージが変更通知を発行
3. RTXレンダラーが変更を検知
4. 該当オブジェクトを再レンダリング
5. ビューポートに反映

## START/STOPボタンの視覚的違い

### STARTボタン（緑色）

- **emissiveColor**: `(0.0, 100.0, 0.0)` - 非常に強い発光
- **diffuseColor**: `(0.0, 1.0, 0.0)` - 明るい緑
- **roughness**: `0.1` - 光沢
- **視覚効果**: 非常に明るく鮮やかな緑色に発光し、周囲も緑色に照らす

### STOPボタン（赤色）

- **emissiveColor**: `(50.0, 0.0, 0.0)` - 強い発光（STARTより控えめ）
- **diffuseColor**: `(1.0, 0.0, 0.0)` - 明るい赤
- **roughness**: `0.1` - 光沢
- **視覚効果**: 明るい赤色に発光し、周囲も赤色に照らす

**STARTボタンを特に明るくした理由**:
- emissiveColorの強度を100にすることで、緑色でも十分目立つようにする
- 緑色は人間の目に赤色より暗く見えやすいため、より強い発光が必要
- STOPボタンは警告色（赤）なので、強度50でも十分目立つ

## トラブルシューティング

### 変化が見えない場合

1. **RTXレンダリングが有効か確認**
   - レンダリング設定でRTX-Realtimeが有効になっているか

2. **emissiveColorの強度を上げる**
   - 環境光が強い場合、発光が見えにくいことがある
   - 強度を200、300と上げてみる

3. **diffuseColorも変更する**
   - emissiveColorだけでなく、diffuseColorも変えることで確実に色が変わる

4. **デバッグログを確認**
   - `✓ emissiveColor設定完了` などのログが出ているか確認
   - シェーダーが正しく取得できているか確認

### 元に戻らない場合

- `original_emissive`などが正しく保存されているか確認
- 初回押下時にログで元の値が出力されているか確認

## コードの全体像

```python
class PhysicalButton:
    def _apply_pressed_visual(self, stage):
        # 1. メッシュを探す
        mesh_prim = self._find_mesh_in_prim(self.button_prim)

        # 2. バインドされているマテリアルを取得
        binding_api = UsdShade.MaterialBindingAPI(mesh_prim)
        bound_material, _ = binding_api.ComputeBoundMaterial()

        # 3. シェーダーを取得
        material_prim = bound_material.GetPrim()
        shader = None
        for prim in material_prim.GetChildren():
            if prim.IsA(UsdShade.Shader):
                shader = UsdShade.Shader(prim)
                break

        # 4. emissiveColorを変更
        emissive_input = shader.GetInput("emissiveColor")
        if not hasattr(self, 'original_emissive'):
            self.original_emissive = emissive_input.Get()
        emissive_input.Set(Gf.Vec3f(0.0, 100.0, 0.0))  # 緑色発光

        # 5. diffuseColorを変更
        diffuse_input = shader.GetInput("diffuseColor")
        if not hasattr(self, 'original_diffuse'):
            self.original_diffuse = diffuse_input.Get()
        diffuse_input.Set(Gf.Vec3f(0.0, 1.0, 0.0))  # 緑色

        # 6. roughnessを変更
        roughness_input = shader.GetInput("roughness")
        if not hasattr(self, 'original_roughness'):
            self.original_roughness = roughness_input.Get()
        roughness_input.Set(0.1)  # 光沢
```

## まとめ

Physical Button Systemのマテリアル変更は：

1. **メッシュの検索** → ボタンオブジェクト内のメッシュを再帰的に探索
2. **マテリアル取得** → MaterialBindingAPIでバインドされたマテリアルを取得
3. **シェーダー取得** → マテリアル内のShaderPrimを探索
4. **パラメータ変更** → emissiveColor、diffuseColor、roughnessを変更
5. **元に戻す** → 保存しておいた元の値に戻す

という流れで実装されています。この方法により、**リアルタイムで確実に視覚的フィードバックを提供**できます。
