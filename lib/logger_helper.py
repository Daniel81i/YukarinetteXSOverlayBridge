"""
汎用ログ設定ヘルパー

使い方:
    logger_mgr = LoggerManager("MyApp", debug=True)
    logger_mgr.setup()
    
    # 使用
    import logging
    logging.info("これは通常ログ")
    logging.debug("これはデバッグログ")
"""

import logging
import os
import sys
from datetime import datetime
from typing import Optional


class LoggerManager:
    """汎用ログ管理クラス"""
    
    def __init__(
        self,
        app_name: str,
        debug: bool = False,
        log_dir: str = "logs",
        console_output: bool = True,
        file_output: bool = True,
        log_format: Optional[str] = None
    ):
        """
        Args:
            app_name: アプリケーション名（ログファイル名に使用）
            debug: Trueならデバッグログも出力
            log_dir: ログディレクトリ（相対パスまたは絶対パス）
            console_output: コンソールに出力するか
            file_output: ファイルに出力するか
            log_format: カスタムログフォーマット
        """
        self.app_name = app_name
        self.debug = debug
        self.log_dir = log_dir
        self.console_output = console_output
        self.file_output = file_output
        
        # デフォルトフォーマット
        self.log_format = log_format or '%(asctime)s [%(levelname)s] %(message)s'
        
        self.log_file_path = None
        self._logger = None
    
    def _get_base_dir(self) -> str:
        """実行ファイルの基準ディレクトリを取得"""
        if getattr(sys, 'frozen', False):
            # PyInstallerで実行ファイル化されている場合
            return os.path.dirname(sys.executable)
        else:
            # 通常のPythonスクリプトとして実行されている場合
            return os.path.dirname(os.path.abspath(sys.argv[0]))
    
    def _create_log_dir(self) -> str:
        """ログディレクトリを作成"""
        base_dir = self._get_base_dir()
        
        # 絶対パスでなければ、base_dirからの相対パスとして扱う
        if not os.path.isabs(self.log_dir):
            log_path = os.path.join(base_dir, self.log_dir)
        else:
            log_path = self.log_dir
        
        if not os.path.exists(log_path):
            try:
                os.makedirs(log_path)
            except OSError as e:
                print(f"ログディレクトリ作成エラー: {e}")
                # フォールバック: カレントディレクトリ
                log_path = os.path.join(os.getcwd(), "logs")
                os.makedirs(log_path, exist_ok=True)
        
        return log_path
    
    def _generate_log_filename(self) -> str:
        """タイムスタンプ付きログファイル名を生成"""
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        return f"{self.app_name}_{timestamp}.log"
    
    def setup(self) -> str:
        """
        ログシステムをセットアップ
        
        Returns:
            ログファイルの絶対パス（file_output=Falseの場合はNone）
        """
        # ロガーを取得（ルートロガー）
        self._logger = logging.getLogger()
        self._logger.setLevel(logging.DEBUG if self.debug else logging.INFO)
        
        # 既存のハンドラーをクリア（重複を防ぐ）
        self._logger.handlers.clear()
        
        # フォーマッターを作成
        formatter = logging.Formatter(self.log_format)
        
        # ファイル出力
        if self.file_output:
            log_dir_path = self._create_log_dir()
            log_filename = self._generate_log_filename()
            self.log_file_path = os.path.join(log_dir_path, log_filename)
            
            try:
                file_handler = logging.FileHandler(
                    self.log_file_path,
                    encoding="utf-8"
                )
                file_handler.setLevel(logging.DEBUG if self.debug else logging.INFO)
                file_handler.setFormatter(formatter)
                self._logger.addHandler(file_handler)
            except Exception as e:
                print(f"ファイルハンドラー作成エラー: {e}")
        
        # コンソール出力
        if self.console_output:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            console_handler.setFormatter(formatter)
            self._logger.addHandler(console_handler)
        
        # セットアップ完了ログ
        logging.info(f"{self.app_name} ログシステム初期化完了")
        if self.log_file_path:
            logging.info(f"ログファイル: {self.log_file_path}")
        
        return self.log_file_path
    
    def get_log_file_path(self) -> Optional[str]:
        """ログファイルのパスを取得"""
        return self.log_file_path
    
    def add_custom_handler(self, handler: logging.Handler):
        """カスタムハンドラーを追加"""
        if self._logger:
            self._logger.addHandler(handler)
    
    @staticmethod
    def create_named_logger(
        name: str,
        log_file: str,
        level: int = logging.INFO,
        log_format: Optional[str] = None
    ) -> logging.Logger:
        """
        名前付きロガーを作成（データログなど専用ロガー用）
        
        Args:
            name: ロガー名
            log_file: ログファイルのパス
            level: ログレベル
            log_format: カスタムフォーマット
        
        Returns:
            設定済みのLogger
        """
        logger = logging.getLogger(name)
        logger.setLevel(level)
        logger.handlers.clear()  # 既存ハンドラークリア
        
        # フォーマッター
        fmt = log_format or '%(asctime)s %(message)s'
        formatter = logging.Formatter(fmt)
        
        # ファイルハンドラー
        try:
            handler = logging.FileHandler(log_file, encoding="utf-8")
            handler.setLevel(level)
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        except Exception as e:
            print(f"名前付きロガー作成エラー: {e}")
        
        return logger


# 使用例
if __name__ == "__main__":
    # 基本的な使い方
    logger_mgr = LoggerManager("TestApp", debug=True)
    logger_mgr.setup()
    
    # ログ出力テスト
    logging.debug("これはデバッグメッセージ")
    logging.info("これは情報メッセージ")
    logging.warning("これは警告メッセージ")
    logging.error("これはエラーメッセージ")
    
    # 専用ロガーの作成例（データログなど）
    data_logger = LoggerManager.create_named_logger(
        name="data_logger",
        log_file="logs/data_log.log",
        level=logging.INFO,
        log_format='%(asctime)s %(message)s'
    )
    
    data_logger.info("これは専用ロガーのメッセージ")
