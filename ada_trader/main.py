# main.py

import ccxt
import os
import pandas as pd
import logging
import time
from datetime import datetime, timezone
from dotenv import load_dotenv

from ada_trader.config import *
from ada_trader.indicators import apply_indicators_multi
from ada_trader.strategy import check_entry_signal
from ada_trader.trader import execute_trade
from ada_trader.utils import get_position_risk, send_slack_message, log_trade_record

# --- 1. 초기 설정 ---
log_level_map = {"DEBUG": logging.DEBUG, "INFO": logging.INFO}
logging.basicConfig(level=log_level_map.get(LOG_LEVEL.upper(), logging.INFO), format='%(asctime)s %(levelname)s:%(message)s', handlers=[logging.FileHandler(f'logs/{datetime.now().strftime("%Y-%m-%d")}.log', encoding='utf-8'), logging.StreamHandler()])

load_dotenv()
binance = ccxt.binance({'apiKey': API_KEY, 'secret': API_SECRET, 'enableRateLimit': True, 'options': {'defaultType': 'future'}})

# ✅마켓 정보를 미리 로드합니다.
try:
    binance.load_markets()
    logging.info("✅ 바이낸스 마켓 정보 로딩 성공.")
except Exception as e:
    logging.critical(f"❌ 바이낸스 마켓 정보 로딩 실패: {e}. 프로그램을 종료합니다.")
    exit()

symbols = ['XRP/USDT', 'SOL/USDT', 'ETH/USDT']
position_lock = {symbol: False for symbol in symbols}
state = {symbol: {'last_signal': None, 'last_timestamp': 0} for symbol in symbols}

for s in symbols:
    market = binance.market(s)
    try:
        binance.fapiPrivatePostLeverage({'symbol': market['id'], 'leverage': LEVERAGE})
        logging.info(f"✅ [{market['id']}] 레버리지 {LEVERAGE}배 설정")
        binance.fapiPrivatePostMarginType({'symbol': market['id'], 'marginType': 'ISOLATED'})
        logging.info(f"✅ [{market['id']}] 격리(ISOLATED) 모드 설정")
    except Exception as e:
        if "No need to change" in str(e): logging.info(f"ℹ️ [{market['id']}] 설정 변경 필요 없음")
        else: logging.error(f"❌ [{market['id']}] 초기 설정 오류: {e}")

# --- 2. 헬퍼 함수 정의 ---
def fetch_candles(symbol, timeframes=['1m', '15m'], limit=200):
    data = {}
    for tf in timeframes:
        try:
            ohlcv = binance.fetch_ohlcv(symbol, timeframe=tf, limit=limit)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            data[tf] = df
        except Exception: data[tf] = pd.DataFrame()
    return data

def get_order_amount(symbol, entry_price, stop_loss, risk_percent, num_symbols):
    try:
        total_balance = binance.fetch_balance({'type': 'future'})['total']['USDT']
        capital_per_trade = total_balance / num_symbols
        allowed_risk_usdt = capital_per_trade * risk_percent
        price_diff = abs(entry_price - stop_loss)
        if price_diff == 0: return 0
        amount = allowed_risk_usdt / price_diff
        position_value = amount * entry_price
        required_margin = position_value / LEVERAGE
        if required_margin > capital_per_trade:
            logging.warning(f"⚠️ [{symbol}] 계산된 증거금(${required_margin:.2f}) > 할당 자본(${capital_per_trade:.2f})")
            amount = (capital_per_trade * LEVERAGE) / entry_price
            logging.info(f"💡 [{symbol}] 주문량을 할당 자본 최대치로 재조정 -> {amount:.4f}")
        min_notional = binance.market(symbol)['limits']['cost']['min']
        if (amount * entry_price) < min_notional:
            logging.error(f"❌ [{symbol}] 최종 주문액(${(amount * entry_price):.2f}) < 최소 주문액(${min_notional})")
            return 0
        return float(binance.amount_to_precision(symbol, amount))
    except Exception as e:
        logging.error(f"❌ [{symbol}] 주문 수량 계산 오류: {e}")
        return 0

def update_trailing_stop(symbol, position, dfs):
    try:
        pos_side = 'long' if float(position['positionAmt']) > 0 else 'short'
        entry_price, current_price, atr = float(position['entryPrice']), dfs['1m'].iloc[-1]['close'], dfs['1m'].iloc[-1]['atr']
        if pd.isna(atr): return
        new_sl_price = current_price - (atr * TRAILING_STOP_ATR_MULTIPLIER) if pos_side == 'long' else current_price + (atr * TRAILING_STOP_ATR_MULTIPLIER)
        if (pos_side == 'long' and new_sl_price <= entry_price) or (pos_side == 'short' and new_sl_price >= entry_price): return
        open_orders = binance.fetch_open_orders(symbol)
        current_sl_order = next((o for o in open_orders if o['type'] == 'STOP_MARKET'), None)
        if not current_sl_order: return
        current_sl_price = current_sl_order['stopPrice']
        if (pos_side == 'long' and new_sl_price > current_sl_price) or (pos_side == 'short' and new_sl_price < current_sl_price):
            binance.cancel_order(current_sl_order['id'], symbol)
            binance.create_order(symbol, 'STOP_MARKET', current_sl_order['side'], current_sl_order['amount'], None, params={'stopPrice': new_sl_price, 'closePosition': True})
            msg = f"🛡️ [{symbol}] 수익 보호! SL 업데이트: ${current_sl_price:,.4f} -> ${new_sl_price:,.4f}"
            logging.info(msg); send_slack_message(msg)
    except Exception as e:
        logging.error(f"❌ [{symbol}] 트레일링 스탑 오류: {e}")

# --- 3. 메인 로직 처리 함수 ---
def process_symbol(symbol, binance_instance, state_data, lock_data, num_symbols):
    dfs = fetch_candles(symbol)
    if any(df.empty for df in dfs.values()): return
    dfs_with_indicators = apply_indicators_multi(dfs)

    risk_percent = RISK_PER_TRADE_PERCENT
    if ENABLE_DYNAMIC_RISK:
        try:
            atr_df = dfs_with_indicators[ATR_TIMEFRAME_FOR_VOLATILITY]
            current_atr, avg_atr = atr_df.iloc[-1]['atr'], atr_df.iloc[-1]['atr_ma']
            if not pd.isna(current_atr) and not pd.isna(avg_atr):
                if current_atr > avg_atr * HIGH_VOLATILITY_THRESHOLD_RATIO: risk_percent *= HIGH_VOLATILITY_RISK_MULTIPLIER
                elif current_atr < avg_atr * LOW_VOLATILITY_THRESHOLD_RATIO: risk_percent *= LOW_VOLATILITY_RISK_MULTIPLIER
        except Exception: pass

    try:
        positions = get_position_risk(binance_instance, symbol)
        current_pos = next((p for p in positions if abs(float(p.get('positionAmt', 0))) > 0), None)
        if current_pos:
            lock_data[symbol] = True
            if ENABLE_TRAILING_STOP: update_trailing_stop(symbol, current_pos, dfs_with_indicators)
            return
        if lock_data[symbol]:
            logging.info(f"🔓 [{symbol}] 포지션 종료 확인 -> Lock 해제."); lock_data[symbol] = False
    except Exception: return

    decision = check_entry_signal(dfs_with_indicators, state_data[symbol]['last_signal'], state_data[symbol]['last_timestamp'], symbol)
    if not decision: return

    direction, entry_price_str, ts_str, reason = decision.split(',', 3)
    entry_price, timestamp = float(entry_price_str), int(ts_str)
    atr = dfs_with_indicators['1m'].iloc[-1]['atr']
    if pd.isna(atr): return
    stop_loss = entry_price - (atr * ENTRY_ATR_SL_MULTIPLIER) if direction == 'long' else entry_price + (atr * ENTRY_ATR_SL_MULTIPLIER)
    take_profit = entry_price + (atr * ENTRY_ATR_TP_MULTIPLIER) if direction == 'long' else entry_price - (atr * ENTRY_ATR_TP_MULTIPLIER)
    amount = get_order_amount(symbol, entry_price, stop_loss, risk_percent, num_symbols)
    if amount <= 0: return
    
    trade_success = execute_trade(binance=binance_instance, symbol=symbol, direction=direction, amount=amount, stop_loss=stop_loss, take_profit=take_profit)
    if trade_success:
        state_data[symbol].update({'last_signal': direction, 'last_timestamp': timestamp})
        lock_data[symbol] = True
        log_trade_record(symbol, direction, entry_price, stop_loss, take_profit, timestamp)

# --- 4. 메인 실행 블록 ---
if __name__ == '__main__':
    logging.info("🚀 적응형 자동매매 프로그램을 시작합니다 (분산 투자 모드).")
    try:
        initial_balance = binance.fetch_balance({'type': 'future'})['total']['USDT']
        logging.info(f"📊 초기 잔고: ${initial_balance:,.2f}")
        for sym in symbols:
            positions = get_position_risk(binance, sym)
            if any(abs(float(p.get('positionAmt', 0))) > 0 for p in positions):
                position_lock[sym] = True
                logging.warning(f"⚠️ [{sym}] 시작 시 포지션 발견! Lock 상태로 시작.")
    except Exception as e:
        logging.critical(f"❌ 초기 잔고 조회 실패: {e}. 프로그램 종료."); exit()
    
    while True:
        try:
            wait_seconds = 60 - datetime.now().second
            if wait_seconds > 0: time.sleep(wait_seconds)
            for symbol in symbols:
                process_symbol(symbol, binance, state, position_lock, len(symbols))
        except Exception as e:
            logging.critical(f"💣 메인 루프 치명적 오류: {e}", exc_info=True)
            send_slack_message(f"🚨 메인 루프 치명적 오류 발생! 확인 필요: {e}")
            time.sleep(60)