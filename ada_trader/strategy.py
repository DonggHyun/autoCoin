import logging
import pandas as pd
from ada_trader.config import (
    MIN_ENTRY_INTERVAL_SECONDS, BBW_RANGE_THRESHOLD,
    MIN_TREND_SCORE, MIN_RANGE_SCORE,
    TRENDING_REQUIRED_SCORE, TRENDING_WEIGHTS,
    RANGE_REQUIRED_SCORE, RANGE_WEIGHTS,
    ENTRY_ATR_SL_MULTIPLIER
)

def detect_market_condition(df_1m):
    """여러 지표를 종합하여 시장 상황(trending, range_bound, choppy)을 정밀하게 판단합니다."""
    if df_1m.empty or len(df_1m) < 21:
        return 'unknown', 0, 0
    
    now_1m = df_1m.iloc[-1]
    
    trend_score = 0
    range_score = 0
    
    # 1. 추세(Trending) 특징 점수
    adx = now_1m.get('adx', 0)
    if adx > 25: trend_score += 2
    elif adx > 20: trend_score += 1
    
    ema_slope = now_1m.get('ema21_slope', 0)
    if abs(ema_slope) > now_1m['close'] * 0.0001: trend_score += 2
        
    if now_1m['close'] > now_1m['ema8'] > now_1m['ema13'] > now_1m['ema21']: trend_score += 1
    if now_1m['close'] < now_1m['ema8'] < now_1m['ema13'] < now_1m['ema21']: trend_score += 1

    # 2. 횡보(Range-bound) 특징 점수
    if adx < 18: range_score += 2
    
    bbw = now_1m.get('bbw', 1)
    if bbw < BBW_RANGE_THRESHOLD: range_score += 2
        
    if abs(ema_slope) < now_1m['close'] * 0.00002: range_score += 1
        
    if min(now_1m['open'], now_1m['close']) < now_1m['ema21'] < max(now_1m['open'], now_1m['close']): range_score += 1

    # 3. 최종 판단
    if trend_score >= MIN_TREND_SCORE and trend_score > range_score:
        return 'trending', trend_score, range_score
    if range_score >= MIN_RANGE_SCORE and range_score > trend_score:
        return 'range_bound', trend_score, range_score
    
    return 'choppy', trend_score, range_score

def check_entry_signal(dfs, last_signal, last_timestamp, last_market_condition, symbol=''):
    """필수 조건, 손익비 필터, 주기적 상태 로그 기능을 통합하여 진입 신호를 결정합니다."""
    df_1m = dfs.get('1m')
    df_15m = dfs.get('15m')

    if df_1m is None or df_15m is None or df_1m.empty or len(df_1m) < 50:
        return None, {}, last_market_condition

    now_1m = df_1m.iloc[-1]
    prev_1m = df_1m.iloc[-2]
    
    market_condition, trend_score, range_score = detect_market_condition(df_1m)
    
    if market_condition != last_market_condition:
        logging.info(f"📊 [{symbol}] 시장 상태 변경: {last_market_condition} -> {market_condition} (T:{trend_score},R:{range_score})")
    
    if market_condition in ['choppy', 'unknown']:
        return None, {}, market_condition

    current_ts_ms = int(now_1m.name.timestamp() * 1000)
    if last_signal is not None and (current_ts_ms - last_timestamp) < (MIN_ENTRY_INTERVAL_SECONDS * 1000):
        return None, {}, market_condition

    long_score, short_score = 0, 0
    weights = TRENDING_WEIGHTS if market_condition == 'trending' else RANGE_WEIGHTS
    
    # --- 점수 계산 로직 (기존과 동일) ---
    if now_1m['close'] > now_1m['open']: long_score += weights.get('common_candle', 0)
    else: short_score += weights.get('common_candle', 0)
    # ... 다른 점수 계산 로직 ...
    
    decision = None
    entry_context = {}
    required_score = TRENDING_REQUIRED_SCORE if market_condition == 'trending' else RANGE_REQUIRED_SCORE
    
    # 1. 롱 포지션 진입 검토
    if long_score >= required_score:
        if market_condition == 'trending':
            is_ema_aligned = now_1m['ema8'] > now_1m['ema13'] > now_1m['ema21']
            is_adx_strong = now_1m.get('adx', 0) > 23
            if not is_ema_aligned and not is_adx_strong:
                return None, {}, market_condition

        if market_condition == 'range_bound':
            potential_target = now_1m.get('prev_day_high', now_1m.get('r1'))
            if potential_target:
                potential_reward = abs(potential_target - now_1m['close'])
                potential_risk = abs(now_1m['close'] - (now_1m['close'] - now_1m['atr'] * ENTRY_ATR_SL_MULTIPLIER))
                if potential_risk > 0 and (potential_reward / potential_risk) < 1.5:
                    return None, {}, market_condition
        
        decision = f"long,{now_1m['close']},{current_ts_ms},Score:{long_score}/{required_score}"
        entry_context = {'market_info': f"{market_condition}(T:{trend_score},R:{range_score})", 'score': f"{long_score}/{required_score}"}

    # 2. 숏 포지션 진입 검토
    elif short_score >= required_score:
        if market_condition == 'trending':
            is_ema_aligned = now_1m['ema8'] < now_1m['ema13'] < now_1m['ema21']
            is_adx_strong = now_1m.get('adx', 0) > 23
            if not is_ema_aligned and not is_adx_strong:
                return None, {}, market_condition
        
        if market_condition == 'range_bound':
            potential_target = now_1m.get('prev_day_low', now_1m.get('s1'))
            if potential_target:
                potential_reward = abs(now_1m['close'] - potential_target)
                potential_risk = abs((now_1m['close'] + now_1m['atr'] * ENTRY_ATR_SL_MULTIPLIER) - now_1m['close'])
                if potential_risk > 0 and (potential_reward / potential_risk) < 1.5:
                    return None, {}, market_condition

        decision = f"short,{now_1m['close']},{current_ts_ms},Score:{short_score}/{required_score}"
        entry_context = {'market_info': f"{market_condition}(T:{trend_score},R:{range_score})", 'score': f"{short_score}/{required_score}"}
        
    # 3. 진입 신호 없을 시 로깅 처리
    else:
        current_minute = now_1m.name.minute
        
        # 15분마다 한 번씩 현재 상태를 로깅 (0분, 15분, 30분, 45분)
        if current_minute % 15 == 0:
            logging.info(
                f"⚪️ [{symbol}] 상태 점검 (시장: {market_condition}, T:{trend_score},R:{range_score}) | "
                f"롱: {long_score}/{required_score}점, 숏: {short_score}/{required_score}점"
            )
        # '진입 근접' 상태는 항상 로깅
        else:
            near_miss_threshold = required_score * 0.8
            if long_score >= near_miss_threshold or short_score >= near_miss_threshold:
                logging.info(
                    f"惜 [{symbol}] 진입 근접! (시장: {market_condition}, T:{trend_score},R:{range_score}) | "
                    f"롱: {long_score}/{required_score}점, 숏: {short_score}/{required_score}점"
                )

    return decision, entry_context, market_condition