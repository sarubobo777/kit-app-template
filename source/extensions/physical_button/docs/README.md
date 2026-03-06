# Physical Button System

物理ボタンシステム拡張機能 - PrismaticJointを使用したボタン押下検知と視覚的フィードバック

## 機能

- **物理ベースのボタン**: PrismaticJointを使用してX軸方向に0.07単位沈み込むと押下判定
- **視覚的フィードバック**: ボタンが押されると発光マテリアルで表示
  - STARTボタン: 緑色に発光
  - STOPボタン: 赤色に発光
- **他の拡張機能との連携**: ボタン押下時に他の拡張機能を開始/停止

## 使用方法

1. エクステンションを有効化
2. UIウィンドウで「ボタンシステムを初期化」をクリック
3. シミュレーションを開始（Playボタン）
4. Switch1/Switch2を物理的に押す

## ボタン設定

- **START Button**: `/World/New_MillingMachine/Main/Switch2`
  - 初期位置: (0, 0, 0)
  - 押下閾値: X軸方向 -0.07
  - 視覚効果: 緑色発光

- **STOP Button**: `/World/New_MillingMachine/Main/Switch1`
  - 初期位置: (0, 0, 0)
  - 押下閾値: X軸方向 -0.07
  - 視覚効果: 赤色発光

## カスタマイズ

`extension.py`の`_on_button_pressed()`メソッドで、ボタン押下時の処理をカスタマイズできます。

```python
def _on_button_pressed(self, button_type: str):
    if button_type == "start":
        # 開始処理をここに追加
        pass
    elif button_type == "stop":
        # 停止処理をここに追加
        pass
```
