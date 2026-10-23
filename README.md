# GPX to WordPress Auto-Blogger

This project is an automated bot that processes GPX files (GPS tracking data), analyzes running records in Korean using LLMs (Gemini or Local LLM), fetches current weather information, and automatically publishes a blog post to WordPress.

## Key Features
- **GPX Data Analysis**: Parses GPX files to extract distance, duration, and pace.
- **AI-Powered Running Analysis**: Uses Gemini or Local LLMs to interpret running records and suggest practical next steps based on the available data.
- **Weather Integration**: Automatically fetches current weather data for the activity location; this may differ from conditions during the run.
- **WordPress Automation**: Automatically creates and publishes posts to your WordPress site.
- **Telegram Integration**: Receive and process GPX files directly via Telegram.

## Installation & Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/now0930/runner_blog.git
   cd runner_blog
   ```

2. **Configure Environment Variables**:
   Copy the example file and fill in your credentials:
   ```bash
   cp .env.example .env
   # Edit .env with your API keys and credentials
   ```

3. **Run with Docker**:
   Use the production Compose file (the default `docker-compose.yml` starts Aider, not the bot):
   ```bash
   docker compose -f docker-compose.prod.yml up --build -d --force-recreate
   ```

## Usage

1. **Start the Bot**: Ensure the container is running.
2. **Send GPX File**: Send a `.gpx` file to the Telegram account associated with the `PHONE_NUMBER` configured in your `.env`.
3. **Processing**: The bot will automatically:
   - Download the file.
   - Parse the GPX data.
   - Generate a Korean running analysis using the configured LLM and `prompt_template.txt`.
   - Publish the post to your WordPress site.

## 러닝 분석 프롬프트

Gemini와 Local LLM은 [prompt_template.txt](prompt_template.txt)를 공통으로 사용합니다.
프롬프트는 한국어로 다음 내용을 작성하도록 지시합니다.

- **기록 요약**: 거리(km), 시간(시·분·초), 평균 페이스(분:초/km), 속도(km/h)를 정리합니다.
- **훈련 해석**: 거리와 지속 시간을 바탕으로 훈련의 의미를 설명합니다. 심박수나
  주관적 운동 강도(RPE) 없이 평균 페이스만으로 실력이나 훈련 강도를 단정하지 않습니다.
- **환경 해석**: 제공된 날씨만 참고하며, 현재 날씨와 러닝 당시 날씨를 구분합니다.
- **다음 훈련 제안**: 피로도와 통증 여부를 고려한 실천 가능한 조언을 1~2개 제시합니다.

구간별 페이스, 고도, 케이던스, 심박수, 칼로리, 과거 기록은 현재 프롬프트 입력에
포함되지 않습니다. 이 정보가 필요한 페이스 변화나 기록 향상 여부를 추측하지 않도록
지시하며, 누락되거나 유효하지 않거나 서로 모순되는 값은 해석을 제한하도록 합니다.

### 입력 변수와 수정 방법

`prompt_template.txt`의 지시문을 수정해 분석 스타일을 조절할 수 있습니다.
아래 변수 이름과 단위를 유지하세요.

| 변수 | 의미 및 입력 단위 |
| --- | --- |
| `distance` | 거리, m |
| `duration` | 시간, 초 |
| `pace_per_km` | 평균 페이스, 소수 단위 min/km (`5.50`은 5분 30초/km) |
| `speed` | 속도, km/h |
| `weather` | 현재 날씨 정보 문자열 |
| `date` | 활동 일시, 없으면 시스템의 현재 날짜 |

템플릿은 Python `str.format_map()`으로 치환됩니다. 변수는 `{distance:.2f}`처럼
표기하고, JSON 예시 등 일반 중괄호는 `{{`와 `}}`로 이스케이프하세요.
운영 Docker 환경에서는 수정한 파일이 반영되도록 컨테이너를 다시 빌드하고 재생성합니다.

```bash
docker compose -f docker-compose.prod.yml up --build -d --force-recreate
```

### 출력 형식

모델에는 `title`과 `summary`가 모두 문자열인 JSON 객체 하나만 반환하도록 요청합니다.
`summary`에는 기록 요약, 훈련 해석, 환경, 다음 훈련 제안을 문단으로 담습니다.
아래는 구조 예시입니다.

```json
{
  "title": "러닝 분석 제목",
  "summary": "러닝 기록 분석 및 다음 훈련 제안"
}
```

## Gemini 오류 진단 및 키 교체

`.env`에서 다음 항목을 설정합니다. 기존 `.env`는 Git 업데이트로 바뀌지 않으므로
이전 모델명이 있으면 직접 변경하세요. 키를 저장소나 명령어 출력에 넣지 마세요.

```dotenv
GEMINI_API_KEY=새_프로젝트의_키
AY_GEMINI_MODEL=gemini-3.6-flash
AY_GEMINI_FALLBACK_MODEL=
```

운영 Compose는 키와 모델을 `env_file: .env`에서 직접 읽습니다.
기존 `environment: GEMINI_API_KEY=${GEMINI_API_KEY}` 중복 설정을 제거하여
셸에 남아 있는 이전 키가 `.env`의 키를 덮어쓰는 경로를 없앴습니다.
Python 직접 실행에서는 명시적으로 설정된 프로세스 환경변수가 `.env`보다 우선합니다.
봇은 `GEMINI_API_KEY`를 명시적으로 전달하고 Gemini Developer API를 사용합니다.
`GOOGLE_API_KEY` 또는 Vertex AI 환경변수로 다른 키/백엔드가 선택되지 않습니다.

업데이트한 코드 폴더에서 실행합니다:

```bash
# 새 .env와 앱 코드로 봇 컨테이너 재생성
# 최초 Telegram 로그인은 -d 없이 실행하여 인증 코드를 입력하세요.
docker compose -f docker-compose.prod.yml up --build -d --force-recreate

# 실행 중인 봇과 동일한 컨테이너의 키/모델 확인 (API 호출 없음)
docker compose -f docker-compose.prod.yml exec runner-app python check_gemini.py --config-only

# 짧은 실제 생성 요청: 정상 JSON까지 검증, Telegram/WordPress에는 게시하지 않음
docker compose -f docker-compose.prod.yml exec runner-app python check_gemini.py
```

봇이 아직 실행되지 않으면 다음으로 독립 진단할 수 있습니다:

```bash
docker compose -f docker-compose.prod.yml build runner-app
docker compose -f docker-compose.prod.yml run --rm --no-deps runner-app python check_gemini.py
```

`restart`만 하면 변경된 환경변수가 반영되지 않을 수 있으므로 위의 재생성을 사용하세요.
진단 결과는 키 원문 대신 SHA-256 앞 12자리 지문을 표시합니다. 키 교체 전후에
지문이 달라지는지, 실제 실행 컨테이너와 새 컨테이너의 지문이 같은지 비교하세요.
실제 생성 진단에는 소량의 API 사용량이 발생하며, 성공하면 `PASS`와 종료 코드 0,
실패하면 원인 안내와 종료 코드 1을 반환합니다.

- **402 / prepayment credits depleted**: 해당 키가 사용하는 프로젝트의 결제 계정에서
  Gemini 선불 잔액을 확인해야 합니다. 같은 결제 계정을 공유하는 새 프로젝트를
  만드는 것만으로는 해결되지 않을 수 있습니다. 키 지문이 예상과 같고 잔액도 있는데
  계속 거부되면 Google 결제 지원에서 확인해야 하며 앱에서 결제 제한을 해제할 수는 없습니다.
- **404**: 모델 사용 종료 또는 프로젝트에서 사용 불가입니다. 사용 가능한 모델로
  `AY_GEMINI_MODEL`을 변경하세요. 선택적 fallback은 404일 때만 사용합니다.
- **400 / 401 / 403**: API 키, 권한, API 제한 또는 요청 설정을 확인하세요.
- **429**: 일반 할당량 초과와 선불 잔액 부족 메시지를 구분해서 표시합니다.
- **500 / 502 / 503 / 504**: 일시적인 서버 오류는 같은 모델로 최대 3회 재시도합니다.
  대기 시간은 2초, 4초, 8초에 각각 최대 1초의 무작위 지연을 더합니다.
  SDK 자체 재시도는 비활성화하여 모델당 총 4회로 제한합니다.
  모두 실패하면 게시하지 않고 GPX를 보존합니다. 잠시 후 해당 GPX를 Telegram으로
  다시 보내세요. 503 자체는 API 키나 결제 오류를 의미하지 않습니다.
  [Google 오류 해결 안내](https://ai.google.dev/gemini-api/docs/troubleshooting)를 참고하세요.

Gemini 호출 실패, 빈 응답, 잘못된 JSON은 이제 게시를 중단합니다. 원본 GPX는
다운로드 폴더에 남으며 해결 후 Telegram에서 다시 보내 재처리할 수 있습니다.
이미 게시된 오류 글은 자동 수정하지 않습니다.

2026-09-20 확인: 제공된 새 키로 `gemini-3.6-flash`의 실제 SDK JSON 생성이 성공했고,
402는 재현되지 않았습니다. `gemini-2.5-flash` 요청은 신규 사용자 사용 불가 404를
반환했습니다. 실제 운영 서버의 기존 키/컨테이너는 직접 조사하지 않았습니다.

참고: [Google 결제 안내](https://ai.google.dev/gemini-api/docs/billing),
[API 키 안내](https://ai.google.dev/gemini-api/docs/api-key),
[Docker 환경변수 우선순위](https://docs.docker.com/compose/how-tos/environment-variables/envvars-precedence/).

## Tests

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

회귀 테스트는 API 호출 없이 결제/인증 오류, 모델 fallback, JSON 검증과
분석 실패 시 WordPress 게시 차단을 확인합니다.
