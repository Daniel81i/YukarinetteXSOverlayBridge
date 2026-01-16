"""
XSOverlay接続管理モジュール

XSOverlayへのWebSocket接続と
メディアプレイヤー情報の表示、通知送信を管理する
"""

import json
import logging
import time
import threading
from typing import Optional, Dict, Any
from websocket import WebSocketApp


class XSOClient:
    """XSOverlayとの通信を管理するクライアント"""
    
    def __init__(
        self,
        endpoint: str,
        app_name: str,
        reconnect_delay: float = 3.0,
        max_reconnect_delay: float = 30.0
    ):
        """
        Args:
            endpoint: XSOverlay WebSocketエンドポイント (例: ws://127.0.0.1:42070)
            app_name: アプリケーション名（クライアント識別用）
            reconnect_delay: 再接続の初期遅延（秒）
            max_reconnect_delay: 再接続の最大遅延（秒）
        """
        self.endpoint = endpoint
        self.app_name = app_name
        self.reconnect_delay = reconnect_delay
        self.max_reconnect_delay = max_reconnect_delay
        
        self._ws = None
        self._ws_thread = None
        self._is_running = False
        self._reconnect_attempts = 0
        self._is_connected = False

    # ----------------------------------------
    # 公開API - 接続管理
    # ----------------------------------------
    def connect(self):
        """WebSocket接続を開始"""
        if self._is_running:
            logging.warning("XSOClient は既に接続中です")
            return
        
        self._is_running = True
        self._ws_thread = threading.Thread(target=self._ws_connect_loop, daemon=True)
        self._ws_thread.start()
        logging.info("XSOClient WebSocket接続を開始しました")

    def disconnect(self):
        """WebSocket接続を切断"""
        self._is_running = False
        
        if self._ws:
            try:
                self._ws.close()
            except Exception as e:
                logging.error(f"XSOClient WebSocket切断エラー: {e}")
        
        if self._ws_thread and self._ws_thread.is_alive():
            self._ws_thread.join(timeout=3.0)
        
        logging.info("XSOClient を切断しました")

    def is_connected(self) -> bool:
        """接続状態を取得"""
        return self._is_connected

    # ----------------------------------------
    # 公開API - メディアプレイヤー情報更新
    # ----------------------------------------
    def send_status(
        self,
        profile: Dict[str, Any],
        is_muted: bool,
        source_app: str = "ゆかコネ"
    ) -> bool:
        """
        メディアプレイヤー情報を送信（XSOverlayの画面に表示される）
        
        Args:
            profile: 翻訳プロファイル
            is_muted: ミュート状態
            source_app: ソースアプリ名
            
        Returns:
            送信成功した場合True
        """
        if not self._is_connected:
            logging.warning("XSOClientが接続されていません")
            return False
        
        try:
            profile_name = profile.get("name", "Unknown")
            engine = profile.get("translation_param", {}).get("engine", "Unknown")
            
            data = {
                "sender": self.app_name,
                "target": "xsoverlay",
                "command": "UpdateMediaPlayerInformation",
                "jsonData": json.dumps({
                    "artist": f"{profile_name} ({engine})",
                    "title": "Mute" if is_muted else "Online",
                    "album": self.app_name,
                    "sourceApp": source_app
                })
            }
            
            self._send_data(data)
            logging.debug(f"XSO状態更新: {profile_name} - {'Mute' if is_muted else 'Online'}")
            return True
            
        except Exception as e:
            logging.error(f"XSO状態送信エラー: {e}")
            return False

    def update_status_simple(
        self,
        title: str,
        artist: str,
        album: Optional[str] = None
    ) -> bool:
        """
        シンプルなステータス更新
        
        Args:
            title: タイトル（大きく表示される）
            artist: アーティスト（小さく表示される）
            album: アルバム名（オプション）
            
        Returns:
            送信成功した場合True
        """
        if not self._is_connected:
            logging.warning("XSOClientが接続されていません")
            return False
        
        try:
            data = {
                "sender": self.app_name,
                "target": "xsoverlay",
                "command": "UpdateMediaPlayerInformation",
                "jsonData": json.dumps({
                    "artist": artist,
                    "title": title,
                    "album": album or self.app_name,
                    "sourceApp": self.app_name
                })
            }
            
            self._send_data(data)
            return True
            
        except Exception as e:
            logging.error(f"XSO状態送信エラー: {e}")
            return False

    # ----------------------------------------
    # 公開API - 通知送信
    # ----------------------------------------
    def send_notification(
        self,
        content: str,
        title: Optional[str] = None,
        notification_type: int = 1,
        opacity: float = 0.5,
        volume: float = 0.0,
        duration: float = 3.0
    ) -> bool:
        """
        XSOverlayに通知を送信
        
        Args:
            content: 通知内容
            title: 通知タイトル（Noneならデフォルト）
            notification_type: 通知タイプ（1=通常）
            opacity: 不透明度（0.0-1.0）
            volume: 音量（0.0-1.0）
            duration: 表示時間（秒）
            
        Returns:
            送信成功した場合True
        """
        if not self._is_connected:
            logging.warning("XSOClientが接続されていません")
            return False
        
        try:
            notification_data = {
                "type": notification_type,
                "title": title or "ゆかコネ翻訳",
                "content": content,
                "opacity": opacity,
                "volume": volume,
                "timeout": duration
            }
            
            data = {
                "sender": self.app_name,
                "target": "xsoverlay",
                "command": "SendNotification",
                "jsonData": json.dumps(notification_data)
            }
            
            self._send_data(data)
            logging.info(f"XSO通知送信: {content}")
            return True
            
        except Exception as e:
            logging.error(f"XSO通知送信エラー: {e}")
            return False

    def send_translation_notification(
        self,
        translated_text: str,
        opacity: float = 0.5
    ) -> bool:
        """
        翻訳結果を通知
        
        Args:
            translated_text: 翻訳されたテキスト
            opacity: 不透明度
            
        Returns:
            送信成功した場合True
        """
        return self.send_notification(
            content=translated_text,
            title="翻訳",
            opacity=opacity,
            volume=0.0
        )

    # ----------------------------------------
    # 内部処理
    # ----------------------------------------
    def _send_data(self, data: Dict[str, Any]):
        """
        データを送信
        
        Args:
            data: 送信するデータ
        """
        if not self._ws or not self._is_connected:
            raise RuntimeError("WebSocketが接続されていません")
        
        self._ws.send(json.dumps(data))

    def _ws_connect_loop(self):
        """WebSocket接続ループ（再接続対応）"""
        while self._is_running:
            try:
                url = f"{self.endpoint}/?client={self.app_name}"
                logging.info(f"XSOverlay接続試行: {url}")
                
                self._ws = WebSocketApp(
                    url,
                    on_open=self._on_ws_open,
                    on_error=self._on_ws_error,
                    on_close=self._on_ws_close
                )
                
                self._ws.run_forever()
                
            except Exception as e:
                logging.error(f"XSOverlay接続エラー: {e}")
            
            self._is_connected = False
            
            if not self._is_running:
                break
            
            # 再接続待機（指数バックオフ）
            delay = min(
                self.reconnect_delay * (2 ** self._reconnect_attempts),
                self.max_reconnect_delay
            )
            logging.info(f"{delay:.1f}秒後にXSOverlayへ再接続します...")
            time.sleep(delay)
            self._reconnect_attempts += 1

    def _on_ws_open(self, ws):
        """WebSocket接続確立"""
        logging.info("XSOverlayに接続しました")
        self._is_connected = True
        self._reconnect_attempts = 0

    def _on_ws_error(self, ws, error):
        """WebSocketエラー"""
        logging.error(f"XSOverlay WebSocketエラー: {error}")
        self._is_connected = False

    def _on_ws_close(self, ws, close_status_code, close_msg):
        """WebSocket切断"""
        logging.warning(
            f"XSOverlay WebSocket切断: code={close_status_code}, msg={close_msg}"
        )
        self._is_connected = False


# 使用例
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    
    # クライアント作成
    client = XSOClient(
        endpoint="ws://127.0.0.1:42070",
        app_name="TestApp"
    )
    
    # 接続
    client.connect()
    
    # 接続待ち
    time.sleep(3)
    
    if client.is_connected():
        # ステータス更新テスト
        client.update_status_simple(
            title="Online",
            artist="Test Profile (Google)",
            album="TestApp"
        )
        
        time.sleep(2)
        
        # 通知テスト
        client.send_notification(
            content="これはテスト通知です",
            title="テスト"
        )
        
        time.sleep(2)
        
        # 翻訳通知テスト
        client.send_translation_notification(
            translated_text="Hello, World!",
            opacity=0.7
        )
    
    # メインループ
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        client.disconnect()
