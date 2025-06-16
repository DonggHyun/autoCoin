# utils.py

import os
import requests
import logging
import ccxt
from datetime import datetime
from ada_trader.config import SLACK_WEBHOOK_URL

def send_slack_message(message):
    if not SLACK_WEBHOOK_URL:
        logging.warning("Slack Webhook URL이 설정되지 않았습니다. 메시지 전송을 건너뜁니다.")
        return
    try:
        requests.post(SLACK_WEBHOOK_URL, json={"text": message}, timeout=5)
    except Exception as e:
        logging.error(f"❌ Slack 메시지 전송 실패: {e}")

def get_position_risk(binance, symbol):
    """ 💡 ccxt 공식 통합 API 메소드인 fetch_positions를 사용하도록 수정 """
    try:
        # fetch_positions는 심볼 리스트를 인자로 받습니다.
        positions = binance.fetch_positions([symbol])
        
        # fetch_positions는 통일된 형식으로 데이터를 반환합니다.
        # 이전 코드와의 호환성을 위해, 실제 데이터가 있는 info 부분을 추출합니다.
        # 포지션 수량이 0이 아닌 경우(실제 포지션이 있는 경우)만 필터링합니다.
        active_positions_info = [p['info'] for p in positions if p.get('contracts') is not None and p['contracts'] != 0]
        
        return active_positions_info

    except ccxt.ExchangeError as e:
        logging.error(f"❌ [API Error] 포지션 조회 실패 ({symbol}): {e}")
        return []
    except Exception as e:
        logging.error(f"❌ [General Error] 포지션 조회 중 예상치 못한 오류 ({symbol}): {e}")
        return []

def log_trade_record(symbol, side, entry_price, stop_loss, take_profit, timestamp):
    file_path = "trade_history.csv"
    try:
        if not os.path.exists(file_path):
            with open(file_path, "w", encoding="utf-8", newline='') as f:
                f.write("trade_time,symbol,side,entry_price,stop_loss,take_profit\n")
        
        trade_time = datetime.fromtimestamp(timestamp / 1000).strftime('%Y-%m-%d %H:%M:%S')
        with open(file_path, "a", encoding="utf-8", newline='') as f:
            f.write(f"{trade_time},{symbol},{side},{entry_price},{stop_loss},{take_profit}\n")
        logging.info(f"✍️ [거래 기록] {symbol} | {side.upper()} | 진입: {entry_price}")
    except Exception as e:
        logging.error(f"❌ CSV 거래 기록 저장 실패: {e}")