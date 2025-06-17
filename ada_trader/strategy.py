#strategy.py
import logging
import pandas as pd
from ada_trader.config import (
    MIN_ENTRY_INTERVAL_SECONDS, BBW_RANGE_THRESHOLD,
    MIN_TREND_SCORE, MIN_RANGE_SCORE,
    TRENDING_REQUIRED_SCORE, TRENDING_WEIGHTS,
    RANGE_REQUIRED_SCORE, RANGE_WEIGHTS,
    SR_WEIGHTS
)

def detect_market_condition(df_1m):
    """
    [전면 수정] 여러 지표를 종합하여 시장 상황(trending, range_bound, choppy)을 정밀하게 판단합니다.
    """
    if df_1m.empty or len(df_1m) < 21:
        return 'unknown', 0, 0
    
    now_1m = df_1m.iloc[-1]
    
    trend_score = 0
    range_score = 0
    
    # --- 1. 추세(Trending) 특징 점수 계산 ---
    adx = now_1m.get('adx', 0)
    if adx > 25: trend_score += 2
    elif adx > 20: trend_score += 1
    
    ema_slope = now_1m.get('ema21_slope', 0)
    if abs(ema_slope) > now_1m['close'] * 0.0001: trend_score += 2
        
    if now_1m['close'] > now_1m['ema8'] and now_1m['ema8'] > now_1m['ema21']: trend_score += 1
    if now_1m['close'] < now_1m['ema8'] and now_1m['ema8'] < now_1m['ema21']: trend_score += 1

    # --- 2. 횡보(Range-bound) 특징 점수 계산 ---
    if adx < 18: range_score += 2
    
    bbw = now_1m.get('bbw', 1)
    if bbw < BBW_RANGE_THRESHOLD: range_score += 2
        
    if abs(ema_slope) < now_1m['close'] * 0.00002: range_score += 1
        
    if min(now_1m['open'], now_1m['close']) < now_1m['ema21'] < max(now_1m['open'], now_1m['close']): range_score += 1

    # --- 3. 최종 시장 상황 판단 ---
    if trend_score >= MIN_TREND_SCORE and trend_score > range_score:
        return 'trending', trend_score, range_score
    if range_score >= MIN_RANGE_SCORE and range_score > trend_score:
        return 'range_bound', trend_score, range_score
    
    return 'choppy', trend_score, range_score

def check_entry_signal(dfs, last_signal, last_timestamp, last_market_condition, symbol=''):
    """
    [수정] 고도화된 시장 판단, 효율적 로깅, 지지/저항 분석을 통합하여 진입 신호를 결정합니다.
    """
    df_1m = dfs.get('1m')
    if df_1m is None or df_1m.empty or len(df_1m) < 50:
        return None, {}, last_market_condition

    now_1m = df_1m.iloc[-1]
    prev_1m = df_1m.iloc[-2]

    market_condition, trend_score, range_score = detect_market_condition(df_1m)
    
    # [수정] 시장 상태가 '변경'되었을 때만 로그 기록
    if market_condition != last_market_condition:
        logging.info(f"📊 [{symbol}] 시장 상태 변경: {last_market_condition} -> {market_condition} (T:{trend_score},R:{range_score})")
    
    if market_condition in ['choppy', 'unknown']:
        return None, {}, market_condition

    current_ts_ms = int(now_1m.name.timestamp() * 1000)
    if last_signal is not None and (current_ts_ms - last_timestamp) < (MIN_ENTRY_INTERVAL_SECONDS * 1000):
        return None, {}, market_condition

    long_score, short_score = 0, 0
    weights = TRENDING_WEIGHTS if market_condition == 'trending' else RANGE_WEIGHTS
    required_score = TRENDING_REQUIRED_SCORE if market_condition == 'trending' else RANGE_REQUIRED_SCORE
    
    # --- 점수 계산 로직 (기존 점수 계산 + S/R 분석 추가) ---
    # 1. 공통 조건
    if now_1m['close'] > now_1m['open']: long_score += weights.get('common_candle', 0)
    else: short_score += weights.get('common_candle', 0)
    
    # ... (기존의 OBV, volume 등 공통 조건 점수 계산) ...

    # 2. 시장 상황별 조건 (추세/횡보)
    if market_condition == 'trending':
        # ... (기존의 추세장 점수 계산: EMA 정배열, RSI 돌파 등) ...
        pass
    else: # range_bound
        # ... (기존의 횡보장 점수 계산: RSI 역추세, 볼린저 반등 등) ...
        pass

    # 3. [추가] 지지/저항(S/R) 점수 계산
    # S1 지지선에서 반등(롱) / R1 저항선에서 반락(숏)
    if 's1' in now_1m and now_1m['low'] < now_1m['s1'] and now_1m['close'] > now_1m['s1']:
        long_score += weights.get('sr_bounce', 0)
    if 'r1' in now_1m and now_1m['high'] > now_1m['r1'] and now_1m['close'] < now_1m['r1']:
        short_score += weights.get('sr_bounce', 0)

    # R1 저항선 돌파(롱) / S1 지지선 돌파(숏)
    if 'r1' in now_1m and now_1m['close'] > now_1m['r1'] and prev_1m['close'] <= prev_1m['r1']:
        long_score += weights.get('sr_breakout', 0)
    if 's1' in now_1m and now_1m['close'] < now_1m['s1'] and prev_1m['close'] >= prev_1m['s1']:
        short_score += weights.get('sr_breakout', 0)

    # --- 최종 결정 ---
    decision = None
    entry_context = {}
    near_miss_threshold = required_score * 0.8

    if long_score >= required_score:
        decision = f"long,{now_1m['close']},{current_ts_ms},Score:{long_score}/{required_score}"
        entry_context = { # 분석을 위한 상세 정보
            'market_info': f"{market_condition}(T:{trend_score},R:{range_score})",
            'rsi': round(now_1m.get('rsi', 0), 2),
            'adx': round(now_1m.get('adx', 0), 2),
            'bbw': round(now_1m.get('bbw', 0), 4),
            'score': f"{long_score}/{required_score}"
        }
    elif short_score >= required_score:
        decision = f"short,{now_1m['close']},{current_ts_ms},Score:{short_score}/{required_score}"
        # ... (숏 포지션 entry_context 저장) ...

    elif long_score >= near_miss_threshold or short_score >= near_miss_threshold:
        logging.info(
            f"惜 [{symbol}] 진입 근접! (시장: {market_condition}, T:{trend_score},R:{range_score}) | "
            f"롱: {long_score}/{required_score}점, 숏: {short_score}/{required_score}점"
        )
    
    return decision, entry_context, market_condition