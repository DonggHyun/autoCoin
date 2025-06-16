# indicators.py

import pandas as pd
import logging
from ada_trader.config import (
    ATR_TIMEFRAME_FOR_VOLATILITY, VOLATILITY_MA_PERIOD
)

def apply_indicators_multi(dfs):
    for tf, df in dfs.items():
        if df.empty: continue
        df = df.copy()

        # RSI
        delta = df['close'].diff()
        gain, loss = delta.where(delta > 0, 0), -delta.where(delta < 0, 0)
        avg_gain, avg_loss = gain.rolling(window=14).mean(), loss.rolling(window=14).mean()
        rs = avg_gain / avg_loss.replace(0, pd.NA)
        df['rsi'] = 100 - (100 / (1 + rs))

        # EMA
        df['ema8'] = df['close'].ewm(span=8, adjust=False).mean()
        df['ema13'] = df['close'].ewm(span=13, adjust=False).mean()
        df['ema21'] = df['close'].ewm(span=21, adjust=False).mean()

        # MACD
        ema12, ema26 = df['close'].ewm(span=12, adjust=False).mean(), df['close'].ewm(span=26, adjust=False).mean()
        df['macd'] = ema12 - ema26
        df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()

        # OBV
        direction = (df['close'] > df['close'].shift(1)).astype(int) * 2 - 1
        direction[df['close'] == df['close'].shift(1)] = 0
        df['obv'] = (df['volume'] * direction).fillna(0).cumsum()

        # ADX (ATR 포함)
        high_diff, low_diff = df['high'].diff(), -df['low'].diff()
        plus_dm = high_diff.where((high_diff > low_diff) & (high_diff > 0), 0.0)
        minus_dm = low_diff.where((low_diff > high_diff) & (low_diff > 0), 0.0)
        tr = pd.concat([df['high'] - df['low'], abs(df['high'] - df['close'].shift(1)), abs(df['low'] - df['close'].shift(1))], axis=1).max(axis=1)
        atr = tr.rolling(window=14).mean()
        
        plus_di_denom, minus_di_denom = atr.replace(0, pd.NA), atr.replace(0, pd.NA)
        df['+di'] = 100 * (plus_dm.rolling(window=14).mean() / plus_di_denom)
        df['-di'] = 100 * (minus_dm.rolling(window=14).mean() / minus_di_denom)
        adx_denom = (df['+di'] + df['-di']).replace(0, pd.NA)
        df['adx'] = 100 * abs((df['+di'] - df['-di']) / adx_denom).rolling(window=14).mean()
        df['atr'] = atr

        # 동적 리스크용 'ATR 이동평균' 지표 추가
        if tf == ATR_TIMEFRAME_FOR_VOLATILITY:
            df['atr_ma'] = df['atr'].rolling(window=VOLATILITY_MA_PERIOD).mean()
        
        # 볼린저밴드
        window_bb = 20
        df['sma_bb'] = df['close'].rolling(window=window_bb).mean()
        df['std_bb'] = df['close'].rolling(window=window_bb).std()
        df['bollinger_upper'] = df['sma_bb'] + (df['std_bb'] * 2)
        df['bollinger_lower'] = df['sma_bb'] - (df['std_bb'] * 2)
        
        logging.debug(f"[{tf}] Indicators >> RSI: {df.iloc[-1].get('rsi', 0):.2f} | ADX: {df.iloc[-1].get('adx', 0):.2f}")
        dfs[tf] = df.dropna()

    return dfs