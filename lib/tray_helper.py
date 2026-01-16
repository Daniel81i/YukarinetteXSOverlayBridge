"""
汎用トレイアイコン管理ヘルパー

使い方:
    tray = TrayHelper(
        app_name="MyApp",
        icon_path="icon.ico",
        on_exit=cleanup_function
    )
    tray.update_status("Running", port=8080, debug=True)
    tray.start()
"""

import os
import sys
from PIL import Image
import pystray
from typing import Callable, Optional, Dict, Any


class TrayHelper:
    """汎用トレイアイコン管理クラス"""
    
    def __init__(
        self,
        app_name: str,
        icon_path: Optional[str] = None,
        on_exit: Optional[Callable] = None,
        additional_menu_items: Optional[list] = None
    ):
        """
        Args:
            app_name: アプリケーション名
            icon_path: アイコンファイルのパス（なければデフォルト画像）
            on_exit: 終了時に呼ばれるコールバック関数
            additional_menu_items: 追加メニュー項目のリスト
                例: [("Settings", callback_func), ("Help", help_func)]
        """
        self.app_name = app_name
        self.icon_path = icon_path
        self.on_exit_callback = on_exit
        self.additional_menu_items = additional_menu_items or []
        
        self.icon = None
        self.status_parts = {}  # 状態情報を辞書で管理
        self._create_icon()
    
    def _get_resource_path(self, relative_path: str) -> str:
        """PyInstaller対応のリソースパス取得"""
        if hasattr(sys, "_MEIPASS"):
            base_path = sys._MEIPASS
        else:
            base_path = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base_path, relative_path)
    
    def _load_icon_image(self) -> Image.Image:
        """アイコン画像を読み込む"""
        if self.icon_path:
            try:
                path = self._get_resource_path(self.icon_path)
                if os.path.exists(path):
                    return Image.open(path)
            except Exception as e:
                print(f"アイコン読み込みエラー: {e}")
        
        # フォールバック: 透明な64x64画像
        return Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    
    def _on_exit_clicked(self, icon, item):
        """終了メニューがクリックされた時の処理"""
        if self.on_exit_callback:
            self.on_exit_callback()
        self.stop()
    
    def _create_menu(self):
        """メニューを動的に生成"""
        menu_items = []
        
        # 追加メニュー項目
        for label, callback in self.additional_menu_items:
            menu_items.append(pystray.MenuItem(label, callback))
        
        # 終了メニュー
        menu_items.append(pystray.MenuItem("Exit", self._on_exit_clicked))
        
        return pystray.Menu(*menu_items)
    
    def _create_icon(self):
        """トレイアイコンを作成"""
        image = self._load_icon_image()
        title = self._build_title()
        menu = self._create_menu()
        
        self.icon = pystray.Icon(self.app_name, image, title, menu)
    
    def _build_title(self) -> str:
        """ステータス文字列を構築"""
        parts = [self.app_name]
        
        # 辞書の内容を文字列化
        for key, value in self.status_parts.items():
            parts.append(f"{key}:{value}")
        
        return " | ".join(parts)
    
    def start(self):
        """トレイアイコンを表示（非ブロッキング）"""
        if self.icon:
            self.icon.run_detached()
    
    def stop(self):
        """トレイアイコンを停止"""
        if self.icon:
            try:
                self.icon.visible = False
                self.icon.stop()
            except Exception as e:
                print(f"トレイアイコン停止エラー: {e}")
    
    def update_status(self, **kwargs):
        """
        ステータスを更新
        
        例:
            tray.update_status(status="Running", port=8080, debug=True)
            → "MyApp | status:Running | port:8080 | debug:True"
        """
        self.status_parts.update(kwargs)
        
        if self.icon:
            self.icon.title = self._build_title()
    
    def set_status(self, status_dict: Dict[str, Any]):
        """ステータスを一括設定（既存の状態をクリア）"""
        self.status_parts = status_dict.copy()
        
        if self.icon:
            self.icon.title = self._build_title()
    
    def add_menu_item(self, label: str, callback: Callable):
        """実行時にメニュー項目を追加（再作成が必要）"""
        self.additional_menu_items.append((label, callback))
        
        # アイコンを再作成
        was_running = self.icon is not None and hasattr(self.icon, '_running')
        if was_running:
            self.stop()
        
        self._create_icon()
        
        if was_running:
            self.start()


# 使用例
if __name__ == "__main__":
    import time
    
    def on_settings():
        print("設定が開かれました")
    
    def on_exit():
        print("終了処理中...")
    
    # トレイヘルパーを作成
    tray = TrayHelper(
        app_name="TestApp",
        icon_path="icon.ico",  # オプション
        on_exit=on_exit,
        additional_menu_items=[
            ("Settings", lambda icon, item: on_settings())
        ]
    )
    
    # 初期ステータス
    tray.update_status(status="Initializing")
    tray.start()
    
    # ステータス更新のデモ
    time.sleep(2)
    tray.update_status(status="Running", port=8080, debug=False)
    
    time.sleep(2)
    tray.update_status(status="Connected", users=5)
    
    # メインループ（実際のアプリではここに処理を書く）
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        tray.stop()
