"""
汎用Config読み込みヘルパー

使い方:
    config_mgr = ConfigManager("config.json")
    config = config_mgr.load()
    
    app_name = config.get("app_name", "DefaultApp")
    port = config.get_int("port", 8080)
"""

import json
import os
import sys
from typing import Any, Optional, Dict


class ConfigManager:
    """汎用Config管理クラス"""
    
    def __init__(
        self,
        config_filename: str = "config.json",
        config_dir: Optional[str] = None,
        required_keys: Optional[list] = None
    ):
        """
        Args:
            config_filename: 設定ファイル名
            config_dir: 設定ファイルのディレクトリ（Noneなら実行ファイルと同じ場所）
            required_keys: 必須キーのリスト（Noneならチェックしない）
        """
        self.config_filename = config_filename
        self.config_dir = config_dir
        self.required_keys = required_keys or []
        
        self._config = {}
        self._config_path = None
    
    def _get_base_dir(self) -> str:
        """実行ファイルの基準ディレクトリを取得"""
        if getattr(sys, 'frozen', False):
            # PyInstallerで実行ファイル化されている場合
            return os.path.dirname(sys.executable)
        else:
            # 通常のPythonスクリプトとして実行されている場合
            return os.path.dirname(os.path.abspath(sys.argv[0]))
    
    def _resolve_config_path(self) -> str:
        """設定ファイルのパスを解決"""
        if self.config_dir:
            # 明示的にディレクトリが指定されている場合
            if os.path.isabs(self.config_dir):
                config_path = os.path.join(self.config_dir, self.config_filename)
            else:
                base_dir = self._get_base_dir()
                config_path = os.path.join(base_dir, self.config_dir, self.config_filename)
        else:
            # 実行ファイルと同じディレクトリ
            base_dir = self._get_base_dir()
            config_path = os.path.join(base_dir, self.config_filename)
        
        return config_path
    
    def _validate_config(self, config: dict):
        """必須キーの存在チェック"""
        if not self.required_keys:
            return
        
        missing_keys = [key for key in self.required_keys if key not in config]
        
        if missing_keys:
            raise ValueError(
                f"Config に必須キーが不足しています: {', '.join(missing_keys)}"
            )
    
    def load(self) -> dict:
        """
        設定ファイルを読み込む
        
        Returns:
            設定内容の辞書
        
        Raises:
            FileNotFoundError: 設定ファイルが見つからない
            json.JSONDecodeError: JSON形式が不正
            ValueError: 必須キーが不足
        """
        self._config_path = self._resolve_config_path()
        
        if not os.path.exists(self._config_path):
            raise FileNotFoundError(
                f"設定ファイルが見つかりません: {self._config_path}"
            )
        
        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                self._config = json.load(f)
        except json.JSONDecodeError as e:
            raise json.JSONDecodeError(
                f"設定ファイルのJSON形式が不正です: {e.msg}",
                e.doc,
                e.pos
            )
        
        # 必須キーのチェック
        self._validate_config(self._config)
        
        return self._config
    
    def get(self, key: str, default: Any = None) -> Any:
        """設定値を取得"""
        return self._config.get(key, default)
    
    def get_int(self, key: str, default: int = 0) -> int:
        """整数型の設定値を取得"""
        value = self._config.get(key, default)
        try:
            return int(value)
        except (ValueError, TypeError):
            return default
    
    def get_bool(self, key: str, default: bool = False) -> bool:
        """ブール型の設定値を取得"""
        value = self._config.get(key, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("true", "yes", "1")
        return bool(value)
    
    def get_list(self, key: str, default: Optional[list] = None) -> list:
        """リスト型の設定値を取得"""
        value = self._config.get(key, default or [])
        return value if isinstance(value, list) else default or []
    
    def get_dict(self, key: str, default: Optional[dict] = None) -> dict:
        """辞書型の設定値を取得"""
        value = self._config.get(key, default or {})
        return value if isinstance(value, dict) else default or {}
    
    def save(self, config: Optional[dict] = None, indent: int = 2):
        """
        設定をファイルに保存
        
        Args:
            config: 保存する設定（Noneなら現在の_configを保存）
            indent: JSONのインデント
        """
        if config is not None:
            self._config = config
        
        if not self._config_path:
            self._config_path = self._resolve_config_path()
        
        try:
            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump(self._config, f, ensure_ascii=False, indent=indent)
        except Exception as e:
            raise IOError(f"設定ファイルの保存に失敗しました: {e}")
    
    def get_config_path(self) -> Optional[str]:
        """設定ファイルのパスを取得"""
        return self._config_path
    
    def reload(self) -> dict:
        """設定を再読み込み"""
        return self.load()


class RegistryConfigMixin:
    """Windowsレジストリから設定を読むMixin"""
    
    @staticmethod
    def read_registry_value(
        hive_name: str,
        key_path: str,
        value_name: str
    ) -> Any:
        """
        Windowsレジストリから値を読み込む
        
        Args:
            hive_name: "HKEY_CURRENT_USER" など
            key_path: レジストリキーのパス
            value_name: 値の名前
        
        Returns:
            レジストリの値
        
        Raises:
            RuntimeError: レジストリアクセス失敗
        """
        try:
            import winreg
        except ImportError:
            raise RuntimeError("winregモジュールが利用できません（Windows専用）")
        
        # Hive名をHKEYオブジェクトに変換
        hive_map = {
            "HKEY_CURRENT_USER": winreg.HKEY_CURRENT_USER,
            "HKCU": winreg.HKEY_CURRENT_USER,
            "HKEY_LOCAL_MACHINE": winreg.HKEY_LOCAL_MACHINE,
            "HKLM": winreg.HKEY_LOCAL_MACHINE,
        }
        
        hive = hive_map.get(hive_name.upper())
        if hive is None:
            raise ValueError(f"未知のレジストリハイブ: {hive_name}")
        
        try:
            with winreg.OpenKey(hive, key_path) as key:
                value, reg_type = winreg.QueryValueEx(key, value_name)
                return value
        except FileNotFoundError:
            raise RuntimeError(
                f"レジストリキーが見つかりません: {hive_name}\\{key_path}"
            )
        except OSError as e:
            raise RuntimeError(
                f"レジストリ値の読み出しに失敗: {hive_name}\\{key_path}\\{value_name} - {e}"
            )


# 使用例
if __name__ == "__main__":
    # 基本的な使い方
    config_mgr = ConfigManager(
        config_filename="config.json",
        required_keys=["app_name", "port"]  # 必須キー指定
    )
    
    try:
        config = config_mgr.load()
        
        # 各種取得メソッド
        app_name = config_mgr.get("app_name", "DefaultApp")
        port = config_mgr.get_int("port", 8080)
        debug = config_mgr.get_bool("debug", False)
        profiles = config_mgr.get_list("translation_profiles", [])
        
        print(f"App: {app_name}, Port: {port}, Debug: {debug}")
        print(f"Profiles: {len(profiles)}件")
        
    except FileNotFoundError as e:
        print(f"エラー: {e}")
    except json.JSONDecodeError as e:
        print(f"JSON形式エラー: {e}")
    except ValueError as e:
        print(f"設定エラー: {e}")
    
    # レジストリ読み込み例（Windowsのみ）
    try:
        port = RegistryConfigMixin.read_registry_value(
            "HKEY_CURRENT_USER",
            "Software\\YukarinetteConnectorNeo",
            "HTTP"
        )
        print(f"レジストリから取得したポート: {port}")
    except RuntimeError as e:
        print(f"レジストリ読み込みエラー: {e}")
