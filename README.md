# My Adaptive Binance Futures Trading Bot

이 프로젝트는 파이썬과 ccxt 라이브러리를 이용한 바이낸스 선물 자동매매 봇입니다. 시장 상황에 적응하는 동적 리스크 관리와 트레일링 스탑 기능을 탑재하여 안정적인 운영을 목표로 합니다.

## ✨ 주요 기능

- **분산 투자**: 여러 코인에 자본을 나누어 동시에 투자합니다.
- **동적 리스크 관리**: 시장 변동성(ATR)에 따라 자동으로 주문량을 조절합니다.
- **트레일링 스탑**: 수익이 발생하면 손절 라인을 자동으로 따라가며 수익을 보호하고 극대화합니다.
- **실시간 점수 로깅**: 매매가 없을 때, 진입 조건 점수를 실시간으로 로깅하여 판단 과정을 투명하게 보여줍니다.
- **슬랙 알림**: 모든 거래 내역과 주요 이벤트가 슬랙으로 전송됩니다.

## 📈 매매 전략

이 봇은 다음과 같은 다층적 전략을 기반으로 동작합니다.

1.  **자본 관리 (Capital Management)**
    - 거래 시작 시, 현재 총자산을 설정된 코인 개수(3개)로 나누어 1개 코인에 진입할 자본 한도를 설정합니다. (유동적 분산 투자)

2.  **리스크 관리 (Risk Management)**
    - 15분봉 ATR과 그것의 이동평균을 비교하여 현재 시장의 변동성을 '과열', '침체', '보통' 세 단계로 진단합니다.
    - 변동성이 높을 때는 할당된 자본 내에서도 리스크 비율을 줄여(주문량 감소) 위험을 회피하고, 변동성이 낮을 때는 리스크를 소폭 늘려 기회를 포착합니다.

3.  **진입 결정 (Entry Strategy)**
    - 15분봉과 1분봉을 동시에 분석하여 현재 시장이 '추세장'인지 '횡보장'인지 판단합니다.
    - 각 시장 상황에 맞는 가중치 규칙(EMA, RSI, OBV, 볼린저밴드 등)에 따라 종합 점수를 계산합니다.
    - 계산된 점수가 기준점(`required_score`)을 넘을 때만 진입 신호를 발생시킵니다.

4.  **포지션 관리 (Position Management)**
    - 진입과 동시에 ATR을 기반으로 명확한 익절(TP) 및 손절(SL) 라인을 설정합니다.
    - 포지션이 수익 방향으로 움직일 경우, 손절 라인을 자동으로 유리한 방향으로 함께 이동(Trailing Stop)시켜 수익을 보호하고, 추세가 계속될 경우 수익을 극대화합니다.

## 📂 소스 코드 구조

각 파일은 다음과 같은 역할을 수행합니다.

- **`config.py`**: 모든 설정값과 전략 변수를 관리하는 **제어판** 파일.
- **`main.py`**: 모든 모듈을 조립하고 메인 루프를 실행하는 프로그램의 **지휘자**.
- **`strategy.py`**: 보조지표와 규칙에 따라 '매수/매도/대기'를 결정하는 핵심 **두뇌**.
- **`indicators.py`**: 차트 데이터를 받아 매매 전략에 필요한 모든 기술적 보조지표를 계산하는 **분석가**.
- **`trader.py`**: '매매 결정'을 받아 실제 거래소에 주문(진입, TP, SL)을 실행하는 **손과 발**.
- **`utils.py`**: 슬랙 알림, CSV 기록, 포지션 조회 등 여러 곳에서 쓰이는 **공구함**.

## 🚀 설치 및 실행 방법

1.  **저장소 복제**
    ```bash
    git clone [https://github.com/여러분의유저네임/my-trading-bot.git](https://github.com/여러분의유저네임/my-trading-bot.git)
    cd my-trading-bot
    ```

2.  **가상 환경 생성 및 활성화**
    ```bash
    python -m venv venv
    # Windows
    venv\Scripts\activate
    # macOS/Linux
    source venv/bin/activate
    ```

3.  **필요 라이브러리 설치**
    ```bash
    pip install -r requirements.txt
    ```

4.  **.env 파일 설정**
    `.env` 파일을 프로젝트 루트에 생성하고 아래 내용을 채워주세요.
    ```
    BINANCE_API_KEY=YOUR_API_KEY_HERE
    BINANCE_API_SECRET=YOUR_SECRET_KEY_HERE
    SLACK_WEBHOOK_URL=YOUR_SLACK_URL_HERE
    LEVERAGE=10

    *SLACK_WEBHOOK_URL 참고  -) http://xn--velog-nu3u.io/@king/slack-incoming-webhook
    ```

5.  **봇 실행**
    ```bash
    python -m ada_trader.main
    ```

## ⚠️ 면책 조항

이 프로젝트는 학습 및 연구 목적으로 제작되었습니다. 모든 투자의 책임은 본인에게 있으며, 이 코드로 인해 발생하는 어떠한 손실에 대해서도 책임지지 않습니다.
