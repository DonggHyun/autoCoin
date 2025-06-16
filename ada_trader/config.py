# config.py

import os
from dotenv import load_dotenv

load_dotenv()

# --- 기본 설정 ---
API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

# --- 시스템 설정 ---
LOG_LEVEL = "INFO" # 운영 시: "INFO", 상세 분석 시: "DEBUG"

# --- 고급 기능 활성화 스위치 ---
ENABLE_DYNAMIC_RISK = True      # True로 설정 시, 시장 변동성에 따라 리스크(주문량)를 자동 조절
ENABLE_TRAILING_STOP = True     # True로 설정 시, 수익이 날 때 손절 라인을 자동으로 따라 올림 (수익 보호)

# --- 거래 설정 ---
LEVERAGE = int(os.getenv("LEVERAGE", 10))

# --- 리스크 관리 설정 (분산 투자 전략) ---
# 아래 리스크 비율은 '전체 계좌'가 아닌, '1개 코인에 할당된 자본(총자산의 1/3)'을 기준으로 적용됩니다.
RISK_PER_TRADE_PERCENT = 0.025  # 2.5%

# --- 동적 리스크 상세 설정 ---
ATR_TIMEFRAME_FOR_VOLATILITY = '15m'
VOLATILITY_MA_PERIOD = 50
HIGH_VOLATILITY_THRESHOLD_RATIO = 1.5
LOW_VOLATILITY_THRESHOLD_RATIO = 0.7
HIGH_VOLATILITY_RISK_MULTIPLIER = 0.6
LOW_VOLATILITY_RISK_MULTIPLIER = 1.2

# --- 트레일링 스탑 상세 설정 ---
ENTRY_ATR_SL_MULTIPLIER = 1.5
ENTRY_ATR_TP_MULTIPLIER = 3.0
TRAILING_STOP_ATR_MULTIPLIER = 1.5

# --- 전략 파라미터 ---
MIN_ENTRY_INTERVAL_SECONDS = 120
TRENDING_ADX_THRESHOLD = 20
RANGE_EMA_DIFF_THRESHOLD = 0.0005
TRENDING_REQUIRED_SCORE = 11
RANGE_REQUIRED_SCORE = 6
TRENDING_WEIGHTS = {
    'common_candle': 2, 'common_obv': 1, 'common_volume': 1, 'ema_alignment': 3,
    'rsi_momentum_cross': 3, 'rsi_momentum_sustain': 1, 'macd_cross': 3,
    'higher_tf_trend': 2, 'adx_strength': 2, 'fib_breakout': 1,
}
RANGE_WEIGHTS = {
    'common_candle': 2, 'common_obv': 1, 'common_volume': 1, 'rsi_reversal': 3,
    'bollinger_reversal': 2, 'fib_support_reversal': 2, 'ema_cross_reclaim': 2,
    'ema_support_reclaim': 1,
}