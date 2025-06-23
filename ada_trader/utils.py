#utils.py
import os
import requests
import logging
import ccxt
import json
from datetime import datetime

from ada_trader.config import SLACK_WEBHOOK_URL

def save_state(state):
    """현재 봇의 상태를 state.json 파일에 저장합니다."""
    try:
        with open("state.json", "w") as f:
            json.dump(state, f, indent=4, default=str)
        logging.info("💾 상태 정보가 state.json 파일에 저장되었습니다.")
    except Exception as e:
        logging.error(f"❌ 상태 저장 실패: {e}")

def load_state():
    """state.json 파일에서 봇의 상태를 불러옵니다."""
    if os.path.exists("state.json"):
        try:
            with open("state.json", "r") as f:
                logging.info("💾 state.json 파일에서 상태 정보를 불러옵니다.")
                return json.load(f)
        except Exception as e:
            logging.error(f"❌ 상태 불러오기 실패: {e}")
            return None
    return None

def send_slack_message(message):
    """Slack으로 메시지를 전송합니다."""
    if not SLACK_WEBHOOK_URL:
        return
    try:
        requests.post(SLACK_WEBHOOK_URL, json={"text": message}, timeout=5)
    except Exception as e:
        logging.error(f"❌ Slack 메시지 전송 실패: {e}")

def get_position_risk(binance, symbol):
    """현재 포지션 정보를 가져옵니다."""
    try:
        positions = binance.fetch_positions([symbol])
        return [p['info'] for p in positions if p.get('contracts') is not None and float(p['info']['positionAmt']) != 0]
    except Exception as e:
        logging.error(f"❌ 포지션 조회 중 오류 ({symbol}): {e}")
        return []

def log_trade_record(symbol, side, timestamp, entry_price=None, stop_loss=None, take_profit=None, 
                        pnl=None, holding_time=None, exit_reason=None, entry_context=None):
    """거래 기록을 CSV 파일에 저장합니다."""
    file_path = "trade_history.csv"
    header = "timestamp,symbol,side,entry_price,stop_loss,take_profit,pnl,holding_time_minutes,exit_reason,entry_context\n"
    
    try:
        if not os.path.exists(file_path):
            with open(file_path, "w", encoding="utf-8", newline='') as f:
                f.write(header)
        
        trade_time = datetime.fromtimestamp(timestamp / 1000).strftime('%Y-%m-%d %H:%M:%S')
        context_str = json.dumps(entry_context) if isinstance(entry_context, dict) else ''
        tp_str = f"{take_profit:.4f}" if take_profit is not None else "Trailing"

        with open(file_path, "a", encoding="utf-8", newline='') as f:
            if exit_reason:
                f.write(f"{trade_time},{symbol},{side},,,,,{pnl or ''},{holding_time or ''},{exit_reason or ''},\n")
                logging.info(f"✍️  [청산 기록] {symbol} | 사유: {exit_reason} | PnL: {pnl:.4f}")
            else:
                f.write(f"{trade_time},{symbol},{side},{entry_price},{stop_loss},{tp_str},,,,{context_str}\n")
                logging.info(f"✍️  [진입 기록] {symbol} | {side.upper()} | 진입: {entry_price}")
    except Exception as e:
        logging.error(f"❌ CSV 거래 기록 저장 실패: {e}")