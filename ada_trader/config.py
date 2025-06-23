#config.py
import os
from dotenv import load_dotenv

load_dotenv()

# --- 기본 설정 ---
API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

# --- 거래 대상 설정 (솔라나 집중 투자) ---
SYMBOLS = ['SOL/USDT']

# --- 시스템 설정 ---
LOG_LEVEL = "INFO" # 운영 시: "INFO", 상세 분석 시: "DEBUG"

# --- 고급 기능 활성화 스위치 ---
ENABLE_DYNAMIC_RISK = False # 단일 종목 집중 투자이므로 비활성화
ENABLE_TRAILING_STOP = True

# --- 투자 전략 설정 ---
CAPITAL_ALLOCATION_PERCENT = 0.6  # 자본금의 60%를 사용
LEVERAGE = int(os.getenv("LEVERAGE", 10))

# --- 트레일링 스탑 상세 설정 (수익 극대화 조정) ---
ENTRY_ATR_SL_MULTIPLIER = 1.5
TRAILING_STOP_ATR_MULTIPLIER = 2.0      # 수익 극대화를 위해 1.5 -> 2.0으로 조정
BREAKEVEN_TRIGGER_ATR_MULTIPLIER = 1.5  # 1.5 ATR 이상 수익 시 본전 로직 발동

# --- 전략 파라미터 ---
MIN_ENTRY_INTERVAL_SECONDS = 120

# 시장 판단을 위한 정밀 파라미터
EMA_SLOPE_PERIOD = 10
BBW_RANGE_THRESHOLD = 0.015
MIN_TREND_SCORE = 3
MIN_RANGE_SCORE = 3

# 진입 결정에 필요한 총 점수
TRENDING_REQUIRED_SCORE = 11
RANGE_REQUIRED_SCORE = 6  # 횡보장 진입 점수 7 -> 6점으로 완화 유지

# 지지/저항(S/R) 관련 가중치
SR_WEIGHTS = {
    'pivot_bounce': 3,
    'pivot_breakout': 2,
    'pdhl_bounce': 4,
    'pdhl_breakout': 3
}

# 각 전략별 조건 가중치
TRENDING_WEIGHTS = {
    'common_candle': 2, 
    'common_obv': 1, 
    'common_volume': 1, 
    'ema_alignment': 3,
    'rsi_momentum_sustain': 1, 
    'macd_cross': 3,
    'higher_tf_trend': 2, 
    'adx_strength': 2,
}
TRENDING_WEIGHTS.update(SR_WEIGHTS)

RANGE_WEIGHTS = {
    'common_candle': 2, 
    'common_obv': 1, 
    'common_volume': 1, 
    'rsi_reversal': 3,
    'bollinger_reversal': 2, 
    'ema_cross_reclaim': 2,
    'ema_support_reclaim': 1,
}
RANGE_WEIGHTS.update(SR_WEIGHTS)