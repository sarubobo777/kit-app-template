# Item Placement System Overview

## システム構成

### 主要コンポーネント

1. **ItemPlacementExtension**: メイン拡張機能クラス
2. **ItemPlacementManager**: アイテム設置の中核ロジック
3. **MachineStatus**: フライス盤状態管理
4. **PlacementSlot**: 個別スロット管理

### データフロー

```
アイテム移動検出
       ↓
位置ベース設置判定
       ↓
Number属性検証
       ↓
スロット適合性チェック
       ↓
物理固定・状態更新
       ↓
MachineStatus通知
```

## 設定項目

### 必須設定
- 各スロットの座標位置
- 許可アイテム番号リスト
- アイテム-ステータスマッピング
- テーブルアイテムパス

### オプション設定
- 検出範囲調整
- 力閾値設定
- UI更新間隔