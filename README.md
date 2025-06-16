# My Binance Futures Trading Bot

이 프로젝트는 파이썬과 ccxt 라이브러리를 이용한 바이낸스 선물 자동매매 봇입니다.

## ✨ 주요 기능

- **분산 투자**: 여러 코인에 자본을 나누어 동시에 투자합니다.
- **동적 리스크 관리**: 시장 변동성(ATR)에 따라 자동으로 주문량을 조절합니다.
- **트레일링 스탑**: 수익이 발생하면 손절 라인을 자동으로 따라가며 수익을 보호하고 극대화합니다.
- **슬랙 알림**: 모든 거래 내역과 주요 이벤트가 슬랙으로 전송됩니다.

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
    ```

5.  **봇 실행**
    ```bash
    python -m ada_trader.main
    ```

## ⚠️ 면책 조항

이 프로젝트는 학습 및 연구 목적으로 제작되었습니다. 모든 투자의 책임은 본인에게 있으며, 이 코드로 인해 발생하는 어떠한 손실에 대해서도 책임지지 않습니다.
