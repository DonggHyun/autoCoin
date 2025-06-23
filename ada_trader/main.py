#main.py
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
from ada_trader.utils import get_position_risk, send_slack_message, log_trade_record, load_state, save_state

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

symbols = SYMBOLS
position_lock = {symbol: False for symbol in symbols}
state = {symbol: {
    'last_signal': None, 'last_timestamp': 0, 'entry_info': None,
    'last_market_condition': 'unknown'
} for symbol in symbols}

for s in symbols:
    try:
        market = binance.market(s)
        binance.fapiPrivatePostLeverage({'symbol': market['id'], 'leverage': LEVERAGE})
        binance.fapiPrivatePostMarginType({'symbol': market['id'], 'marginType': 'ISOLATED'})
    except Exception as e:
        if "No need to change" not in str(e):
            logging.error(f"❌ [{s}] 초기 설정 오류: {e}")

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

def get_order_amount(symbol, entry_price):
    """총 자본의 지정된 비율을 사용해 주문 수량을 계산합니다."""
    try:
        total_balance = binance.fetch_balance({'type': 'future'})['total']['USDT']
        position_value_usdt = total_balance * CAPITAL_ALLOCATION_PERCENT
        amount = position_value_usdt / entry_price
        
        required_margin = position_value_usdt / LEVERAGE
        if required_margin > total_balance:
            logging.warning(f"⚠️ 요구 증거금({required_margin:,.2f} USDT)이 전체 잔고({total_balance:,.2f} USDT)를 초과하여 주문을 취소합니다.")
            return 0
            
        market_info = binance.market(symbol)
        min_notional = market_info.get('limits', {}).get('cost', {}).get('min', 5)
        if position_value_usdt < min_notional:
            logging.warning(f"⚠️ 계산된 포지션 가치({position_value_usdt:,.2f} USDT)가 최소 주문 금액({min_notional} USDT)보다 작아 주문을 취소합니다.")
            return 0
            
        return float(binance.amount_to_precision(symbol, amount))
    except Exception as e:
        logging.error(f"❌ [{symbol}] 주문 수량 계산 중 오류 발생: {e}")
        return 0

def update_trailing_stop(symbol, position, dfs):
    """수익 중인 포지션의 SL을 본전(Breakeven)으로 옮기거나, 트레일링 스탑을 업데이트합니다."""
    try:
        side = 'long' if float(position.get('positionAmt', 0)) > 0 else 'short'
        entry_price = float(position['entryPrice'])
        current_price = float(dfs['1m'].iloc[-1]['close'])
        
        atr_15m = float(dfs['15m'].iloc[-1]['atr'])
        if pd.isna(atr_15m) or atr_15m == 0: return

        open_orders = binance.fetch_open_orders(symbol)
        sl_order = next((o for o in open_orders if o['info'].get('reduceOnly') == 'true' and o['type'] == 'stop_market'), None)
        
        if not sl_order:
            logging.warning(f"⚠️ [{symbol}] 트레일링 스탑을 위한 SL 주문을 찾지 못했습니다.")
            return

        current_sl_price = float(sl_order['stopPrice'])
        new_sl_price = 0
        
        is_breakeven_set = sl_order.get('info', {}).get('workingType') == 'CONTRACT_PRICE' and abs(sl_order['stopPrice'] - entry_price) < 1e-9

        if not is_breakeven_set:
            if side == 'long' and current_price >= entry_price + (atr_15m * BREAKEVEN_TRIGGER_ATR_MULTIPLIER):
                new_sl_price = entry_price
                logging.info(f"🛡️ [{symbol}] 본전(Breakeven) 조건 충족! SL을 진입가({entry_price})로 이동합니다.")
            elif side == 'short' and current_price <= entry_price - (atr_15m * BREAKEVEN_TRIGGER_ATR_MULTIPLIER):
                new_sl_price = entry_price
                logging.info(f"🛡️ [{symbol}] 본전(Breakeven) 조건 충족! SL을 진입가({entry_price})로 이동합니다.")
        
        if side == 'long' and current_price > entry_price:
            potential_new_sl = current_price - (atr_15m * TRAILING_STOP_ATR_MULTIPLIER)
            if potential_new_sl > current_sl_price:
                new_sl_price = potential_new_sl
        elif side == 'short' and current_price < entry_price:
            potential_new_sl = current_price + (atr_15m * TRAILING_STOP_ATR_MULTIPLIER)
            if potential_new_sl < current_sl_price:
                new_sl_price = potential_new_sl

        if new_sl_price > 0 and abs(new_sl_price - current_sl_price) / current_sl_price > 0.0005:
            binance.cancel_order(sl_order['id'], symbol)
            close_side = 'sell' if side == 'long' else 'buy'
            amount = float(position['positionAmt'])
            sl_params = {'stopPrice': new_sl_price, 'closePosition': True}
            binance.create_order(symbol, 'STOP_MARKET', close_side, abs(amount), None, params=sl_params)
            
            msg_prefix = "🛡️" if abs(new_sl_price - entry_price) < 1e-9 else "🚀"
            logging.info(f"{msg_prefix} [{symbol}] SL 업데이트! New SL: {new_sl_price:.4f} (기존: {current_sl_price:.4f})")
            send_slack_message(f"{msg_prefix} [{symbol}] SL 업데이트!\n  - 기존 SL: {current_sl_price:,.4f}\n  - 신규 SL: {new_sl_price:,.4f}")
    except Exception as e:
        logging.error(f"❌ [{symbol}] SL 업데이트 중 오류: {e}", exc_info=True)


# 3. 메인 로직
def process_symbol(symbol, binance_instance, state_data, lock_data):
    try:
        daily_ohlcv = binance_instance.fetch_ohlcv(symbol, '1d', limit=2)
        daily_df = pd.DataFrame(daily_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    except Exception as e:
        logging.error(f"❌ [{symbol}] 일봉 데이터 조회 실패: {e}")
        daily_df = pd.DataFrame()

    dfs = fetch_candles(symbol)
    if any(df.empty for df in dfs.values()): return
    
    dfs_with_indicators = apply_indicators_multi(dfs, daily_df)

    try:
        positions = get_position_risk(binance_instance, symbol)
        current_pos = next((p for p in positions if float(p.get('positionAmt', 0)) != 0), None)
        
        if current_pos:
            if not lock_data.get(symbol): lock_data[symbol] = True
            
            entry_info = state_data[symbol].get('entry_info', {})
            if ENABLE_TRAILING_STOP and entry_info.get('entry_market_condition') == 'trending':
                update_trailing_stop(symbol, current_pos, dfs_with_indicators)
            return

        if lock_data.get(symbol):
            logging.info(f"🔓 [{symbol}] 포지션 종료 확인. 결과 분석 및 알림 시작...")
            lock_data[symbol] = False
            
            entry_info = state_data[symbol].get('entry_info')
            if entry_info:
                try:
                    last_trade = binance_instance.fetch_my_trades(symbol, limit=1)[0]
                    realized_pnl = float(last_trade['info']['realizedPnl'])
                    
                    entry_time_obj = datetime.fromisoformat(entry_info['entry_time'])
                    holding_time = (datetime.now(timezone.utc) - entry_time_obj).total_seconds() / 60
                    exit_reason = "Take Profit" if realized_pnl > 0 else "Stop Loss"
                    
                    msg = (f"🔔 [{symbol}] 포지션 종료 | {entry_info['direction'].upper()}\n"
                            f"   - PnL: {realized_pnl:,.4f}\n"
                            f"   - 보유 시간: {holding_time:.2f}분\n"
                            f"   - 종료 사유: {exit_reason}")
                    send_slack_message(msg)
                    
                    log_trade_record(symbol=symbol, side=entry_info['direction'], timestamp=int(datetime.now().timestamp()*1000),
                                        pnl=realized_pnl, holding_time=round(holding_time, 2), exit_reason=exit_reason)
                except Exception as e:
                    logging.error(f"❌ [{symbol}] 포지션 종료 후처리 중 오류: {e}")
                finally:
                    state_data[symbol]['entry_info'] = None
                    save_state(state_data)
            return
    except Exception as e: 
        logging.error(f"❌ [{symbol}] 포지션 확인 로직 오류: {e}"); return

    decision, entry_context, market_condition = check_entry_signal(
        dfs_with_indicators, 
        state_data[symbol]['last_signal'], 
        state_data[symbol]['last_timestamp'],
        state_data[symbol]['last_market_condition'],
        symbol
    )
    state_data[symbol]['last_market_condition'] = market_condition

    if not decision: return

    direction, entry_price_str, ts_str, reason = decision.split(',', 3)
    entry_price, timestamp = float(entry_price_str), int(ts_str)
    
    atr_15m = dfs_with_indicators['15m'].iloc[-1].get('atr')
    if pd.isna(atr_15m) or atr_15m == 0:
        logging.warning(f"[{symbol}] 15분봉 ATR 값이 유효하지 않아 진입을 건너뜁니다.")
        return
    
    stop_loss = entry_price - (atr_15m * ENTRY_ATR_SL_MULTIPLIER) if direction == 'long' else entry_price + (atr_15m * ENTRY_ATR_SL_MULTIPLIER)
    take_profit = None

    if market_condition == 'range_bound':
        sma_bb = dfs_with_indicators['1m'].iloc[-1].get('sma_bb')
        if pd.notna(sma_bb):
            take_profit = sma_bb
            logging.info(f"📊 [{symbol}] 횡보장 전략. TP를 BB중간선({take_profit:.4f})으로 설정합니다.")
    else: # trending
        logging.info(f"📊 [{symbol}] 추세장 전략. 트레일링 스탑으로 수익을 극대화합니다.")
        take_profit = None
    
    amount = get_order_amount(symbol, entry_price)
    if amount <= 0: return
    
    trade_success = execute_trade(binance=binance_instance, symbol=symbol, direction=direction, amount=amount, stop_loss=stop_loss, take_profit=take_profit)
    if trade_success:
        state_data[symbol].update({'last_signal': direction, 'last_timestamp': timestamp})
        state_data[symbol]['entry_info'] = {
            'direction': direction,
            'entry_price': entry_price,
            'entry_time': datetime.now(timezone.utc).isoformat(),
            'entry_market_condition': market_condition
        }
        lock_data[symbol] = True
        log_trade_record(symbol, direction, timestamp, entry_price=entry_price, stop_loss=stop_loss, take_profit=take_profit, entry_context=entry_context)
        save_state(state_data)

# 4. 메인 실행 블록
if __name__ == '__main__':
    logging.info("🚀 적응형 자동매매 프로그램을 시작합니다 (SOL 집중 투자 모드).")

    loaded_state = load_state()
    if loaded_state:
        for sym, s_data in loaded_state.items():
            if sym in state and s_data.get('entry_info') and s_data['entry_info'].get('entry_time'):
                try:
                    state[sym] = s_data
                    state[sym]['entry_info']['entry_time'] = datetime.fromisoformat(s_data['entry_info']['entry_time'])
                except Exception as e:
                    logging.error(f"[{sym}] 상태 복원 중 오류: {e}")
        logging.info("✅ 이전 상태 정보를 성공적으로 복원했습니다.")

    try:
        initial_balance = binance.fetch_balance({'type': 'future'})['total']['USDT']
        logging.info(f"📊 초기 잔고: ${initial_balance:,.2f}")
        for sym in symbols:
            if state[sym].get('entry_info'):
                position_lock[sym] = True
                logging.warning(f"⚠️ [{sym}] 복원된 포지션 발견! Lock 상태로 시작.")
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
                process_symbol(symbol, binance, state, position_lock)

        except Exception as e:
            logging.critical(f"💣 메인 루프 치명적 오류: {e}", exc_info=True)
            send_slack_message(f"🚨 메인 루프 치명적 오류 발생! 확인 필요: {e}")
            time.sleep(60)