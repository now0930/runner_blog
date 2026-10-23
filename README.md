# Telegram GPX 러닝 분석 블로그

지정한 Telegram 채팅에 GPX 파일을 올리면 봇이 러닝 수치를 계산하고 **Gemini 3.8 Flash**로 기록 해석과 다음 훈련 제안을 작성한 뒤 WordPress에 게시합니다. 모델 선택 기능은 없으며 분석은 Gemini Developer API만 사용합니다.

## 설정과 실행

1. `.env.example`을 `.env`로 복사하고 Telegram, Gemini, WordPress 설정을 입력합니다. `.env`는 Git에 포함되지 않습니다.
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

`.env`의 기본 모델은 `AY_GEMINI_MODEL=gemini-3.8-flash`입니다. `AY_GEMINI_FALLBACK_MODEL`은 기본적으로 비어 있으며, 설정했을 때 기본 모델이 HTTP 404를 반환하는 경우에만 시도합니다. 기존 `.env`는 Git 업데이트로 바뀌지 않으므로 모델 설정을 직접 확인하세요. 설정 변경은 컨테이너 **재생성** 후 반영됩니다.

## GPX 전송과 게시 내용

`.env`의 `CHAT_ID`에 지정한 Telegram 채팅에 `.gpx` 파일을 문서로 보냅니다. 봇은 파일을 내려받고 거리·운동 시간·평균 페이스, 1km 구간별 시간과 심박·케이던스·고도, 전체 심박·케이던스·고도 및 GPS 기록점 수를 계산합니다. 마지막 구간에는 1km 미만의 남은 거리를 표시합니다. GPX에 없는 값은 채워 넣지 않습니다.

Gemini는 계산된 수치와 [러닝 분석 지시문](prompt_template.txt)을 받아 **제목, 기록 해석, 훈련 제안 1~3개**를 만듭니다. [게시 형식](report.py)은 수치 요약, 구간별 표, 해석, 훈련 제안, GPX 경로 지도로 구성됩니다. 수치와 표는 프로그램이 GPX에서 계산하며 Gemini가 임의로 만들지 않습니다. 심박 구간·운동 강도는 개인의 기준 정보가 없으면 단정하지 않습니다. 고도 범위는 누적 상승량이 아닙니다.

현재 기온을 조회할 수 있지만 **달렸던 당시의 날씨는 아닐 수 있습니다**. Gemini 또는 WordPress 요청이 실패하면 GPX 파일을 보존하고 게시를 중단합니다. 원인을 해결한 뒤 해당 GPX를 Telegram에 다시 보내면 재처리됩니다. **같은 GPX를 다시 보내면 중복 글이 생길 수 있으므로** 이미 게시됐는지 먼저 확인하세요.

프롬프트를 수정할 때는 기존 입력 변수(`distance`, `duration`, `pace_per_km`, `speed`, `weather`, `date`, `splits_text`, `heart_rate_text`, `cadence_text`, `elevation_text`)를 유지하세요. Python 형식 문자열이므로 JSON 예시의 중괄호는 `{{`와 `}}`로 씁니다. 수정 후 봇 컨테이너를 재생성합니다. 프롬프트를 읽지 못하거나 Gemini가 유효한 `title`·`summary`·`training` JSON을 반환하지 않으면 게시하지 않습니다.

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

테스트는 외부 API에 게시하지 않고 GPX 추출, 보고서, Gemini 오류 처리와 게시 중단 조건을 확인합니다.
