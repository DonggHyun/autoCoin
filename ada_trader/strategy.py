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
    """모든 상세 점수 로직, 필터, 로깅 기능을 통합하여 진입 신호를 결정합니다."""
    df_1m = dfs.get('1m')
    df_15m = dfs.get('15m')

    if df_1m is None or df_15m is None or df_1m.empty or len(df_1m) < 50:
        return None, {}, last_market_condition

    now_1m = df_1m.iloc[-1]
    prev_1m = df_1m.iloc[-2]
    now_15m = df_15m.iloc[-1]
    
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
    
    # --- 전체 점수 계산 로직 ---
    # 1. 공통 조건
    if now_1m['close'] > now_1m['open']: long_score += weights.get('common_candle', 0)
    else: short_score += weights.get('common_candle', 0)
    if now_1m['obv'] > prev_1m['obv']: long_score += weights.get('common_obv', 0)
    elif now_1m['obv'] < prev_1m['obv']: short_score += weights.get('common_obv', 0)
    if now_1m['volume'] > prev_1m['volume'] * 1.5:
        long_score += weights.get('common_volume', 0); short_score += weights.get('common_volume', 0)

    # 2. 시장 상황별 핵심 조건
    if market_condition == 'trending':
        if now_1m['ema8'] > now_1m['ema13'] > now_1m['ema21']: long_score += weights.get('ema_alignment', 0)
        if now_1m['ema8'] < now_1m['ema13'] < now_1m['ema21']: short_score += weights.get('ema_alignment', 0)
        if now_1m['macd'] > now_1m['macd_signal'] and prev_1m['macd'] <= prev_1m['macd_signal']: long_score += weights.get('macd_cross', 0)
        if now_1m['macd'] < now_1m['macd_signal'] and prev_1m['macd'] >= prev_1m['macd_signal']: short_score += weights.get('macd_cross', 0)
        if now_15m['ema8'] > now_15m['ema21']: long_score += weights.get('higher_tf_trend', 0)
        if now_15m['ema8'] < now_15m['ema21']: short_score += weights.get('higher_tf_trend', 0)
        if now_1m.get('adx', 0) > 23:
            if now_1m.get('+di', 0) > now_1m.get('-di', 0): long_score += weights.get('adx_strength', 0)
            if now_1m.get('-di', 0) > now_1m.get('+di', 0): short_score += weights.get('adx_strength', 0)
    else: # range_bound
        if now_1m['rsi'] < 35 and now_1m['rsi'] > prev_1m['rsi']: long_score += weights.get('rsi_reversal', 0)
        if now_1m['rsi'] > 65 and now_1m['rsi'] < prev_1m['rsi']: short_score += weights.get('rsi_reversal', 0)
        if 'bollinger_lower' in now_1m and now_1m['low'] < now_1m['bollinger_lower']: long_score += weights.get('bollinger_reversal', 0)
        if 'bollinger_upper' in now_1m and now_1m['high'] > now_1m['bollinger_upper']: short_score += weights.get('bollinger_reversal', 0)

    # 3. 지지/저항(S/R) 점수
    if 's1' in now_1m and now_1m['low'] < now_1m['s1'] < now_1m['close']: long_score += weights.get('pivot_bounce', 0)
    if 'r1' in now_1m and now_1m['high'] > now_1m['r1'] > now_1m['close']: short_score += weights.get('pivot_bounce', 0)
    if 'prev_day_low' in now_1m and now_1m['low'] < now_1m['prev_day_low'] and now_1m['close'] > now_1m['prev_day_low']: long_score += weights.get('pdhl_bounce', 0)
    if 'prev_day_high' in now_1m and now_1m['high'] > now_1m['prev_day_high'] and now_1m['close'] < now_1m['prev_day_high']: short_score += weights.get('pdhl_bounce', 0)
    
    # --- 최종 결정 및 필터링 ---
    decision, entry_context = None, {}
    required_score = TRENDING_REQUIRED_SCORE if market_condition == 'trending' else RANGE_REQUIRED_SCORE
    
    if long_score >= required_score:
        if market_condition == 'trending':
            is_ema_aligned = now_1m['ema8'] > now_1m['ema13'] > now_1m['ema21']
            is_adx_strong = now_1m.get('adx', 0) > 23
            if not is_ema_aligned and not is_adx_strong: return None, {}, market_condition
        if market_condition == 'range_bound':
            potential_target = now_1m.get('prev_day_high', now_1m.get('r1'))
            if potential_target and 'atr' in now_1m:
                potential_reward = abs(potential_target - now_1m['close'])
                potential_risk = abs(now_1m['close'] - (now_1m['close'] - now_1m['atr'] * ENTRY_ATR_SL_MULTIPLIER))
                if potential_risk > 0 and (potential_reward / potential_risk) < 1.5: return None, {}, market_condition
        decision = f"long,{now_1m['close']},{current_ts_ms},Score:{long_score}/{required_score}"
        entry_context = {'market_info': f"{market_condition}(T:{trend_score},R:{range_score})", 'score': f"{long_score}/{required_score}"}

    elif short_score >= required_score:
        if market_condition == 'trending':
            is_ema_aligned = now_1m['ema8'] < now_1m['ema13'] < now_1m['ema21']
            is_adx_strong = now_1m.get('adx', 0) > 23
            if not is_ema_aligned and not is_adx_strong: return None, {}, market_condition
        if market_condition == 'range_bound':
            potential_target = now_1m.get('prev_day_low', now_1m.get('s1'))
            if potential_target and 'atr' in now_1m:
                potential_reward = abs(now_1m['close'] - potential_target)
                potential_risk = abs((now_1m['close'] + now_1m['atr'] * ENTRY_ATR_SL_MULTIPLIER) - now_1m['close'])
                if potential_risk > 0 and (potential_reward / potential_risk) < 1.5: return None, {}, market_condition
        decision = f"short,{now_1m['close']},{current_ts_ms},Score:{short_score}/{required_score}"
        entry_context = {'market_info': f"{market_condition}(T:{trend_score},R:{range_score})", 'score': f"{short_score}/{required_score}"}
        
    else:
        current_minute = now_1m.name.minute
        if current_minute % 15 == 0:
            logging.info(f"⚪️ [{symbol}] 상태 점검 (시장: {market_condition}, T:{trend_score},R:{range_score}) | 롱: {long_score}/{required_score}점, 숏: {short_score}/{required_score}점")
        else:
            near_miss_threshold = required_score * 0.8
            if long_score >= near_miss_threshold or short_score >= near_miss_threshold:
                logging.info(f"惜 [{symbol}] 진입 근접! (시장: {market_condition}, T:{trend_score},R:{range_score}) | 롱: {long_score}/{required_score}점, 숏: {short_score}/{required_score}점")

    return decision, entry_context, market_condition