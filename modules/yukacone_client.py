"""
Yukacone接続管理モジュール

YukarinetteConnectorNeoへのHTTP API呼び出しと
WebSocket接続を管理する
"""

import json
import logging
import time
import threading
from typing import Optional, List, Dict, Any, Callable
import requests
from websocket import WebSocketApp


class YukaconeClient:
    """Yukaconeとの通信を管理するクライアント"""
    
    def __init__(
        self,
        http_endpoint: str,
        ws_endpoint: str,
        translation_profiles: List[Dict],
        on_translation_data: Optional[Callable[[Dict], None]] = None,
        on_status_change: Optional[Callable[[], None]] = None,
        reconnect_delay: float = 3.0,
        max_reconnect_delay: float = 60.0
    ):
        """
        Args:
            http_endpoint: HTTP APIエンドポイント (例: http://127.0.0.1:15520/api)
            ws_endpoint: WebSocketエンドポイント (例: ws://127.0.0.1:15520/api)
            translation_profiles: 翻訳プロファイルのリスト
            on_translation_data: 翻訳データ受信時のコールバック
            on_status_change: ステータス変更時のコールバック
            reconnect_delay: 再接続の初期遅延（秒）
            max_reconnect_delay: 再接続の最大遅延（秒）
        """
        self.http_endpoint = http_endpoint
        self.ws_endpoint = ws_endpoint
        self.translation_profiles = translation_profiles
        self.on_translation_data = on_translation_data
        self.on_status_change = on_status_change
        
        self.reconnect_delay = reconnect_delay
        self.max_reconnect_delay = max_reconnect_delay
        
        self.current_profile_index = 0
        self.is_muted = True
        self.last_recognition_language = None
        
        self._ws = None
        self._ws_thread = None
        self._is_running = False
        self._reconnect_attempts = 0
        self._lock = threading.Lock()

    # ----------------------------------------
    # 公開API - 接続管理
    # ----------------------------------------
    def connect(self):
        """WebSocket接続を開始"""
        if self._is_running:
            logging.warning("YukaconeClient は既に接続中です")
            return
        
        self._is_running = True
        self._ws_thread = threading.Thread(target=self._ws_connect_loop, daemon=True)
        self._ws_thread.start()
        logging.info("YukaconeClient WebSocket接続を開始しました")

    def disconnect(self):
        """WebSocket接続を切断"""
        self._is_running = False
        
        if self._ws:
            try:
                self._ws.close()
            except Exception as e:
                logging.error(f"WebSocket切断エラー: {e}")
        
        if self._ws_thread and self._ws_thread.is_alive():
            self._ws_thread.join(timeout=3.0)
        
        logging.info("YukaconeClient を切断しました")

    # ----------------------------------------
    # 公開API - 翻訳制御
    # ----------------------------------------
    def set_translation_profile(self, index: int) -> bool:
        """
        翻訳プロファイルを変更
        
        Args:
            index: プロファイルのインデックス
            
        Returns:
            成功した場合True
        """
        if index < 0 or index >= len(self.translation_profiles):
            logging.error(f"無効なプロファイルインデックス: {index}")
            return False
        
        with self._lock:
            try:
                profile = self.translation_profiles[index]
                
                # 認識言語の変更（前回と異なる場合のみ）
                new_recognition_lang = profile.get("recognition_language")
                if new_recognition_lang != self.last_recognition_language:
                    self._call_api(
                        "/setRecognitionParam",
                        {"language": new_recognition_lang}
                    )
                    self.last_recognition_language = new_recognition_lang
                    time.sleep(0.5)
                
                # 翻訳エンジンの設定
                trans_param = profile.get("translation_param", {})
                self._call_api(
                    "/setTranslationParam",
                    {
                        "slot": trans_param.get("slot", 1),
                        "language": trans_param.get("language", "en-US"),
                        "engine": trans_param.get("engine", "google")
                    }
                )
                
                self.current_profile_index = index
                logging.info(f"翻訳プロファイル変更: {profile.get('name', 'Unknown')}")
                
                if self.on_status_change:
                    self.on_status_change()
                
                return True
                
            except Exception as e:
                logging.error(f"翻訳プロファイル変更エラー: {e}")
                return False

    def next_profile(self) -> bool:
        """次の翻訳プロファイルに切り替え"""
        next_index = (self.current_profile_index + 1) % len(self.translation_profiles)
        return self.set_translation_profile(next_index)

    def previous_profile(self) -> bool:
        """前の翻訳プロファイルに切り替え"""
        prev_index = (self.current_profile_index - 1) % len(self.translation_profiles)
        return self.set_translation_profile(prev_index)

    def set_mute(self, muted: bool) -> bool:
        """
        ミュート状態を変更
        
        Args:
            muted: Trueでミュート、Falseで解除
            
        Returns:
            成功した場合True
        """
        with self._lock:
            try:
                endpoint = "/mute-on" if muted else "/mute-off"
                self._call_api(endpoint, {})
                self.is_muted = muted
                
                logging.info(f"ミュート状態変更: {'ON' if muted else 'OFF'}")
                
                if self.on_status_change:
                    self.on_status_change()
                
                return True
                
            except Exception as e:
                logging.error(f"ミュート変更エラー: {e}")
                return False

    def toggle_mute(self) -> bool:
        """ミュート状態をトグル"""
        return self.set_mute(not self.is_muted)

    # ----------------------------------------
    # 公開API - 情報取得
    # ----------------------------------------
    def get_current_profile(self) -> Optional[Dict]:
        """現在の翻訳プロファイルを取得"""
        if 0 <= self.current_profile_index < len(self.translation_profiles):
            return self.translation_profiles[self.current_profile_index]
        return None

    def get_profile_name(self) -> str:
        """現在のプロファイル名を取得"""
        profile = self.get_current_profile()
        return profile.get("name", "Unknown") if profile else "Unknown"

    def get_translation_engine(self) -> str:
        """現在の翻訳エンジンを取得"""
        profile = self.get_current_profile()
        if profile:
            return profile.get("translation_param", {}).get("engine", "Unknown")
        return "Unknown"

    # ----------------------------------------
    # 内部処理 - HTTP API
    # ----------------------------------------
    def _call_api(self, path: str, params: Dict[str, Any]) -> bool:
        """
        Yukacone HTTP APIを呼び出す
        
        Args:
            path: APIパス (例: "/mute-on")
            params: パラメータ
            
        Returns:
            成功した場合True
        """
        try:
            url = f"{self.http_endpoint}{path}"
            logging.debug(f"API呼び出し: {path} {params}")
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            logging.debug(f"API成功: {path}")
            return True
            
        except requests.exceptions.RequestException as e:
            logging.error(f"API呼び出し失敗: {path} - {e}")
            return False

    # ----------------------------------------
    # 内部処理 - WebSocket
    # ----------------------------------------
    def _ws_connect_loop(self):
        """WebSocket接続ループ（再接続対応）"""
        while self._is_running:
            try:
                logging.info(f"WebSocket接続試行: {self.ws_endpoint}")
                
                self._ws = WebSocketApp(
                    self.ws_endpoint,
                    on_open=self._on_ws_open,
                    on_message=self._on_ws_message,
                    on_error=self._on_ws_error,
                    on_close=self._on_ws_close
                )
                
                self._ws.run_forever()
                
            except Exception as e:
                logging.error(f"WebSocket接続エラー: {e}")
            
            if not self._is_running:
                break
            
            # 再接続待機（指数バックオフ）
            delay = min(
                self.reconnect_delay * (2 ** self._reconnect_attempts),
                self.max_reconnect_delay
            )
            logging.info(f"{delay:.1f}秒後に再接続します...")
            time.sleep(delay)
            self._reconnect_attempts += 1

    def _on_ws_open(self, ws):
        """WebSocket接続確立"""
        logging.info("Yukacone WebSocketに接続しました")
        self._reconnect_attempts = 0

    def _on_ws_message(self, ws, message):
        """WebSocketメッセージ受信"""
        try:
            data = json.loads(message)
            logging.debug(f"翻訳データ受信: MessageID={data.get('MessageID')}")
            
            # コールバック呼び出し
            if self.on_translation_data:
                self.on_translation_data(data)
                
        except json.JSONDecodeError as e:
            logging.error(f"JSONデコードエラー: {e}")
        except Exception as e:
            logging.error(f"メッセージ処理エラー: {e}")

    def _on_ws_error(self, ws, error):
        """WebSocketエラー"""
        logging.error(f"Yukacone WebSocketエラー: {error}")

    def _on_ws_close(self, ws, close_status_code, close_msg):
        """WebSocket切断"""
        logging.warning(
            f"Yukacone WebSocket切断: code={close_status_code}, msg={close_msg}"
        )


# 使用例
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    
    # テスト用プロファイル
    profiles = [
        {
            "name": "日本語→英語",
            "recognition_language": "ja",
            "translation_param": {
                "slot": 1,
                "language": "en-US",
                "engine": "google"
            }
        },
        {
            "name": "日本語→中国語",
            "recognition_language": "ja",
            "translation_param": {
                "slot": 1,
                "language": "zh-CN",
                "engine": "google"
            }
        }
    ]
    
    def on_data(data):
        print(f"翻訳データ: {data}")
    
    def on_status():
        print(f"ステータス変更: Mute={client.is_muted}")
    
    # クライアント作成
    client = YukaconeClient(
        http_endpoint="http://127.0.0.1:15520/api",
        ws_endpoint="ws://127.0.0.1:15520/api",
        translation_profiles=profiles,
        on_translation_data=on_data,
        on_status_change=on_status
    )
    
    # 接続
    client.connect()
    
    # 初期設定
    time.sleep(2)
    client.set_translation_profile(0)
    client.set_mute(False)
    
    # メインループ
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        client.disconnect()
