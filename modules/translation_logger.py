"""
翻訳ログ管理モジュール

Yukacone WebSocketから受信した翻訳データを
一定時間安定した後にログファイルに出力する
"""

import os
import json
import time
import threading
import logging
from datetime import datetime
from typing import Optional, Dict, Any, Callable


class TranslationLogger:
    """
    翻訳ログを管理するクラス
    
    - ./log/translation-YYYY-MM-DD-HHMMSS.log に追記
    - MessageID が一定時間変化しなかったら1行として確定
    """

    def __init__(
        self,
        base_dir: str,
        stable_sec: float = 10.0,
        flush_interval: float = 1.0,
        log_subdir: str = "log",
        on_message_logged: Optional[Callable[[Dict], None]] = None
    ):
        """
        Args:
            base_dir: ベースディレクトリ
            stable_sec: 何秒更新が止まったら確定とみなすか
            flush_interval: 何秒おきに安定チェックするか
            log_subdir: ログサブディレクトリ名
            on_message_logged: メッセージ確定時のコールバック
        """
        self.log_dir = os.path.join(base_dir, log_subdir)
        os.makedirs(self.log_dir, exist_ok=True)

        ts = datetime.now().strftime("%Y-%m-%d-%H%M%S")
        self.log_filename = f"translation-{ts}.log"

        self.stable_sec = stable_sec
        self.flush_interval = flush_interval
        self.on_message_logged = on_message_logged

        self.current_id = None
        self.last_data = None
        self.last_update_time = None

        self._lock = threading.Lock()
        self._stop = False
        self._thread = None

    # ----------------------------------------
    # 公開API
    # ----------------------------------------
    def start(self):
        """バックグラウンドで安定チェック用スレッドを開始"""
        if self._thread is not None:
            logging.warning("TranslationLogger は既に起動しています")
            return
        
        self._stop = False
        self._thread = threading.Thread(target=self._periodic_flush_loop, daemon=True)
        self._thread.start()
        logging.info("TranslationLogger を起動しました")

    def stop(self):
        """スレッド停止＆残りのメッセージを強制フラッシュ"""
        if self._thread is None:
            return
        
        self._stop = True
        
        # スレッドの終了を待つ
        if self._thread.is_alive():
            self._thread.join(timeout=3.0)
        
        # 残っているメッセージを出力
        with self._lock:
            self._flush_locked()
        
        logging.info("TranslationLogger を停止しました")

    def add_yukacone_message(self, data: dict):
        """
        Yukacone WebSocket から受け取った JSON（MessageID, textList 等）を
        Logger 用の内部形式に変換してバッファに追加する
        
        Args:
            data: Yukaconeから受信したJSONデータ
        """
        converted = self._convert_to_internal_format(data)
        if not converted:
            return

        self._add_message_internal(converted)

    def flush_now(self):
        """即座に現在のメッセージを確定して出力"""
        with self._lock:
            self._flush_locked()

    def get_log_file_path(self) -> str:
        """ログファイルのフルパスを取得"""
        return os.path.join(self.log_dir, self.log_filename)

    # ----------------------------------------
    # 内部処理
    # ----------------------------------------
    def _convert_to_internal_format(self, data: dict) -> Optional[Dict[str, Any]]:
        """
        {MessageID, textList, ...} → {MsgID, Lang1, Text1, Lang2, Text2}
        という形に変換する

        Args:
            data: Yukaconeから受信したデータ

        Returns:
            変換後のデータ、または変換不可能な場合はNone
        """
        msg_id = data.get("MessageID")
        if msg_id is None:
            logging.debug("MessageID が含まれていないデータを受信しました")
            return None

        text_list = data.get("textList") or []
        if len(text_list) < 2:
            # 2言語揃っていない場合はログ対象外
            logging.debug(f"textList が不足しています: {len(text_list)}言語")
            return None

        # textList = [{ "Lang": "ja", "Text": "こんにちは" }, { "Lang": "en", "Text": "Hello" }]
        lang1 = text_list[0].get("Lang", "")
        text1 = text_list[0].get("Text", "")
        lang2 = text_list[1].get("Lang", "")
        text2 = text_list[1].get("Text", "")

        return {
            "MsgID": msg_id,
            "Lang1": lang1,
            "Text1": text1,
            "Lang2": lang2,
            "Text2": text2,
        }

    def _add_message_internal(self, msg: dict):
        """
        内部形式のメッセージをバッファに追加
        
        Args:
            msg: 内部形式のメッセージ
        """
        msg_id = msg.get("MsgID")
        if msg_id is None:
            logging.warning("内部メッセージに MsgID がありません")
            return

        now = time.time()
        with self._lock:
            if self.current_id is None:
                # 初回
                self.current_id = msg_id
                self.last_data = msg
                self.last_update_time = now
                logging.debug(f"新規メッセージ受信: MsgID={msg_id}")
                return

            if msg_id != self.current_id:
                # 別IDが来た → 旧IDを確定してから新IDに切り替え
                logging.debug(f"MessageID変更: {self.current_id} → {msg_id}")
                self._flush_locked()
                self.current_id = msg_id
                self.last_data = msg
                self.last_update_time = now
            else:
                # 同じIDの更新 → 最新に差し替え
                self.last_data = msg
                self.last_update_time = now
                logging.debug(f"メッセージ更新: MsgID={msg_id}")

    def _periodic_flush_loop(self):
        """定期的に安定チェックを行うループ"""
        while not self._stop:
            time.sleep(self.flush_interval)
            
            with self._lock:
                if self.current_id is None or self.last_update_time is None:
                    continue

                now = time.time()
                elapsed = now - self.last_update_time
                
                if elapsed >= self.stable_sec:
                    # 一定時間更新が止まっていれば確定
                    logging.debug(f"安定時間経過({elapsed:.1f}秒): MsgID={self.current_id}")
                    self._flush_locked()

    def _flush_locked(self):
        """
        現在のメッセージを確定してログファイルに出力
        
        注意: この関数は _lock を取得した状態で呼ばれる前提
        """
        if not self.last_data:
            return

        timestamp = datetime.now().strftime("%Y%m%d-%H:%M:%S.%f")[:-3]
        lang1 = self.last_data.get("Lang1", "")
        text1 = self.last_data.get("Text1", "")
        lang2 = self.last_data.get("Lang2", "")
        text2 = self.last_data.get("Text2", "")

        line = f"{timestamp},{lang1}:{text1},{lang2}:{text2}"

        log_path = os.path.join(self.log_dir, self.log_filename)
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
            logging.info(f"[TranslationLog] {line}")
        except Exception as e:
            logging.error(f"翻訳ログ書き込みエラー: {e}")

        # コールバック呼び出し
        if self.on_message_logged:
            try:
                self.on_message_logged(self.last_data)
            except Exception as e:
                logging.error(f"on_message_logged コールバックエラー: {e}")

        # 状態リセット
        self.current_id = None
        self.last_data = None
        self.last_update_time = None


# 使用例
if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.DEBUG)
    
    def on_logged(data):
        print(f"確定されたメッセージ: {data['MsgID']}")
    
    # ロガー作成
    logger = TranslationLogger(
        base_dir=".",
        stable_sec=3.0,
        flush_interval=0.5,
        on_message_logged=on_logged
    )
    logger.start()
    
    # テストデータ送信
    test_data = {
        "MessageID": "msg001",
        "textList": [
            {"Lang": "ja", "Text": "こんにちは"},
            {"Lang": "en", "Text": "Hello"}
        ]
    }
    
    # 同じIDで複数回送信（更新）
    for i in range(3):
        test_data["textList"][1]["Text"] = f"Hello {i}"
        logger.add_yukacone_message(test_data)
        time.sleep(1)
    
    # 新しいID
    test_data["MessageID"] = "msg002"
    test_data["textList"][0]["Text"] = "さようなら"
    test_data["textList"][1]["Text"] = "Goodbye"
    logger.add_yukacone_message(test_data)
    
    time.sleep(5)
    logger.stop()
