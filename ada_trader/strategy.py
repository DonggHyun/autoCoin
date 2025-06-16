# strategy.py

import logging
import pandas as pd
from ada_trader.config import (
    MIN_ENTRY_INTERVAL_SECONDS, TRENDING_ADX_THRESHOLD, RANGE_EMA_DIFF_THRESHOLD,
    TRENDING_REQUIRED_SCORE, TRENDING_WEIGHTS,
    RANGE_REQUIRED_SCORE, RANGE_WEIGHTS
)

def detect_market_condition(df_1m, df_15m):
    """ 현재 시장 상황 (횡보 또는 추세)을 판단합니다. """
    if df_1m.empty or df_15m.empty:
        return 'unknown'
    
    now_1m = df_1m.iloc[-1]
    now_15m = df_15m.iloc[-1]

    ema_diff_1m = (abs(now_1m['ema8'] - now_1m['ema13']) + abs(now_1m['ema13'] - now_1m['ema21'])) / now_1m['close']
    
    is_1m_range_bound = (ema_diff_1m < RANGE_EMA_DIFF_THRESHOLD) and (now_1m.get('adx', 100) < TRENDING_ADX_THRESHOLD)
    is_15m_range_bound = (now_15m.get('adx', 100) < TRENDING_ADX_THRESHOLD)

    if is_1m_range_bound and is_15m_range_bound:
        logging.debug(f"[{now_1m.name.strftime('%H:%M')}] 📈 시장 상황: 횡보장 (Range Bound)")
        return 'range_bound'
    else:
        logging.debug(f"[{now_1m.name.strftime('%H:%M')}] 📈 시장 상황: 추세장 (Trending)")
        return 'trending'

def check_entry_signal(dfs, last_signal, last_timestamp, symbol=''):
    """ 진입 신호를 확인하고, 없을 경우 현재 점수를 로깅합니다. """
    df_1m = dfs.get('1m')
    df_15m = dfs.get('15m')

    if df_1m is None or df_15m is None or df_1m.empty or df_15m.empty:
        return None
        
    # 안정적인 지표 계산을 위해 최소 50개 캔들 필요
    if len(df_1m) < 50 or len(df_15m) < 50:
        return None

    now_1m = df_1m.iloc[-1]
    prev_1m = df_1m.iloc[-2]
    now_15m = df_15m.iloc[-1]
    prev_15m = df_15m.iloc[-2]

    current_ts_ms = int(now_1m.name.timestamp() * 1000)
    if last_signal is not None and (current_ts_ms - last_timestamp) < (MIN_ENTRY_INTERVAL_SECONDS * 1000):
        return None

    market_condition = detect_market_condition(df_1m, df_15m)
    if market_condition == 'unknown':
        return None

    long_score, short_score = 0, 0
    weights = TRENDING_WEIGHTS if market_condition == 'trending' else RANGE_WEIGHTS
    
    # --- 공통 조건 점수 계산 ---
    if now_1m['close'] > now_1m['open']: long_score += weights.get('common_candle', 0)
    else: short_score += weights.get('common_candle', 0)
    
    if now_1m['obv'] > prev_1m['obv']: long_score += weights.get('common_obv', 0)
    elif now_1m['obv'] < prev_1m['obv']: short_score += weights.get('common_obv', 0)
    
    if now_1m['volume'] > prev_1m['volume'] * 1.2:
        long_score += weights.get('common_volume', 0)
        short_score += weights.get('common_volume', 0)

    # --- 시장 상황별 조건 점수 계산 ---
    if market_condition == 'trending':
        required_score = TRENDING_REQUIRED_SCORE
        # [추세장 롱]
        if now_1m['ema8'] > now_1m['ema13'] > now_1m['ema21']: long_score += weights.get('ema_alignment', 0)
        if now_1m['rsi'] > 50 and prev_1m['rsi'] <= 50: long_score += weights.get('rsi_momentum_cross', 0)
        if now_15m['ema21'] > prev_15m['ema21']: long_score += weights.get('higher_tf_trend', 0)
        
        # [추세장 숏]
        if now_1m['ema8'] < now_1m['ema13'] < now_1m['ema21']: short_score += weights.get('ema_alignment', 0)
        if now_1m['rsi'] < 50 and prev_1m['rsi'] >= 50: short_score += weights.get('rsi_momentum_cross', 0)
        if now_15m['ema21'] < prev_15m['ema21']: short_score += weights.get('higher_tf_trend', 0)
    else: # range_bound
        required_score = RANGE_REQUIRED_SCORE
        # [횡보장 롱]
        if now_1m['rsi'] < 30 and now_1m['rsi'] > prev_1m['rsi']: long_score += weights.get('rsi_reversal', 0)
        if now_1m['close'] > now_1m['bollinger_lower'] and prev_1m['close'] <= prev_1m['bollinger_lower']: long_score += weights.get('bollinger_reversal', 0)
        
        # [횡보장 숏]
        if now_1m['rsi'] > 70 and now_1m['rsi'] < prev_1m['rsi']: short_score += weights.get('rsi_reversal', 0)
        if now_1m['close'] < now_1m['bollinger_upper'] and prev_1m['close'] >= prev_1m['bollinger_upper']: short_score += weights.get('bollinger_reversal', 0)

    # --- 최종 진입 결정 ---
    if long_score >= required_score:
        return f"long,{now_1m['close']},{current_ts_ms},Score:{long_score}/{required_score}"
    elif short_score >= required_score:
        return f"short,{now_1m['close']},{current_ts_ms},Score:{short_score}/{required_score}"
    else:
        # 매매가 없을 때, INFO 레벨로 현재 점수 현황을 항상 기록합니다.
        logging.info(
            f"⚪ [{symbol}] 대기 ({market_condition}) | "
            f"롱: {long_score}/{required_score}점, 숏: {short_score}/{required_score}점"
        )
        return None