# Telegram GPX 러닝 분석 블로그

지정한 Telegram 채팅에 GPX 파일을 올리면 봇이 러닝 수치를 계산하고 `.env`에서 선택한 모델로 기록 해석과 다음 훈련 제안을 작성한 뒤 WordPress에 게시합니다. 기본값은 Gemini 3.8 Flash입니다.

## 설정과 실행

1. `.env.example`을 `.env`로 복사하고 Telegram, 선택할 분석 모델, WordPress 설정을 입력합니다. `.env`는 Git에 포함되지 않습니다.
2. 운영 봇을 실행합니다. 첫 Telegram 로그인에는 인증 코드 입력이 필요할 수 있으므로 처음에는 `-d` 없이 실행합니다.

```bash
cp .env.example .env
docker compose -f docker-compose.prod.yml up --build --force-recreate runner-app
```

인증을 마친 뒤 백그라운드로 실행하거나 설정을 바꿨을 때는 다음 명령을 사용합니다.

```bash
docker compose -f docker-compose.prod.yml up --build -d --force-recreate runner-app
docker compose -f docker-compose.prod.yml logs -f --tail=50 runner-app
```

## 모델 선택

`.env`에서 제공업체와 모델을 지정합니다. **기존 운영 설정은 `LLM_PROVIDER=gemini`, `AY_GEMINI_MODEL=gemini-3.8-flash`**입니다.

| 제공업체 | `.env` 설정 | 필요한 준비 |
| --- | --- | --- |
| Gemini | `LLM_PROVIDER=gemini`, `AY_GEMINI_MODEL=gemini-3.8-flash` | `GEMINI_API_KEY` |
| OpenAI | `LLM_PROVIDER=openai`, `OPENAI_MODEL=gpt-6-luna` | `OPENAI_API_KEY` |
| 로컬 Ollama | `LLM_PROVIDER=local`, `LOCAL_LLM_MODEL=gemma4:e4b` | 실행 중인 Ollama와 `LOCAL_LLM_ENDPOINT` |

Gemini의 다른 모델을 쓰려면 `AY_GEMINI_MODEL`만 바꾸면 됩니다. 선택적 `AY_GEMINI_FALLBACK_MODEL`은 기본 모델이 HTTP 404를 반환할 때만 시도합니다. OpenAI와 로컬 모델도 각 `*_MODEL` 값으로 선택합니다. 로컬 Ollama 모델명은 설치된 모델명으로 바꾸고, `LOCAL_LLM_ENDPOINT`는 **컨테이너에서 접근 가능한 주소**로 지정하세요.

제공업체를 바꾸면 계산된 운동 기록이 해당 제공업체로 전송됩니다. OpenAI를 선택하면 운동 기록이 OpenAI API로 전송되므로 전송을 원할 때만 바꾸세요. 설정이 잘못됐거나 인증 정보가 없으면 다른 제공업체로 몰래 전환하지 않고 시작을 중단합니다. 기존 `.env`는 Git 업데이트로 바뀌지 않으며, 변경한 설정은 다음 명령으로 컨테이너를 **재생성**해야 반영됩니다.

```bash
docker compose -f docker-compose.prod.yml up -d --no-deps --force-recreate runner-app
```

## GPX 전송과 게시 내용

`.env`의 `CHAT_ID`에 지정한 Telegram 채팅에 `.gpx` 파일을 문서로 보냅니다. 봇은 파일을 내려받고 거리·운동 시간·평균 페이스, 1km 구간별 시간과 심박·케이던스·고도, 전체 심박·케이던스·고도 및 GPS 기록점 수를 계산합니다. 마지막 구간에는 1km 미만의 남은 거리를 표시합니다. GPX에 없는 값은 채워 넣지 않습니다.

선택한 모델은 계산된 수치와 [러닝 분석 지시문](prompt_template.txt)을 받아 **제목, 기록 해석, 훈련 제안 1~3개**를 만듭니다. [게시 형식](report.py)은 수치 요약, 구간별 표, 해석, 훈련 제안, GPX 경로 지도로 구성됩니다. 수치와 표는 프로그램이 GPX에서 계산하며 모델이 임의로 만들지 않습니다. 심박 구간·운동 강도는 개인의 기준 정보가 없으면 단정하지 않습니다. 고도 범위는 누적 상승량이 아닙니다.

GPX에 시작 시각과 위치가 있으면 Open-Meteo 과거 날씨 API에서 **운동 시작 시각이 속한 1시간의 기온·습도·풍속·강수량**을 조회해 포스트에 기록합니다. 이 값은 해당 위치의 기상 재분석 추정치이며 현장 실측값이나 러닝 전체 시간의 평균이 아닙니다. 자료가 없으면 날씨를 추정하지 않고 `운동 당시 날씨 자료 없음`으로 표시합니다. 모델 또는 WordPress 요청이 실패하면 GPX 파일을 보존하고 게시를 중단합니다. 원인을 해결한 뒤 해당 GPX를 Telegram에 다시 보내면 재처리됩니다. **같은 GPX를 다시 보내면 중복 글이 생길 수 있으므로** 이미 게시됐는지 먼저 확인하세요.

프롬프트를 수정할 때는 기존 입력 변수(`distance`, `duration`, `pace_per_km`, `speed`, `weather`, `date`, `splits_text`, `heart_rate_text`, `cadence_text`, `elevation_text`)를 유지하세요. Python 형식 문자열이므로 JSON 예시의 중괄호는 `{{`와 `}}`로 씁니다. 수정 후 봇 컨테이너를 재생성합니다. 프롬프트를 읽지 못하거나 모델이 유효한 `title`·`summary`·`training` JSON을 반환하지 않으면 게시하지 않습니다.

## Gemini 연결 확인

개인 GPX를 보내거나 글을 게시하지 않는 짧은 진단입니다.

```bash
docker compose -f docker-compose.prod.yml exec runner-app python check_gemini.py --config-only
docker compose -f docker-compose.prod.yml exec runner-app python check_gemini.py
```

첫 명령은 모델과 키 지문만 확인합니다. 두 번째 명령은 실제 Gemini API로 짧은 JSON 생성 요청을 보냅니다. 키 원문은 출력하지 않습니다. HTTP 503·504 등 일시적인 서버 오류는 최대 3회 재시도하고, 계속 실패하면 게시하지 않습니다. HTTP 404는 모델명을, HTTP 400·401·403은 키·권한을, HTTP 429는 할당량 또는 결제 상태를 확인하세요. [Gemini 오류 안내](https://ai.google.dev/gemini-api/docs/troubleshooting)를 참고할 수 있습니다.

## 테스트

```bash
docker compose -f docker-compose.prod.yml run --rm --no-deps -T runner-app python -m unittest discover -s tests -v
```

테스트는 외부 API에 게시하지 않고 GPX 추출, 보고서, 모델 선택과 오류 처리, 게시 중단 조건을 확인합니다.
