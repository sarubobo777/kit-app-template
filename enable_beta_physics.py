"""
Physics Beta機能を強制的に有効化するスクリプト
"""

import carb.settings

def enable_beta_physics():
    """Physics Beta機能を有効化"""
    settings = carb.settings.get_settings()

    print("=" * 70)
    print("Physics Beta機能 強制有効化")
    print("=" * 70)

    # 複数の設定パスを試す
    settings_paths = [
        "/physics/developmentMode",
        "/physics/enableBetaFeatures",
        "/app/physics/enableBetaFeatures",
        "/persistent/physics/betaFeaturesEnabled",
    ]

    for path in settings_paths:
        try:
            settings.set(path, True)
            print(f"✅ {path} = True")
        except Exception as e:
            print(f"⚠️  {path} 設定失敗: {e}")

    print("\n確認:")
    for path in settings_paths:
        value = settings.get(path)
        print(f"  {path}: {value}")

    print("\n" + "=" * 70)
    print("⚠️  重要: アプリケーションを再起動してください")
    print("=" * 70)

if __name__ == "__main__":
    enable_beta_physics()
