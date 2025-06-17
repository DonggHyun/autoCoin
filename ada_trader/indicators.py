#indicators.py

import pandas as pd
import logging
import numpy as np
from ada_trader.config import (
    ATR_TIMEFRAME_FOR_VOLATILITY, VOLATILITY_MA_PERIOD, EMA_SLOPE_PERIOD
)

def calculate_pivot_points(df_daily):
    """일봉 데이터로 피봇 포인트(지지/저항선)를 계산합니다."""
    if df_daily.empty:
        return {}
    
    # 전일 데이터를 사용하기 위해 마지막에서 두 번째 행을 선택
    if len(df_daily) < 2:
        return {}
    last_day = df_daily.iloc[-2]
    
    high = last_day.get('high', 0)
    low = last_day.get('low', 0)
    close = last_day.get('close', 0)
    
    pivot = (high + low + close) / 3
    s1 = (pivot * 2) - high
    r1 = (pivot * 2) - low
    s2 = pivot - (high - low)
    r2 = pivot + (high - low)
    
    return {'pivot': pivot, 's1': s1, 'r1': r1, 's2': s2, 'r2': r2}

def apply_indicators_multi(dfs, daily_df):
    """
    기본 지표, 피봇 포인트, EMA 기울기, 볼린저밴드 폭을 계산하여 DataFrame에 추가합니다.
    """
    # 일봉 데이터로 피봇 포인트 미리 계산
    pivots = calculate_pivot_points(daily_df)

    for tf, df in dfs.items():
        if df.empty: continue
        df = df.copy()

        # RSI
        delta = df['close'].diff()
        gain, loss = delta.where(delta > 0, 0), -delta.where(delta < 0, 0)
        avg_gain = gain.rolling(window=14, min_periods=1).mean()
        avg_loss = loss.rolling(window=14, min_periods=1).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        df['rsi'] = 100 - (100 / (1 + rs))

        # EMA
        df['ema8'] = df['close'].ewm(span=8, adjust=False).mean()
        df['ema13'] = df['close'].ewm(span=13, adjust=False).mean()
        df['ema21'] = df['close'].ewm(span=21, adjust=False).mean()
        
        # [추가] EMA 기울기 (Slope)
        df['ema21_slope'] = (df['ema21'] - df['ema21'].shift(EMA_SLOPE_PERIOD)) / EMA_SLOPE_PERIOD

        # MACD
        ema12 = df['close'].ewm(span=12, adjust=False).mean()
        ema26 = df['close'].ewm(span=26, adjust=False).mean()
        df['macd'] = ema12 - ema26
        df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()

        # OBV
        direction = np.sign(df['close'].diff()).fillna(0)
        df['obv'] = (df['volume'] * direction).cumsum()

        # ADX (ATR 포함)
        high_diff, low_diff = df['high'].diff(), -df['low'].diff()
        plus_dm = high_diff.where((high_diff > low_diff) & (high_diff > 0), 0.0)
        minus_dm = low_diff.where((low_diff > high_diff) & (low_diff > 0), 0.0)
        tr = pd.concat([df['high'] - df['low'], abs(df['high'] - df['close'].shift(1)), abs(df['low'] - df['close'].shift(1))], axis=1).max(axis=1)
        atr = tr.ewm(alpha=1/14, adjust=False).mean() # Wilder's Smoothing 적용
        df['atr'] = atr
        
        plus_di = 100 * (plus_dm.ewm(alpha=1/14, adjust=False).mean() / atr)
        minus_di = 100 * (minus_dm.ewm(alpha=1/14, adjust=False).mean() / atr)
        df['+di'] = plus_di
        df['-di'] = minus_di
        
        dx = 100 * (abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan))
        df['adx'] = dx.ewm(alpha=1/14, adjust=False).mean()

        # 볼린저밴드
        window_bb = 20
        df['sma_bb'] = df['close'].rolling(window=window_bb).mean()
        df['std_bb'] = df['close'].rolling(window=window_bb).std()
        df['bollinger_upper'] = df['sma_bb'] + (df['std_bb'] * 2)
        df['bollinger_lower'] = df['sma_bb'] - (df['std_bb'] * 2)
        
        # [추가] 볼린저밴드 폭 (Bollinger Band Width, BBW)
        epsilon = 1e-10
        df['bbw'] = (df['bollinger_upper'] - df['bollinger_lower']) / (df['sma_bb'] + epsilon)
        
        # [추가] 계산된 피봇 값을 각 행에 추가
        if pivots:
            for key, value in pivots.items():
                df[key] = value

        # 동적 리스크용 'ATR 이동평균' 지표
        if tf == ATR_TIMEFRAME_FOR_VOLATILITY:
            df['atr_ma'] = df['atr'].rolling(window=VOLATILITY_MA_PERIOD).mean()
        
        dfs[tf] = df

    return dfs