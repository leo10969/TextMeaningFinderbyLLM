#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import threading
import time
import json
import pyperclip
import rumps
import google.generativeai as genai
import requests
from dotenv import load_dotenv
from pynput import keyboard
from pynput import mouse

# .envファイルから環境変数を読み込む
load_dotenv(override=True)  # 既存の環境変数を上書き

# Google Gemini API設定
API_KEY = os.getenv("API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-pro")

# キーボードショートカット設定
SHORTCUT_KEY = os.getenv("SHORTCUT_KEY", ",")  # デフォルトはカンマ
SHORTCUT_MODIFIER = os.getenv("SHORTCUT_MODIFIER", "cmd+shift").split("+")
TRANSLATE_SHORTCUT_KEY = "."  # 翻訳モード用のショートカットキー

# デバッグモード
DEBUG = True

# 動作モード
MODE_MEANING = "meaning"  # 意味解析モード
MODE_TRANSLATE = "translate"  # 翻訳モード

def debug_print(message):
    """デバッグメッセージを出力"""
    if DEBUG:
        print(f"[DEBUG] {message}")

# 環境変数の読み込み結果をデバッグ出力
debug_print("環境変数を読み込みました")
debug_print(f"SHORTCUT_KEY: {SHORTCUT_KEY}")
debug_print(f"SHORTCUT_MODIFIER: {SHORTCUT_MODIFIER}")

def show_notification(title, message, sound=False):
    """macOSの通知を表示"""
    # メッセージ内の特殊文字をエスケープ
    message = message.replace('"', '\\"').replace("'", "\\'")
    title = title.replace('"', '\\"').replace("'", "\\'")
    
    # 通知コマンドを構築
    cmd = f'osascript -e \'display notification "{message}" with title "{title}"\''
    
    # サウンドを追加（オプション）
    if sound:
        os.system('osascript -e "beep"')
    
    # 通知を表示
    os.system(cmd)

def show_result(title, message):
    """結果をmacOSのダイアログで表示"""
    try:
        # 特殊文字をエスケープ
        message = message.replace('"', '\\"').replace("'", "\\'")
        title = title.replace('"', '\\"').replace("'", "\\'")
        
        # ダイアログを直接表示
        cmd = f'''osascript -e 'display dialog "{message}" with title "{title}" buttons {{"OK"}} default button "OK" with icon note' '''
        os.system(cmd)
    except Exception as e:
        debug_print(f"結果の表示でエラーが発生しました: {e}")
        show_notification(
            "表示エラー",
            "結果の表示中にエラーが発生しました。",
            sound=True
        )

class TextMeaningFinderApp(rumps.App):
    def __init__(self):
        super(TextMeaningFinderApp, self).__init__(
            "意味検索/翻訳", 
            icon=None
        )
        
        # 現在のモードを設定
        self.current_mode = MODE_MEANING
        
        # Geminiモデルの初期化
        self.setup_llm_model()
        
        # メニューの設定
        self.menu = [
            rumps.MenuItem("選択したテキストの意味を調べる", callback=self.get_meaning),
            rumps.MenuItem("選択したテキストを翻訳する", callback=self.get_translation),
            None,  # セパレータ
            rumps.MenuItem("モード切替", [
                rumps.MenuItem("意味解析モード", callback=self.switch_to_meaning_mode),
                rumps.MenuItem("翻訳モード", callback=self.switch_to_translate_mode)
            ]),
            rumps.MenuItem("設定", callback=self.show_settings),
            rumps.MenuItem("終了", callback=self.quit_app)
        ]
        
        # キーボードリスナーの初期化
        self.setup_keyboard_listener()
        
        debug_print("アプリケーションを初期化しました")
        debug_print(f"ショートカットキー: Command + Shift + {SHORTCUT_KEY}")
        debug_print(f"必要なモディファイアキー: {SHORTCUT_MODIFIER}")
        debug_print(f"初期モード: {self.current_mode}")
    
    def setup_llm_model(self):
        """LLMモデルの初期化"""
        try:
            # Google Gemini APIの設定
            genai.configure(api_key=API_KEY)
            
            # モデルの生成とパラメータ設定
            generation_config = {
                "temperature": 0.3,
                "top_p": 0.8,
                "top_k": 20,
                "max_output_tokens": 200,
            }
            safety_settings = [
                {
                    "category": "HARM_CATEGORY_HARASSMENT",
                    "threshold": "BLOCK_NONE"
                },
                {
                    "category": "HARM_CATEGORY_HATE_SPEECH",
                    "threshold": "BLOCK_NONE"
                },
                {
                    "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    "threshold": "BLOCK_NONE"
                },
                {
                    "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                    "threshold": "BLOCK_NONE"
                },
            ]
            self.model = genai.GenerativeModel(
                GEMINI_MODEL,
                generation_config=generation_config,
                safety_settings=safety_settings
            )
            debug_print("LLMモデルを初期化しました")
        except Exception as e:
            debug_print(f"LLMモデルの初期化でエラーが発生しました: {e}")
            show_notification(
                "初期化エラー",
                "LLMモデルの初期化に失敗しました",
                sound=True
            )
    
    def setup_keyboard_listener(self):
        """キーボードショートカットのリスナーを設定"""
        try:
            # モディファイアキーのマッピング
            modifier_map = {
                "cmd": keyboard.Key.cmd,
                "shift": keyboard.Key.shift,
                "ctrl": keyboard.Key.ctrl,
                "alt": keyboard.Key.alt
            }
            
            # モディファイアキーのセットを作成
            self.required_modifiers = set()
            for mod in SHORTCUT_MODIFIER:
                if mod in modifier_map:
                    self.required_modifiers.add(modifier_map[mod])
            
            debug_print(f"必要なモディファイアキー: {self.required_modifiers}")
            
            # 現在押されているキーを追跡
            self.current_modifiers = set()
            
            # キーボードリスナーを別スレッドで開始
            self.listener = keyboard.Listener(
                on_press=self.on_key_press,
                on_release=self.on_key_release
            )
            self.listener.start()
            debug_print("キーボードリスナーを開始しました")
        except Exception as e:
            print(f"キーボードリスナーの初期化でエラーが発生しました: {e}")
    
    def on_key_press(self, key):
        """キーが押されたときの処理"""
        try:
            # 特殊なキーイベントは無視
            if isinstance(key, keyboard.KeyCode) and key.vk in [0, 255]:
                return
            
            debug_print(f"キーが押されました: {key}")
            
            # モディファイアキーを記録
            if key in self.required_modifiers:
                self.current_modifiers.add(key)
                debug_print(f"現在のモディファイアキー: {self.current_modifiers}")
            
            # ショートカットキーの確認
            is_meaning_shortcut = False
            is_translate_shortcut = False
            
            if hasattr(key, 'char'):
                is_meaning_shortcut = (key.char == SHORTCUT_KEY)
                is_translate_shortcut = (key.char == TRANSLATE_SHORTCUT_KEY)
                debug_print(f"文字キーの比較（意味）: {key.char} == {SHORTCUT_KEY} -> {is_meaning_shortcut}")
                debug_print(f"文字キーの比較（翻訳）: {key.char} == {TRANSLATE_SHORTCUT_KEY} -> {is_translate_shortcut}")
            elif hasattr(key, 'vk'):
                if key.vk == 44:  # カンマのvirtual keycode
                    is_meaning_shortcut = True
                    debug_print("カンマキーを検出しました（virtual keycode）")
                elif key.vk == 46:  # ピリオドのvirtual keycode
                    is_translate_shortcut = True
                    debug_print("ピリオドキーを検出しました（virtual keycode）")
            
            # モディファイアキーとショートカットキーの組み合わせをチェック
            if self.required_modifiers.issubset(self.current_modifiers):
                if is_meaning_shortcut:
                    debug_print("意味解析ショートカットキーの組み合わせを検出しました")
                    self.current_mode = MODE_MEANING
                    threading.Thread(target=self.process_text).start()
                elif is_translate_shortcut:
                    debug_print("翻訳ショートカットキーの組み合わせを検出しました")
                    self.current_mode = MODE_TRANSLATE
                    threading.Thread(target=self.process_text).start()
        except Exception as e:
            print(f"キー処理でエラーが発生しました: {e}")
    
    def on_key_release(self, key):
        """キーが離されたときの処理"""
        try:
            # 特殊なキーイベントは無視
            if isinstance(key, keyboard.KeyCode) and key.vk in [0, 255]:
                return
            
            debug_print(f"キーが離されました: {key}")
            
            # モディファイアキーを削除
            if key in self.current_modifiers:
                self.current_modifiers.remove(key)
                debug_print(f"現在のモディファイアキー: {self.current_modifiers}")
        except Exception as e:
            print(f"キー処理でエラーが発生しました: {e}")
    
    def switch_to_meaning_mode(self, _):
        """意味解析モードに切り替え"""
        self.current_mode = MODE_MEANING
        debug_print(f"モードを切り替えました: {self.current_mode}")
        show_notification("モード切替", "意味解析モードに切り替えました")

    def switch_to_translate_mode(self, _):
        """翻訳モードに切り替え"""
        self.current_mode = MODE_TRANSLATE
        debug_print(f"モードを切り替えました: {self.current_mode}")
        show_notification("モード切替", "翻訳モードに切り替えました")

    def get_translation(self, _):
        """選択したテキストを翻訳"""
        self.current_mode = MODE_TRANSLATE
        self.process_text()

    def get_meaning(self, _):
        """選択したテキストの意味を取得"""
        self.current_mode = MODE_MEANING
        self.process_text()

    def process_text(self):
        """テキスト処理のメイン関数"""
        try:
            debug_print("テキストの処理を開始します")
            
            # 選択テキストをコピー（Command+C）とクリップボードから取得
            keyboard_controller = keyboard.Controller()
            try:
                # Command+Cを実行
                keyboard_controller.press(keyboard.Key.cmd)
                keyboard_controller.press('c')
                keyboard_controller.release('c')
                keyboard_controller.release(keyboard.Key.cmd)
                
                # クリップボードの内容が更新されるまで少し待機
                time.sleep(0.1)  # 100ミリ秒待機
                
                # クリップボードから選択テキストを取得
                selected_text = pyperclip.paste().strip()
                
                if not selected_text:
                    debug_print("テキストが選択されていません")
                    show_notification(
                        "テキスト未選択",
                        "テキストを選択してからショートカットキーを押してください",
                        sound=True
                    )
                    return
                
                # 選択テキストを変数に保存
                text_to_process = selected_text
                
                # LLM処理を開始
                threading.Thread(target=self.query_llm, args=(text_to_process,)).start()
                
            except Exception as e:
                debug_print(f"テキスト処理でエラーが発生しました: {e}")
                show_notification(
                    "エラー",
                    "テキストの処理中にエラーが発生しました",
                    sound=True
                )
        except Exception as e:
            debug_print(f"テキスト処理でエラーが発生しました: {e}")
            show_notification(
                "エラー",
                "テキストの処理中にエラーが発生しました",
                sound=True
            )
    
    def query_llm(self, text):
        """Google Gemini APIを使ってテキストを処理"""
        try:
            debug_print("LLMに問い合わせを開始します")
            
            # モードに応じてプロンプトを設定
            if self.current_mode == MODE_TRANSLATE:
                prompt = f"""
                次のテキストについて、以下の2点を出力してください：
                1. 日本語訳
                2. 重要な単語や表現の類似語/同義語（英語で3-5個）

                テキスト：
                {text}

                出力形式：
                【日本語訳】
                （翻訳文）

                【Similar Expressions】
                ・(synonym/related word 1)
                ・(synonym/related word 2)
                ・(synonym/related word 3)
                """
                title = "翻訳結果と類似表現"
            else:
                prompt = f"""
                次のテキストの内容を、50-100文字程度の日本語で簡潔に説明してください。
                専門用語がある場合は、その短い説明も含めてください。

                テキスト：
                {text}
                """
                title = "テキストの要約"
            
            # 応答の生成
            response = self.model.generate_content(prompt)
            result = response.text.strip()
            
            # 結果をダイアログで表示
            show_result(title, result)
        except Exception as e:
            error_message = str(e)
            debug_print(f"LLMの処理でエラーが発生しました: {error_message}")
            show_notification(
                "エラー",
                f"処理中にエラーが発生しました: {error_message}",
                sound=True
            )
    
    def show_settings(self, _):
        """設定画面を表示（将来的に実装）"""
        rumps.alert(
            title="設定",
            message="設定画面は現在開発中です。\n\n.envファイルを編集して設定を変更できます。",
            ok="OK"
        )
    
    def quit_app(self, _):
        """アプリケーションを終了"""
        debug_print("アプリケーションを終了します")
        # キーボードリスナーを停止
        if hasattr(self, 'listener'):
            self.listener.stop()
        rumps.quit_application()


if __name__ == "__main__":
    # Google Gemini APIキーが設定されているか確認
    if not API_KEY:
        show_notification(
            "設定エラー",
            "Google Gemini APIキーが設定されていません。.envファイルを確認してください。",
            sound=True
        )
        sys.exit(1)
    
    debug_print("アプリケーションを起動します")
    # アプリケーションを起動
    TextMeaningFinderApp().run() 