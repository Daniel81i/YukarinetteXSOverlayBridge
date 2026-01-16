"""
メディアキー制御モジュール

メディアキー（再生/一時停止、次へ、前へ）を監視し、
翻訳設定やミュート状態を制御する
"""

import logging
import threading
from typing import Optional, Callable
from pynput import keyboard


class MediaKeyController:
    """メディアキーで翻訳を制御するコントローラー"""
    
    def __init__(
        self,
        yukacone_client,
        xso_client,
        on_status_change: Optional[Callable[[], None]] = None
    ):
        """
        Args:
            yukacone_client: YukaconeClientインスタンス
            xso_client: XSOClientインスタンス
            on_status_change: ステータス変更時のコールバック
        """
        self.yukacone = yukacone_client
        self.xso = xso_client
        self.on_status_change = on_status_change
        
        self._listener = None
        self._is_running = False

    # ----------------------------------------
    # 公開API
    # ----------------------------------------
    def start(self):
        """メディアキー監視を開始"""
        if self._is_running:
            logging.warning("MediaKeyController は既に起動しています")
            return
        
        self._is_running = True
        
        self._listener = keyboard.Listener(on_press=self._on_key_press)
        self._listener.start()
        
        logging.info("メディアキー監視を開始しました")

    def stop(self):
        """メディアキー監視を停止"""
        if not self._is_running:
            return
        
        self._is_running = False
        
        if self._listener:
            self._listener.stop()
            self._listener = None
        
        logging.info("メディアキー監視を停止しました")

    # ----------------------------------------
    # 内部処理
    # ----------------------------------------
    def _on_key_press(self, key):
        """キー押下時のハンドラー"""
        try:
            if key == keyboard.Key.media_play_pause:
                self._handle_play_pause()
            elif key == keyboard.Key.media_next:
                self._handle_next()
            elif key == keyboard.Key.media_previous:
                self._handle_previous()
                
        except Exception as e:
            logging.error(f"メディアキー処理エラー: {e}")

    def _handle_play_pause(self):
        """再生/一時停止キーの処理"""
        logging.info("メディアキー: 再生/一時停止")
        
        # ミュート状態をトグル
        success = self.yukacone.toggle_mute()
        
        if success:
            # XSOに状態を送信
            profile = self.yukacone.get_current_profile()
            if profile:
                self.xso.send_status(profile, self.yukacone.is_muted)
            
            # コールバック呼び出し
            if self.on_status_change:
                self.on_status_change()

    def _handle_next(self):
        """次へキーの処理"""
        logging.info("メディアキー: 次へ")
        
        # 次のプロファイルに切り替え
        success = self.yukacone.next_profile()
        
        if success:
            # ミュート解除
            self.yukacone.set_mute(False)
            
            # XSOに状態を送信
            profile = self.yukacone.get_current_profile()
            if profile:
                self.xso.send_status(profile, self.yukacone.is_muted)
            
            # コールバック呼び出し
            if self.on_status_change:
                self.on_status_change()

    def _handle_previous(self):
        """前へキーの処理"""
        logging.info("メディアキー: 前へ")
        
        # 前のプロファイルに切り替え
        success = self.yukacone.previous_profile()
        
        if success:
            # ミュート解除
            self.yukacone.set_mute(False)
            
            # XSOに状態を送信
            profile = self.yukacone.get_current_profile()
            if profile:
                self.xso.send_status(profile, self.yukacone.is_muted)
            
            # コールバック呼び出し
            if self.on_status_change:
                self.on_status_change()


# 使用例
if __name__ == "__main__":
    import time
    logging.basicConfig(level=logging.DEBUG)
    
    # ダミークライアント（テスト用）
    class DummyYukacone:
        def __init__(self):
            self.is_muted = True
            self.profile_index = 0
            self.profiles = [
                {"name": "JP->EN", "translation_param": {"engine": "google"}},
                {"name": "JP->CN", "translation_param": {"engine": "google"}}
            ]
        
        def toggle_mute(self):
            self.is_muted = not self.is_muted
            print(f"Mute: {self.is_muted}")
            return True
        
        def next_profile(self):
            self.profile_index = (self.profile_index + 1) % len(self.profiles)
            print(f"Profile: {self.profiles[self.profile_index]['name']}")
            return True
        
        def previous_profile(self):
            self.profile_index = (self.profile_index - 1) % len(self.profiles)
            print(f"Profile: {self.profiles[self.profile_index]['name']}")
            return True
        
        def set_mute(self, muted):
            self.is_muted = muted
            return True
        
        def get_current_profile(self):
            return self.profiles[self.profile_index]
    
    class DummyXSO:
        def send_status(self, profile, is_muted):
            print(f"XSO: {profile['name']} - {'Mute' if is_muted else 'Online'}")
    
    yukacone = DummyYukacone()
    xso = DummyXSO()
    
    def on_change():
        print("ステータス変更!")
    
    # コントローラー作成
    controller = MediaKeyController(yukacone, xso, on_change)
    controller.start()
    
    print("メディアキーをテストしてください（Ctrl+Cで終了）")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        controller.stop()
