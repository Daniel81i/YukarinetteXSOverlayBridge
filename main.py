"""
YncneoXSOBridge - リファクタリング版

共通ライブラリを使用した簡潔なメイン処理
"""

import sys
import time
import signal
import logging
from typing import Optional

# 共通ライブラリ（再利用可能）
from lib.tray_helper import TrayHelper
from lib.logger_helper import LoggerManager
from lib.config_helper import ConfigManager, RegistryConfigMixin

# プロジェクト固有モジュール
from modules.translation_logger import TranslationLogger
from modules.yukacone_client import YukaconeClient
from modules.xso_client import XSOClient
from modules.media_controller import MediaKeyController


class YncneoXSOBridge:
    """メインアプリケーションクラス"""
    
    def __init__(self):
        self.is_running = True
        self.config = None
        self.logger_mgr = None
        self.tray = None
        self.xso_client = None
        self.yukacone_client = None
        self.translation_logger = None
        self.media_controller = None
    
    def load_config(self):
        """設定を読み込む"""
        config_mgr = ConfigManager(
            config_filename="config.json",
            required_keys=["app_name", "xso_endpoint", "translation_profiles"]
        )
        
        self.config = config_mgr.load()
        
        # レジストリからポート取得
        try:
            http_port = RegistryConfigMixin.read_registry_value(
                self.config["Yncneo_Registry_Hive"],
                self.config["Yncneo_Registry_Path"],
                self.config["Yncneo_Registry_Value_Http"]
            )
            ws_port = RegistryConfigMixin.read_registry_value(
                self.config["Yncneo_Registry_Hive"],
                self.config["Yncneo_Registry_Path"],
                self.config["Yncneo_Registry_Value_Websocket"]
            )
            
            # エンドポイントを構築
            self.config["yukacone_http_endpoint"] = f"http://127.0.0.1:{http_port}/api"
            self.config["yukacone_ws_endpoint"] = f"ws://127.0.0.1:{ws_port}/api"
            
            # ポート情報を保存（トレイ表示用）
            self.config["_ports"] = {
                "yukacone_http": http_port,
                "yukacone_ws": ws_port
            }
            
        except RuntimeError as e:
            logging.error(f"レジストリからポート取得失敗: {e}")
            sys.exit(1)
    
    def setup_logging(self):
        """ログシステムをセットアップ"""
        self.logger_mgr = LoggerManager(
            app_name=self.config["app_name"],
            debug=self.config.get("debug", False),
            log_dir="logs"
        )
        self.logger_mgr.setup()
    
    def setup_tray_icon(self):
        """トレイアイコンをセットアップ"""
        def on_settings():
            logging.info("設定メニューが選択されました")
            # 設定ダイアログを開く処理など
        
        self.tray = TrayHelper(
            app_name=self.config["app_name"],
            icon_path="icon.ico",
            on_exit=self.cleanup,
            additional_menu_items=[
                ("Settings", lambda icon, item: on_settings())
            ]
        )
        
        # 初期ステータス
        self._update_tray_status()
        self.tray.start()
    
    def _update_tray_status(self):
        """トレイのステータスを更新"""
        if not self.tray:
            return
        
        status = "Mute" if self.yukacone_client and self.yukacone_client.is_muted else "Online"
        
        ports = self.config.get("_ports", {})
        
        self.tray.update_status(
            status=status,
            HTTP=ports.get("yukacone_http"),
            WS=ports.get("yukacone_ws"),
            DEBUG="ON" if self.config.get("debug") else "OFF"
        )
    
    def setup_clients(self):
        """各種クライアントをセットアップ"""
        # XSOクライアント
        self.xso_client = XSOClient(
            endpoint=self.config["xso_endpoint"],
            app_name=self.config["app_name"]
        )
        self.xso_client.connect()
        
        # Yukaconeクライアント
        self.yukacone_client = YukaconeClient(
            http_endpoint=self.config["yukacone_http_endpoint"],
            ws_endpoint=self.config["yukacone_ws_endpoint"],
            translation_profiles=self.config["translation_profiles"],
            on_status_change=self._update_tray_status
        )
        self.yukacone_client.connect()
        
        # 翻訳ログ
        self.translation_logger = TranslationLogger(
            base_dir=".",
            stable_sec=self.config.get("PROCESS_STABLE_SEC", 10.0),
            flush_interval=self.config.get("FLUSH_INTERVAL_SEC", 1.0)
        )
        self.translation_logger.start()
        
        # Yukaconeの受信データを翻訳ログに渡す
        self.yukacone_client.on_translation_data = self.translation_logger.add_yukacone_message
    
    def setup_media_controller(self):
        """メディアキーコントローラーをセットアップ"""
        self.media_controller = MediaKeyController(
            yukacone_client=self.yukacone_client,
            xso_client=self.xso_client,
            on_status_change=self._update_tray_status
        )
        self.media_controller.start()
    
    def initialize(self):
        """初期化処理"""
        logging.info("初期化を開始します")
        
        # 初期翻訳設定
        self.yukacone_client.set_translation_profile(0)
        time.sleep(1.0)
        
        # ミュート状態にする
        self.yukacone_client.set_mute(True)
        
        # XSOに状態を送信
        self.xso_client.send_status(
            profile=self.config["translation_profiles"][0],
            is_muted=True
        )
        
        logging.info("初期化完了")
    
    def run(self):
        """メインループ"""
        logging.info(f"{self.config['app_name']} を起動しました")
        
        while self.is_running:
            try:
                time.sleep(1)
            except KeyboardInterrupt:
                break
        
        self.cleanup()
    
    def cleanup(self):
        """終了処理"""
        logging.info("クリーンアップを開始します")
        self.is_running = False
        
        # 各コンポーネントの停止
        if self.media_controller:
            self.media_controller.stop()
        
        if self.translation_logger:
            self.translation_logger.stop()
        
        if self.yukacone_client:
            self.yukacone_client.disconnect()
        
        if self.xso_client:
            self.xso_client.disconnect()
        
        if self.tray:
            self.tray.stop()
        
        logging.info("プログラムを終了します")
        sys.exit(0)
    
    def signal_handler(self, sig, frame):
        """シグナルハンドラー"""
        logging.info(f"シグナル {sig} を受信しました")
        self.cleanup()


def main():
    """エントリーポイント"""
    app = YncneoXSOBridge()
    
    # シグナルハンドラー登録
    signal.signal(signal.SIGINT, app.signal_handler)
    signal.signal(signal.SIGTERM, app.signal_handler)
    
    try:
        # 設定読み込み
        app.load_config()
        
        # ログ初期化
        app.setup_logging()
        
        # トレイアイコン
        app.setup_tray_icon()
        
        # 各種クライアント
        app.setup_clients()
        
        # メディアキーコントローラー
        app.setup_media_controller()
        
        # 初期化
        app.initialize()
        
        # 実行
        app.run()
        
    except Exception as e:
        logging.error(f"予期しないエラー: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
