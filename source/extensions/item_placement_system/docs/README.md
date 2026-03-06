# Item Placement System

フライス盤用のアイテム設置システム

## 概要

このシステムは、フライス盤シミュレーションにおけるアイテムの設置・管理を行います。

## 主な機能

- 4つの設置スロットでのアイテム管理
- アイテム番号（Number属性）による設置検証
- MachineStatusシステムとの連携
- 力による自動取り外し機能
- リアルタイムUI表示

## 設定が必要な項目

設置システムを使用する前に、以下の設定を行ってください：

### 1. machine_status.py の設定
- `_item_to_status_mapping` : アイテム番号とマシンステータスのマッピング
- 安全チェック条件の追加

### 2. placement_manager.py の設定
- 各スロットの実際の設置位置
- 許可されたアイテム番号
- テーブルベースパス
- 力取得ロジックの実装

## 使用方法

```python
# 拡張機能インスタンス取得
from item_placement_system.extension import get_extension_instance
ext = get_extension_instance()

# アイテム設置
success, message = ext.attempt_place_item_by_path("/World/ItemTray/Item1", "drill_mount")

# 自動検出設置
success, message = ext.auto_detect_and_place_item("/World/ItemTray/Item1")
```