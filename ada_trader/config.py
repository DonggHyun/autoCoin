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
ENABLE_DYNAMIC_RISK = True
ENABLE_TRAILING_STOP = True

# --- 거래 설정 ---
LEVERAGE = int(os.getenv("LEVERAGE", 10))

# --- 리스크 관리 설정 (분산 투자 전략) ---
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
ENTRY_ATR_TP_MULTIPLIER = 4.0
TRAILING_STOP_ATR_MULTIPLIER = 1.5

# --- 전략 파라미터 ---
MIN_ENTRY_INTERVAL_SECONDS = 120

# [수정] 시장 판단을 위한 정밀 파라미터
EMA_SLOPE_PERIOD = 10           # EMA 기울기 계산 시 사용할 기간
BBW_RANGE_THRESHOLD = 0.015     # 이 값보다 BBW가 좁으면 '횡보' 점수 획득
MIN_TREND_SCORE = 4             # 시장을 '추세'로 판단하기 위한 최소 점수
MIN_RANGE_SCORE = 4             # 시장을 '횡보'로 판단하기 위한 최소 점수

# [수정] 진입 결정에 필요한 총 점수
TRENDING_REQUIRED_SCORE = 11
RANGE_REQUIRED_SCORE = 7

# [추가] 지지/저항(S/R) 관련 가중치
SR_WEIGHTS = {
    'sr_bounce': 3,  # 지지선에서 반등하거나 저항선에서 반락할 때
    'sr_breakout': 2 # 지지/저항선을 돌파할 때
}

# [수정] 각 전략별 조건 가중치
TRENDING_WEIGHTS = {
    'common_candle': 2, 'common_obv': 1, 'common_volume': 1, 'ema_alignment': 3,
    'rsi_momentum_cross': 3, 'rsi_momentum_sustain': 1, 'macd_cross': 3,
    'higher_tf_trend': 2, 'adx_strength': 2, 'fib_breakout': 1,
}
TRENDING_WEIGHTS.update(SR_WEIGHTS) # 지지/저항 가중치 추가

RANGE_WEIGHTS = {
    'common_candle': 2, 'common_obv': 1, 'common_volume': 1, 'rsi_reversal': 3,
    'bollinger_reversal': 2, 'fib_support_reversal': 2, 'ema_cross_reclaim': 2,
    'ema_support_reclaim': 1,
}
RANGE_WEIGHTS.update(SR_WEIGHTS) # 지지/저항 가중치 추가