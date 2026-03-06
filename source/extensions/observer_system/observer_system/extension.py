# SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

import omni.ext

# Global extension instance for external access
_extension_instance = None

class ObserverSystemExtension(omni.ext.IExt):
    """
    Observer System Extension
    システム全体の状態監視とオブジェクト着脱管理システム
    """

    def __init__(self):
        super().__init__()
        # System configuration
        self._trigger_configs = {
            "/World/New_MillingMachine/Main/Doril/Trigger_Drill": {
                "expected_number": 1,
                "name": "Drill Trigger"
            },
            "/World/New_MillingMachine/Table/Trigger_Table": {
                "expected_number": 2,
                "name": "Table Trigger"
            },
            "/World/Industrial/Industrial/Trigger_Plug": {
                "expected_number": 3,
                "name": "Plug Trigger"
            }
        }

        self._system_paths = {
            "ground": "/Environment/groundCollider",
            "item_tray": "/World/ItemTray",
            "stock": "/World/Stock"
        }

        # System state
        self._is_power_connected = False
        self._current_scenario_step = 0
        self._removable_objects = {}  # path -> removable_flag

    def on_startup(self, ext_id):
        """Extension startup"""
        global _extension_instance
        _extension_instance = self

        print("[Observer System] Starting up...")

        try:
            print("[Observer System] Basic startup complete")
        except Exception as e:
            print(f"[Observer System] Startup failed: {e}")

    def on_shutdown(self):
        """Extension shutdown"""
        global _extension_instance

        print("[Observer System] Shutting down...")

        try:
            _extension_instance = None
            print("[Observer System] Shutdown complete")
        except Exception as e:
            print(f"[Observer System] Shutdown error: {e}")

    # Public API methods for external access
    def get_trigger_configs(self):
        """Get trigger configurations"""
        return self._trigger_configs.copy()

    def get_system_paths(self):
        """Get system paths"""
        return self._system_paths.copy()

    def is_power_connected(self):
        """Check if power is connected"""
        return self._is_power_connected

    def set_power_connected(self, connected):
        """Set power connection state"""
        self._is_power_connected = connected
        print(f"[Observer System] Power connection: {'ON' if connected else 'OFF'}")

    def get_current_scenario_step(self):
        """Get current scenario step"""
        return self._current_scenario_step

    def set_scenario_step(self, step):
        """Set current scenario step"""
        old_step = self._current_scenario_step
        self._current_scenario_step = step
        print(f"[Observer System] Scenario step: {old_step} -> {step}")

    def set_object_removable(self, object_path, removable):
        """Set object removable state"""
        self._removable_objects[object_path] = removable
        print(f"[Observer System] Object {object_path} removable: {removable}")

    def is_object_removable(self, object_path):
        """Check if object is removable"""
        return self._removable_objects.get(object_path, True)  # Default to removable

    def show_message(self, message, message_type="info"):
        """Show message in UI"""
        print(f"[Observer System] Message ({message_type}): {message}")

def get_extension_instance():
    """Get the global extension instance"""
    return _extension_instance