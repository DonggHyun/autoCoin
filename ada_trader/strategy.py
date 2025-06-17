import logging
import pandas as pd
from ada_trader.config import (
    MIN_ENTRY_INTERVAL_SECONDS, BBW_RANGE_THRESHOLD,
    MIN_TREND_SCORE, MIN_RANGE_SCORE,
    TRENDING_REQUIRED_SCORE, TRENDING_WEIGHTS,
    RANGE_REQUIRED_SCORE, RANGE_WEIGHTS,
    ENTRY_ATR_SL_MULTIPLIER  # 손익비 계산을 위해 import 추가
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
    """필수 조건 및 손익비 필터를 추가하여 진입 신호를 결정합니다."""
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

    # ... (중복 진입 방지 로직은 동일) ...

    long_score, short_score = 0, 0
    weights = TRENDING_WEIGHTS if market_condition == 'trending' else RANGE_WEIGHTS
    
    # --- 점수 계산 로직 (기존 점수 계산 + S/R 분석 추가) ---
    # ... (기존과 동일한 점수 계산 로직 적용) ...

    # --- 최종 결정 ---
    decision = None
    entry_context = {}
    required_score = TRENDING_REQUIRED_SCORE if market_condition == 'trending' else RANGE_REQUIRED_SCORE
    
    # 1. 롱 포지션 진입 검토
    if long_score >= required_score:
        # [추가] 추세장 필수 조건 확인
        if market_condition == 'trending':
            is_ema_aligned = now_1m['ema8'] > now_1m['ema13'] > now_1m['ema21']
            is_adx_strong = now_1m.get('adx', 0) > 23
            if not is_ema_aligned and not is_adx_strong:
                logging.info(f"⚪️ [{symbol}] 추세장 롱 필수 조건 미충족 (EMA 정렬X, ADX 약함).")
                return None, {}, market_condition

        # [추가] 횡보장 손익비 필터
        if market_condition == 'range_bound':
            potential_target = now_1m.get('prev_day_high', now_1m.get('r1'))
            if potential_target:
                potential_reward = abs(potential_target - now_1m['close'])
                potential_risk = abs(now_1m['close'] - (now_1m['close'] - now_1m['atr'] * ENTRY_ATR_SL_MULTIPLIER))
                if potential_risk > 0 and (potential_reward / potential_risk) < 1.5:
                    logging.info(f"⚪️ [{symbol}] 횡보장 롱 손익비 불리 (RRR: {(potential_reward / potential_risk):.2f} < 1.5).")
                    return None, {}, market_condition
        
        # 모든 필터 통과 시 진입 결정
        decision = f"long,{now_1m['close']},{int(now_1m.name.timestamp() * 1000)},Score:{long_score}/{required_score}"
        # ... (entry_context 저장 로직) ...

    # 2. 숏 포지션 진입 검토 (롱 포지션과 대칭적으로 로직 적용)
    elif short_score >= required_score:
        # [추가] 추세장 필수 조건 확인
        if market_condition == 'trending':
            is_ema_aligned = now_1m['ema8'] < now_1m['ema13'] < now_1m['ema21']
            is_adx_strong = now_1m.get('adx', 0) > 23
            if not is_ema_aligned and not is_adx_strong:
                logging.info(f"⚪️ [{symbol}] 추세장 숏 필수 조건 미충족 (EMA 역배열X, ADX 약함).")
                return None, {}, market_condition
        
        # [추가] 횡보장 손익비 필터
        if market_condition == 'range_bound':
            potential_target = now_1m.get('prev_day_low', now_1m.get('s1'))
            if potential_target:
                potential_reward = abs(now_1m['close'] - potential_target)
                potential_risk = abs((now_1m['close'] + now_1m['atr'] * ENTRY_ATR_SL_MULTIPLIER) - now_1m['close'])
                if potential_risk > 0 and (potential_reward / potential_risk) < 1.5:
                    logging.info(f"⚪️ [{symbol}] 횡보장 숏 손익비 불리 (RRR: {(potential_reward / potential_risk):.2f} < 1.5).")
                    return None, {}, market_condition

        # 모든 필터 통과 시 진입 결정
        decision = f"short,{now_1m['close']},{int(now_1m.name.timestamp() * 1000)},Score:{short_score}/{required_score}"
        # ... (entry_context 저장 로직) ...
        
    # '아까운 기회' 로깅
    else:
        near_miss_threshold = required_score * 0.8
        if long_score >= near_miss_threshold or short_score >= near_miss_threshold:
            logging.info(
                f"惜 [{symbol}] 진입 근접! (시장: {market_condition}, T:{trend_score},R:{range_score}) | "
                f"롱: {long_score}/{required_score}점, 숏: {short_score}/{required_score}점"
            )
    
    return decision, entry_context, market_condition