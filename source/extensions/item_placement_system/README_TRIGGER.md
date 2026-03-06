# Item Placement System (Trigger版) - クイックスタート

## 🚀 5分で始めるTriggerベースのアイテム配置システム

### ステップ1: トリガーを配置（USDシーン）

```
/World/Triggers/TriggerSlot1  (Cube with Collider)
/World/Triggers/TriggerSlot2  (Cube with Collider)
/World/Triggers/TriggerSlot3  (Cube with Collider)
/World/Triggers/TriggerSlot4  (Cube with Collider)
```

### ステップ2: アイテムにNumber属性を設定

```python
from pxr import Sdf

item_prim = stage.GetPrimAtPath("/World/Items/Item1")
number_attr = item_prim.CreateAttribute("Number", Sdf.ValueTypeNames.Int)
number_attr.Set(1)
```

### ステップ3: 拡張機能を有効化

Window → Extensions → `Item Placement System` → Enable

### ステップ4: 実行

1. UIの「トリガー再セットアップ」をクリック
2. Playボタンでシミュレーション開始
3. アイテムをトリガーに移動
4. **正解→自動配置、不正解→原点リセット**

---

## ⚙️ デフォルト設定

| スロットID | トリガーパス | 正解Number | 配置先座標 |
|-----------|-------------|-----------|-----------|
| trigger_slot_1 | /World/Triggers/TriggerSlot1 | 1 | (10, 5, 0) |
| trigger_slot_2 | /World/Triggers/TriggerSlot2 | 2 | (20, 5, 0) |
| trigger_slot_3 | /World/Triggers/TriggerSlot3 | 3 | (30, 5, 0) |
| trigger_slot_4 | /World/Triggers/TriggerSlot4 | 4 | (40, 5, 0) |

**カスタマイズ**: `trigger_manager.py` の `DEFAULT_SLOTS` を編集

---

## 📖 詳細ドキュメント

- **使い方ガイド**: [TRIGGER_SYSTEM_GUIDE.md](docs/TRIGGER_SYSTEM_GUIDE.md)
- **実装ガイド**: [IMPLEMENTATION_GUIDE.md](docs/IMPLEMENTATION_GUIDE.md)

---

## 🐛 トラブルシューティング

### トリガーが反応しない？

1. UIの「トリガー診断」ボタンをクリック
2. コンソール出力を確認:
   - `Prim Status: Valid ✅` になっているか
   - `CollisionAPI: True` になっているか
   - `Script Exists: True` になっているか

### アイテムが判定されない？

1. アイテムに`Number`属性があるか確認
2. Number値がトリガーの`correct_numbers`に含まれているか確認
3. コンソールで判定ログを確認

---

## 💡 よくある質問

**Q: 複数の正解値を設定できますか？**
A: はい。`correct_numbers=[1, 2, 3]` のように配列で設定できます。

**Q: 配置先を動的に変更できますか？**
A: はい。シナリオコントローラーから`update_slot_from_scenario()`で更新可能です（将来実装）。

**Q: 5つ目以降のトリガーを追加できますか？**
A: はい。`trigger_manager.py`の`DEFAULT_SLOTS`に追加するか、実行時に`add_trigger_slot()`で追加できます。

---

## 📞 サポート

質問やバグ報告は、プロジェクトのIssueトラッカーまで。

Happy coding! 🎉
