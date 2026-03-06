# SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

"""
MachineStatus System
フライス盤の現在の状態フラグを管理するシステム
"""

import typing
from enum import Enum

class MachineStatusType(Enum):
    """マシンステータスの種類"""
    POWER_ON = "power_on" #電源プラグ管理
    DRILL_ATTACHED = "drill_attached" #ドリル取付状態
    DRILL_ROTATING = "drill_rotating" #ドリルが回転しているかどうか
    WORKPIECE_MOUNTED = "workpiece_mounted" #材料設置状態
    SAFETY_GUARD_CLOSED = "safety_guard_closed" #安全かどうか
    SPINDLE_LOCKED = "spindle_locked" #ドリル固定
    HANDLE_ATTACHED = "handle_attached" #ハンドル取付状態

class MachineStatus:
    """
    フライス盤の状態管理システム
    各種フラグの管理とアイテム設置による状態変更を処理
    """

    def __init__(self):
        # 状態フラグの初期化
        self._status_flags = {
            MachineStatusType.POWER_ON: False,
            MachineStatusType.DRILL_ATTACHED: False,
            MachineStatusType.DRILL_ROTATING: False,
            MachineStatusType.WORKPIECE_MOUNTED: False,
            MachineStatusType.SAFETY_GUARD_CLOSED: False,
            MachineStatusType.SPINDLE_LOCKED: False,
            MachineStatusType.HANDLE_ATTACHED: False
        }

        # アイテム番号と状態フラグのマッピング
        self._item_to_status_mapping = {
            1: MachineStatusType.DRILL_ATTACHED,
            2: MachineStatusType.POWER_ON,
            3: MachineStatusType.WORKPIECE_MOUNTED,
            4: MachineStatusType.HANDLE_ATTACHED
        }

        # 状態変更のリスナー
        self._status_listeners = []

        print("[MachineStatus] システム初期化完了")

    def set_status(self, status_type: MachineStatusType, value: bool, source_item_number: int = None):
        """
        状態フラグを設定

        Args:
            status_type: 設定する状態タイプ
            value: 設定値 (True/False)
            source_item_number: 状態変更の原因となったアイテム番号
        """
        old_value = self._status_flags.get(status_type, False)
        self._status_flags[status_type] = value

        print(f"[MachineStatus] {status_type.value}: {old_value} -> {value}")
        if source_item_number:
            print(f"[MachineStatus] 変更原因: アイテム番号 {source_item_number}")

        # リスナーに通知
        self._notify_status_change(status_type, old_value, value, source_item_number)

    def get_status(self, status_type: MachineStatusType) -> bool:
        """
        状態フラグを取得

        Args:
            status_type: 取得する状態タイプ

        Returns:
            bool: 現在の状態値
        """
        return self._status_flags.get(status_type, False)

    def get_all_status(self) -> dict:
        """
        全ての状態フラグを取得

        Returns:
            dict: 全状態フラグの辞書
        """
        return self._status_flags.copy()

    def on_item_placed(self, item_number: int, placement_slot: str):
        """
        アイテムが設置されたときの状態更新

        Args:
            item_number: 設置されたアイテムの番号
            placement_slot: 設置されたスロット名
        """
        if item_number in self._item_to_status_mapping:
            status_type = self._item_to_status_mapping[item_number]
            self.set_status(status_type, True, item_number)

            # 特別な処理が必要な場合
            self._handle_special_placement_logic(item_number, placement_slot)

        print(f"[MachineStatus] アイテム {item_number} が {placement_slot} に設置されました")

    def on_item_removed(self, item_number: int, placement_slot: str):
        """
        アイテムが取り外されたときの状態更新

        Args:
            item_number: 取り外されたアイテムの番号
            placement_slot: 取り外されたスロット名
        """
        if item_number in self._item_to_status_mapping:
            status_type = self._item_to_status_mapping[item_number]
            self.set_status(status_type, False, item_number)

            # 関連する状態もリセット（例：ドリルが外されたら回転も停止）
            self._handle_removal_cascade(item_number, placement_slot)

        print(f"[MachineStatus] アイテム {item_number} が {placement_slot} から取り外されました")

    def _handle_special_placement_logic(self, item_number: int, placement_slot: str):
        """
        特別な設置ロジックの処理

        Args:
            item_number: アイテム番号
            placement_slot: 設置スロット
        """
        # 例: ドリルが設置されたら、電源がONなら自動的にスピンドルロックを解除
        if item_number == 1:  # ドリルの場合（実際の番号は要設定）
            if self.get_status(MachineStatusType.POWER_ON):
                self.set_status(MachineStatusType.SPINDLE_LOCKED, False)

    def _handle_removal_cascade(self, item_number: int, placement_slot: str):
        """
        取り外しによる連鎖的状態変更

        Args:
            item_number: アイテム番号
            placement_slot: 設置スロット
        """
        # 例: ドリルが外されたら回転も停止
        if item_number == 1:  # ドリルの場合（実際の番号は要設定）
            self.set_status(MachineStatusType.DRILL_ROTATING, False)
            self.set_status(MachineStatusType.SPINDLE_LOCKED, True)

    def add_status_listener(self, listener):
        """
        状態変更リスナーを追加

        Args:
            listener: 状態変更時に呼び出される関数
        """
        self._status_listeners.append(listener)

    def remove_status_listener(self, listener):
        """
        状態変更リスナーを削除

        Args:
            listener: 削除するリスナー
        """
        if listener in self._status_listeners:
            self._status_listeners.remove(listener)

    def _notify_status_change(self, status_type: MachineStatusType, old_value: bool,
                             new_value: bool, source_item: int = None):
        """
        状態変更をリスナーに通知

        Args:
            status_type: 変更された状態タイプ
            old_value: 変更前の値
            new_value: 変更後の値
            source_item: 変更原因のアイテム番号
        """
        for listener in self._status_listeners:
            try:
                listener(status_type, old_value, new_value, source_item)
            except Exception as e:
                print(f"[MachineStatus] リスナーエラー: {e}")

    def is_safe_to_operate(self) -> bool:
        """
        機械が安全に動作可能かチェック

        Returns:
            bool: 安全に動作可能かどうか
        """
        # 基本的な安全チェック
        if self.get_status(MachineStatusType.EMERGENCY_STOP):
            return False

        if not self.get_status(MachineStatusType.POWER_ON):
            return False

        # その他の安全条件
        # ここに入力してください: 追加の安全チェック条件

        return True

    def get_status_summary(self) -> str:
        """
        現在の状態サマリーを取得

        Returns:
            str: 状態の要約文字列
        """
        summary = ["=== Machine Status Summary ==="]
        for status_type, value in self._status_flags.items():
            status_str = "ON" if value else "OFF"
            summary.append(f"{status_type.value}: {status_str}")

        summary.append(f"Safe to operate: {'YES' if self.is_safe_to_operate() else 'NO'}")

        return "\n".join(summary)

# グローバルインスタンス
_machine_status_instance = None

def get_machine_status() -> MachineStatus:
    """
    MachineStatusのグローバルインスタンスを取得

    Returns:
        MachineStatus: グローバルインスタンス
    """
    global _machine_status_instance
    if _machine_status_instance is None:
        _machine_status_instance = MachineStatus()
    return _machine_status_instance