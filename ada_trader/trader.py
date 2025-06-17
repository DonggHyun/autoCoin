#trader.py

import logging
import ccxt
from ada_trader.utils import send_slack_message

def execute_trade(binance, symbol, direction, amount, stop_loss, take_profit):
    """
    [수정] 시장가 진입, TP/SL 주문 설정 등 오직 '주문 실행' 역할만 수행합니다.
    """
    market_id = binance.market(symbol)['id']
    side = 'buy' if direction == 'long' else 'sell'
    close_side = 'sell' if side == 'buy' else 'buy'
    
    try:
        # 안전을 위해 진입 전 해당 심볼의 모든 기존 주문 취소
        binance.cancel_all_orders(symbol)
        logging.info(f"✅ [{symbol}] 진입 전, 기존 조건부 주문 취소 완료.")

        # 시장가 진입
        entry_order = binance.create_market_order(symbol, side, amount)
        entry_price = float(entry_order.get('average', entry_order.get('price')))
        logging.info(f"🚀 [{symbol}] 진입 성공! {direction.upper()} | 수량: {amount} | 진입가: {entry_price}")

        # TP, SL 주문 (closePosition: True 파라미터로 포지션 전체 청산을 보장)
        tp_params = {'stopPrice': take_profit, 'closePosition': True}
        binance.create_order(symbol, 'TAKE_PROFIT_MARKET', close_side, amount, None, params=tp_params)
        logging.info(f"✅ [{symbol}] TP 주문 설정 완료. 발동가: {take_profit}")

        sl_params = {'stopPrice': stop_loss, 'closePosition': True}
        binance.create_order(symbol, 'STOP_MARKET', close_side, amount, None, params=sl_params)
        logging.info(f"✅ [{symbol}] SL 주문 설정 완료. 발동가: {stop_loss}")
        
        # 진입 슬랙 알림
        msg = (f"📈 [{symbol}] 신규 진입 | {direction.upper()} | 수량: {amount} | 진입가: ${entry_price:,.4f}\n"
               f"   - TP: ${take_profit:,.4f}, SL: ${stop_loss:,.4f}")
        send_slack_message(msg)
        return True

    except ccxt.InsufficientFunds as e:
        logging.error(f"❌ [{symbol}] 잔고 부족으로 주문 실패: {e}")
        send_slack_message(f"🚨 [{symbol}] 잔고 부족! 주문에 실패했습니다.")
        return False
    except Exception as e:
        logging.error(f"❌ [{symbol}] 주문 실행 중 오류: {e}", exc_info=True)
        send_slack_message(f"🚨 [{symbol}] 주문 실행 실패! 로그 확인 필요: {e}")
        # 오류 발생 시 정리
        try:
            binance.cancel_all_orders(symbol)
        except Exception as cancel_e:
            logging.error(f"❌ [{symbol}] 주문 실패 후 정리 중 추가 오류: {cancel_e}")
        return False