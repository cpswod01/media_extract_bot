# 🎙️ X Media Summary Bot (@BAEKPRO_summary_bot)

X(트위터) 스페이스, 유튜브 영상 링크를 텔레그램으로 보내면
자동으로 전사(STT)해서 텍스트 파일로 저장해주는 개인용 봇입니다.

## 작동 방식

1. 텔레그램에 링크 전송
2. 파일명 설정 (기본 or 직접 입력)
3. 자동 다운로드 → 변환 → Whisper 전사
4. 대본 파일 저장 + 텔레그램으로 파일 전송

## 지원 플랫폼

- X(트위터) 스페이스/영상
- 유튜브/유튜브 라이브
- 그 외 yt-dlp 지원 1000개 이상 사이트

## 필요 환경

- macOS (Apple Silicon 권장)
- Python 3.9 이상
- Homebrew

## 설치 방법

### 1. 필수 도구 설치

```bash
brew install yt-dlp ffmpeg
pip3 install openai-whisper
```

### 2. 프로젝트 클론

```bash
git clone https://github.com/YOUR_USERNAME/baekbot.git
cd baekbot
```

### 3. 가상환경 설정

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 4. 환경변수 설정

```bash
cp .env.example .env
nano .env
```

`.env` 파일에 아래 값 입력:
- `TELEGRAM_TOKEN`: BotFather에서 발급

### 5. 실행

```bash
python3 bot.py
```

### 6. 자동 실행 설정 (선택사항)

macOS launchctl을 이용한 자동 실행:

```bash
nano ~/Library/LaunchAgents/com.baekbot.plist
```

## 기술 스택

- **인터페이스**: Telegram Bot API
- **다운로드**: yt-dlp
- **변환**: ffmpeg
- **전사**: OpenAI Whisper (로컬)
- **언어**: Python 3

## 비용

완전 무료로 운영 가능합니다.
모든 처리가 로컬에서 실행됩니다.

## 변경 이력

### 2026-04-24
- 이전 요청 파일이 재전송되는 버그 수정 (`pending_data` 초기화 누락)
- yt-dlp 타임아웃 300초로 설정 (Timed out 오류 대응)
- 실행 경로 수정 (`~/baekbot` → `~/BOT/baekbot`)
- Claude 요약 기능 제거 (로컬 전사만 유지)

## 만든 사람

[@baekpro](https://x.com/baekpro)
