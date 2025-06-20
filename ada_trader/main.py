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

# 1. 초기 설정
log_level_map = {"DEBUG": logging.DEBUG, "INFO": logging.INFO}
logging.basicConfig(level=log_level_map.get(LOG_LEVEL.upper(), logging.INFO), format='%(asctime)s %(levelname)s:%(message)s', handlers=[logging.FileHandler(f'logs/{datetime.now().strftime("%Y-%m-%d")}.log', encoding='utf-8'), logging.StreamHandler()])

load_dotenv()
binance = ccxt.binance({'apiKey': API_KEY, 'secret': API_SECRET, 'enableRateLimit': True, 'options': {'defaultType': 'future'}})

try:
    binance.load_markets()
    logging.info("✅ 바이낸스 마켓 정보 로딩 성공.")
except Exception as e:
    logging.critical(f"❌ 바이낸스 마켓 정보 로딩 실패: {e}. 프로그램을 종료합니다.")
    exit()

symbols = ['XRP/USDT', 'SOL/USDT', 'ETH/USDT', 'BTC/USDT', 'DOGE/USDT']
position_lock = {symbol: False for symbol in symbols}
state = {symbol: {
    'last_signal': None, 'last_timestamp': 0, 'entry_info': None,
    'last_market_condition': 'unknown'
} for symbol in symbols}

for s in symbols:
    market = binance.market(s)
    try:
        binance.fapiPrivatePostLeverage({'symbol': market['id'], 'leverage': LEVERAGE})
        binance.fapiPrivatePostMarginType({'symbol': market['id'], 'marginType': 'ISOLATED'})
    except Exception as e:
        if "No need to change" not in str(e):
            logging.error(f"❌ [{market['id']}] 초기 설정 오류: {e}")

# 2. 헬퍼 함수
def fetch_candles(symbol, timeframes=['1m', '15m'], limit=200):
    data = {}
    for tf in timeframes:
        try:
            ohlcv = binance.fetch_ohlcv(symbol, timeframe=tf, limit=limit)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            data[tf] = df
        except Exception as e:
            logging.warning(f"캔들 조회 실패 ({symbol}, {tf}): {e}")
            data[tf] = pd.DataFrame()
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
            amount = (capital_per_trade * LEVERAGE) / entry_price

        min_notional = binance.market(symbol)['limits']['cost']['min']
        if (amount * entry_price) < min_notional: return 0
        
        return float(binance.amount_to_precision(symbol, amount))
    except Exception as e:
        logging.error(f"❌ [{symbol}] 주문 수량 계산 오류: {e}")
        return 0

def update_trailing_stop(symbol, position, dfs):
    # 트레일링 스탑 로직
    pass

# 3. 메인 로직
def process_symbol(symbol, binance_instance, state_data, lock_data, num_symbols):
    try:
        daily_ohlcv = binance_instance.fetch_ohlcv(symbol, '1d', limit=2)
        daily_df = pd.DataFrame(daily_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    except Exception as e:
        logging.error(f"❌ [{symbol}] 일봉 데이터 조회 실패: {e}")
        daily_df = pd.DataFrame()

    dfs = fetch_candles(symbol)
    if any(df.empty for df in dfs.values()): return
    
    dfs_with_indicators = apply_indicators_multi(dfs, daily_df)

    risk_percent = RISK_PER_TRADE_PERCENT
    if ENABLE_DYNAMIC_RISK:
        # 동적 리스크 계산 로직
        pass

    try:
        positions = get_position_risk(binance_instance, symbol)
        current_pos = next((p for p in positions if float(p.get('positionAmt', 0)) != 0), None)
        
        if current_pos:
            if not lock_data.get(symbol): lock_data[symbol] = True
            if ENABLE_TRAILING_STOP: update_trailing_stop(symbol, current_pos, dfs_with_indicators)
            return

        if lock_data.get(symbol):
            logging.info(f"🔓 [{symbol}] 포지션 종료 확인. 결과 분석 및 알림 시작...")
            lock_data[symbol] = False
            
            entry_info = state_data[symbol].get('entry_info')
            if entry_info:
                try:
                    last_trade = binance_instance.fetch_my_trades(symbol, limit=1)[0]
                    realized_pnl = float(last_trade['info']['realizedPnl'])
                    
                    holding_time = (datetime.now(timezone.utc) - entry_info['entry_time']).total_seconds() / 60
                    exit_reason = "Take Profit" if realized_pnl > 0 else "Stop Loss"
                    
                    msg = (f"🔔 [{symbol}] 포지션 종료 | {entry_info['direction'].upper()}\n"
                        f"   - PnL: {realized_pnl:,.4f}\n"
                        f"   - 보유 시간: {holding_time:.2f}분\n"
                        f"   - 종료 사유: {exit_reason}")
                    send_slack_message(msg)
                    
                    log_trade_record(symbol=symbol, side=entry_info['direction'], timestamp=int(datetime.now().timestamp()*1000),
                                    pnl=realized_pnl, holding_time=round(holding_time, 2), exit_reason=exit_reason)
                except Exception as e:
                    logging.error(f"❌ [{symbol}] 포지션 종료 후처리 중 오류: {e}")
                finally:
                    state_data[symbol]['entry_info'] = None
            return

    except Exception as e: 
        logging.error(f"❌ [{symbol}] 포지션 확인 로직 오류: {e}"); return

    decision, entry_context, new_market_condition = check_entry_signal(
        dfs_with_indicators, 
        state_data[symbol]['last_signal'], 
        state_data[symbol]['last_timestamp'],
        state_data[symbol]['last_market_condition'],
        symbol
    )
    state_data[symbol]['last_market_condition'] = new_market_condition

    if not decision: return

    direction, entry_price_str, ts_str, reason = decision.split(',', 3)
    entry_price, timestamp = float(entry_price_str), int(ts_str)
    atr = dfs_with_indicators['1m'].iloc[-1].get('atr')
    if pd.isna(atr): return
    
    stop_loss = entry_price - (atr * ENTRY_ATR_SL_MULTIPLIER) if direction == 'long' else entry_price + (atr * ENTRY_ATR_SL_MULTIPLIER)
    take_profit = entry_price + (atr * ENTRY_ATR_TP_MULTIPLIER) if direction == 'long' else entry_price - (atr * ENTRY_ATR_TP_MULTIPLIER)
    
    amount = get_order_amount(symbol, entry_price, stop_loss, risk_percent, len(symbols))
    if amount <= 0: return
    
    trade_success = execute_trade(binance=binance_instance, symbol=symbol, direction=direction, amount=amount, stop_loss=stop_loss, take_profit=take_profit)
    if trade_success:
        state_data[symbol].update({'last_signal': direction, 'last_timestamp': timestamp})
        state_data[symbol]['entry_info'] = {
            'direction': direction,
            'entry_price': entry_price,
            'entry_time': datetime.now(timezone.utc)
        }
        lock_data[symbol] = True
        log_trade_record(symbol, direction, timestamp, entry_price=entry_price, stop_loss=stop_loss, take_profit=take_profit, entry_context=entry_context)

# 4. 메인 실행 블록
if __name__ == '__main__':
    logging.info("🚀 적응형 자동매매 프로그램을 시작합니다 (분산 투자 모드).")
    try:
        initial_balance = binance.fetch_balance({'type': 'future'})['total']['USDT']
        logging.info(f"📊 초기 잔고: ${initial_balance:,.2f}")
    except Exception as e:
        logging.critical(f"❌ 초기 잔고 조회 실패: {e}. 프로그램 종료.")
        exit()
    
    while True:
        try:
            now = datetime.now(timezone.utc)
            seconds_until_next_minute = 60 - now.second - (now.microsecond / 1_000_000)
            if seconds_until_next_minute > 0:
                time.sleep(seconds_until_next_minute)
            
            for symbol in symbols:
                process_symbol(symbol, binance, state, position_lock, len(symbols))

        except Exception as e:
            logging.critical(f"💣 메인 루프 치명적 오류: {e}", exc_info=True)
            send_slack_message(f"🚨 메인 루프 치명적 오류 발생! 확인 필요: {e}")
            time.sleep(60)