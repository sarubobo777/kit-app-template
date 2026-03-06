"""
Item Placement System Extension (Trigger-based)
トリガーベースのアイテム配置システム拡張機能

PhysX Triggerを使用して、アイテムの正誤判定と自動配置を行います。
旧システムからの移行: extension_backup.pyに旧バージョンをバックアップ
"""

# 新しいTriggerベースのシステムをインポート
from .extension_trigger import (
    ItemPlacementTriggerExtension as ItemPlacementExtension,
    get_extension_instance,
    LOG_PREFIX
)

# 後方互換性のため、旧モジュールもインポート可能にする
try:
    from .placement_manager import get_placement_manager, ItemPlacementManager
    from .machine_status import get_machine_status, MachineStatus
except ImportError:
    # 旧モジュールが利用できない場合はスキップ
    pass

# このファイルから直接インポートできるようにエクスポート
__all__ = [
    'ItemPlacementExtension',
    'get_extension_instance',
]
