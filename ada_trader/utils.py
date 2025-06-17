import os
import requests
import logging
import ccxt
import json
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
    try:
        positions = binance.fetch_positions([symbol])
        active_positions_info = [p['info'] for p in positions if p.get('contracts') is not None and float(p['info']['positionAmt']) != 0]
        return active_positions_info
    except ccxt.ExchangeError as e:
        logging.error(f"❌ [API Error] 포지션 조회 실패 ({symbol}): {e}")
        return []
    except Exception as e:
        logging.error(f"❌ [General Error] 포지션 조회 중 예상치 못한 오류 ({symbol}): {e}")
        return []

def log_trade_record(symbol, side, timestamp, entry_price=None, stop_loss=None, take_profit=None, 
                     pnl=None, holding_time=None, exit_reason=None, entry_context=None):
    """
    [전면 수정] 거래 기록을 CSV 파일에 저장합니다. 진입과 청산 기록을 모두 처리합니다.
    """
    file_path = "trade_history.csv"
    header = "timestamp,symbol,side,entry_price,stop_loss,take_profit,pnl,holding_time_minutes,exit_reason,entry_context\n"
    
    try:
        if not os.path.exists(file_path):
            with open(file_path, "w", encoding="utf-8", newline='') as f:
                f.write(header)
        
        trade_time = datetime.fromtimestamp(timestamp / 1000).strftime('%Y-%m-%d %H:%M:%S')
        
        # entry_context가 dict 형태일 경우 json 문자열로 변환
        context_str = json.dumps(entry_context) if isinstance(entry_context, dict) else ''

        with open(file_path, "a", encoding="utf-8", newline='') as f:
            # exit_reason이 있으면 청산 기록, 없으면 진입 기록
            if exit_reason:
                f.write(f"{trade_time},{symbol},{side},,,,,{pnl or ''},{holding_time or ''},{exit_reason or ''},\n")
                logging.info(f"✍️  [청산 기록] {symbol} | 사유: {exit_reason} | PnL: ${pnl:.4f}")
            else:
                f.write(f"{trade_time},{symbol},{side},{entry_price},{stop_loss},{take_profit},,,,{context_str}\n")
                logging.info(f"✍️  [진입 기록] {symbol} | {side.upper()} | 진입: {entry_price}")
                
    except Exception as e:
        logging.error(f"❌ CSV 거래 기록 저장 실패: {e}")