# VR Test UI Extension

VRテスト用の拡張機能です。VR Experience（CloudXR/OpenXR）と組み合わせて使用します。

## 機能

### 1. テキスト表示テスト
- 英語テキスト: "Hello World"
- 日本語テキスト: "ハローワールド"
- 混在テキスト: "Hello World ハローワールド"

UIに正常に表示されることを確認します。

### 2. VRコントローラー入力表示
リアルタイムでコントローラーの入力状態を表示：
- **Left Controller**:
  - Trigger: トリガーボタンの押下状態
  - Grip: グリップボタンの押下状態
  - A Button: Aボタンの押下状態
  - B Button: Bボタンの押下状態
  - Position: コントローラーの3D位置 (x, y, z)

- **Right Controller**:
  - 同様の情報を表示

### 3. インタラクティブボタン
"Click Me / クリックしてください" ボタン
- クリックすると `Click OK` がコンソールに出力
- クリック回数をカウント表示

## 使用方法

### 1. 通常モード（VRなし）での動作確認

```bash
# アプリケーションを起動
.\repo.bat launch

# Extension Managerから「VR Test UI」を有効化
# Window → Extensions → Search "VR Test UI" → Enable
```

通常モードでは：
- UIウィンドウが表示されます
- テキスト表示は動作します
- ボタンクリックは動作します
- コントローラー入力は「XRCore Not Available」と表示されます

### 2. VRモードでの使用

```bash
# VR Experience拡張機能を有効化
# Extension Manager → Search "CloudXR" or "VR Experience" → Enable

# VR Test UIを有効化
# Extension Manager → Search "VR Test UI" → Enable

# VRヘッドセットを接続してアプリを起動
```

VRモードでは：
- UIがVRヘッドセット内に表示されます
- コントローラーの入力が検知され、リアルタイムで表示更新されます
- VRコントローラーでボタンをクリック可能

## 検証項目

### ✓ テキスト表示
- [ ] 英語が正しく表示される
- [ ] 日本語が正しく表示される
- [ ] 混在テキストが正しく表示される

### ✓ コントローラー入力
- [ ] XRCoreが正しく取得できる
- [ ] 左コントローラーの入力が検知される
- [ ] 右コントローラーの入力が検知される
- [ ] トリガー/グリップ/ボタンの状態がリアルタイム更新される
- [ ] 位置情報が表示される

### ✓ UI操作
- [ ] ボタンをクリックできる
- [ ] "Click OK"がコンソールに出力される
- [ ] クリック回数がカウントされる

## トラブルシューティング

### XRCoreが利用できない
**症状**: "XRCore Not Available (VR機能なし)" と表示される

**原因**:
- VR Experience拡張機能が有効化されていない
- `omni.kit.xr.core`が利用できない環境

**解決方法**:
1. Extension Managerで「CloudXR」または「VR Experience」を検索して有効化
2. アプリケーションを再起動

### コントローラー入力が反応しない
**原因**:
- VRヘッドセットが正しく接続されていない
- コントローラーがペアリングされていない

**解決方法**:
1. VRヘッドセットとコントローラーの接続を確認
2. SteamVRまたはOculus Softwareが起動しているか確認
3. コントローラーのバッテリーを確認

### 日本語が文字化けする
**原因**: フォントが日本語をサポートしていない

**解決方法**:
- Omniverseのフォント設定を確認
- UTF-8対応フォントを使用

## 開発者向け情報

### 依存関係
```toml
[dependencies]
"omni.kit.xr.core" = {}
"omni.ui" = {}
"omni.ui.scene" = {}
```

### 拡張機能の構造
```
source/extensions/vr_test_ui/
├── config/
│   └── extension.toml          # 拡張機能設定
├── vr_test_ui/
│   ├── __init__.py
│   └── extension.py            # メインコード
└── docs/
    └── README.md               # このファイル
```

### カスタマイズ方法

#### 新しいボタンを追加
```python
ui.Button("My Button", clicked_fn=self._my_callback)

def _my_callback(self):
    print("My button clicked!")
```

#### コントローラーイベントを追加
```python
def _on_update(self, e):
    controller = self._xr_core.get_controller_state(1)  # 右手

    if controller.x_button_pressed:
        print("X button pressed!")
```

## 次のステップ

このテスト拡張機能で基本動作を確認したら、以下の実装に進めます：

1. **3D空間UIの実装** - `omni.ui.scene`を使用してVR空間内にUIを配置
2. **ハプティックフィードバック** - コントローラーの振動
3. **視線追跡** - ユーザーが見ている方向の検知
4. **音声ガイド** - `omni.kit.audio`を使用した音声案内

## ライセンス

このプロジェクトの一部として同じライセンスが適用されます。
