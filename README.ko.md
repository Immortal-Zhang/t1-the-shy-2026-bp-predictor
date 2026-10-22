# LOL Worlds 2026 BP Predictor

[English](README.md) · [简体中文](README.zh-CN.md) · **한국어**

실제 리그 오브 레전드 프로 경기로 학습한 **단일 경기 승률 예측 및 밴픽 분석 도구**입니다. React 기반 밴픽 화면에서 두 팀의 선수 10명과 챔피언 10명을 선택하면 FastAPI가 학습된 CatBoost 모델로 예측합니다. 임의의 챔피언 점수, 고정 승률, LLM의 추측을 예측값으로 사용하지 않습니다.

현재 웹 인터페이스는 **중국어**입니다. 이 문서는 한국어 사용 안내이며, 한국어 UI가 구현되었다는 의미는 아닙니다. 이 저장소는 로컬에서 실행하는 연구 도구의 소스 코드이며, 운영 중인 공개 웹 서비스는 아닙니다.

![실제 모델을 연결한 공격적 판단 화면](reports/aggressive/screenshots/chromium-aggressive.png)

## 주요 기능

- 출처를 확인한 2026 월드 챔피언십 참가 팀 19개, 공식 Data Dragon 챔피언 173개, 데이터에 포함된 해당 대회·패치 경기 22개.
- 팀 검색, 시점별 최근 출전 선수 자동 입력, 수동 선수 변경, TOP/JUNGLE/MID/BOT/SUPPORT별 챔피언 선택 및 양 팀 밴 입력.
- 챔피언 중복·밴 충돌 검사, 진영 교환, 초기화, 실제 경기 밴픽 불러오기. 입력이 바뀌면 이전 예측은 무효화됩니다.
- 맵의 블루·레드 진영과 밴픽 선픽 권한을 별도로 입력합니다. 경기 패치와 예측 시점 `as_of`도 지정합니다.
- 보정된 승률, 밴픽 전후 모델 비교, SHAP 설명, 선수의 해당 챔피언 사용 기록, 포지션별 대진 및 챔피언 조합 통계.
- 브라우저 로컬 예측 기록과 실제 결과 수동 입력. 과거 기록은 당시 모델의 결과를 그대로 보존하며, 수동 결과는 별도로 표시합니다.
- Bo3/Bo5 Fearless Draft의 이전 경기 챔피언 기록과 재선택 제한. Bo5는 최대 4경기의 이전 밴픽을 기록할 수 있습니다.

**지원 범위:** 밴픽을 편집한 뒤 완성된 10인 조합의 승률을 다시 예측합니다. 아직 완성되지 않은 밴픽의 매 선택 단계별 실시간 승률이나 **Bo5 시리즈 전체 승률은 제공하지 않습니다.** Fearless 이력은 현재 단일 경기의 선택 제약이며, 시리즈 예측 모델이 아닙니다.

## 세 가지 표시 모드

| 모드 | 표시 내용 |
|---|---|
| 표준 | 기존 모델의 보정된 블루·레드 승률 |
| 공격적 판단 — 기본 | 예측 승리 팀, 양 팀 지지 지수, 우세 등급, 핵심 근거 3개, 반대 근거·위험 2개, 데이터 신뢰도 |
| 극한 판단 | 결론과 실패 위험을 더 강조하되, 공격적 모드의 승리 팀·지수·등급은 유지 |

**지지 지수는 승리 확률이 아닙니다.** 모델의 원시 점수와 결정 경계 사이 거리를 검증 기간의 점수 분포에서 순위화한 값입니다. 기술 상세 화면에 기존 보정 확률과 실험 모델의 보정 확률을 따로 표시합니다. 51%를 80% 승률로 바꾸거나 모든 경기에 최소 65% 승률을 부여하지 않습니다.

선택된 실험 모델은 검증 AUC 기준을 충족했지만, 기존 테스트 기간의 전체 성능 향상은 입증하지 못했습니다. 화면에도 **실험적 판단**임을 표시합니다. 모델 근거가 부족하면 그 사실을 표시하고, 근거를 채우기 위해 전술적 설명을 만들어 내지 않습니다. 종합 우세 등급과 밴픽 특성의 순기여도도 구분합니다.

## 실제 데이터와 평가

유효한 역사적 경기 **28,738개**를 사용했습니다. 데이터의 실제 경기 기록은 **2026-10-18 19:48:36 UTC**까지이며, 기존 배포 모델의 학습·선택·보정에 사용한 라벨의 가용 시점은 **2025-12-30 00:00:00 UTC**까지입니다.

학습 / 검증 / 별도 확률 보정 / 테스트는 시간순으로 **15,717 / 2,968 / 716 / 9,309경기**입니다. 같은 경기가 양쪽 분할에 들어가지 않으며, 결과가 아직 알려지지 않은 경계의 경기는 제외합니다. 역사적 특성은 경기 시작과 `as_of`보다 앞서 알려진 결과로만 계산합니다. 현재 경기의 KDA, 골드, 피해량 등의 경기 후 정보는 예측 입력이 아닙니다.

| 9,309경기 테스트 | Accuracy | ROC-AUC | Log Loss | Brier |
|---|---:|---:|---:|---:|
| 기존 표준 모델 | 63.95% | 0.697653 | 0.630171 | 0.220150 |
| 선택된 실험 모델 | 63.64% | 0.692046 | 0.633306 | 0.221484 |

실험에서는 최근 상태의 시간 감쇠, 현재 패치의 선수·챔피언 기록, 미드·정글 및 바텀·서포터 조합, 동일 라인업 경험 등 **190개 특성을 추가**해 총 374개 특성으로 후보 3개를 실제 학습했습니다. 후보 선택에는 검증 결과만 사용했으며, 테스트 점수가 더 높은 후보로 사후 교체하지 않았습니다.

| 실험 판단 등급 | 경기 수 | 적중률 |
|---|---:|---:|
| 근소한 우세 | 2,649 | 51.26% |
| 뚜렷한 우세 | 3,963 | 62.93% |
| 강한 지지 | 2,697 | 76.83% |

강한 지지는 지지 지수 85 이상이며, 검증 그룹의 표본 100개 이상·95% Wilson 하한 60% 이상 조건을 추가로 요구합니다. 기존 모델에 같은 규칙을 적용한 강한 지지 그룹의 적중률은 **78.02%**이므로, 강한 판단의 성능 개선도 입증되지 않았습니다.

이 2026 테스트 기간은 이전 개발 단계에서 이미 확인한 데이터입니다. 실험 모델의 비교는 **회고적 연구 결과이며 새롭게 확보한 독립 확인 증거가 아닙니다.** 목표 월드 챔피언십 패치의 표본은 22경기뿐이므로 대회 전용 정확도나 보정의 신뢰성을 보장하지 않습니다. 학습과 평가는 하나의 시드·시간 분할을 사용했습니다.

[실험 보고서](reports/aggressive/experiment_results.md) · [등급별 평가](reports/aggressive/judgment_evaluation.md) · [검증 보고서](reports/aggressive/TEST_RESULTS.md) · [최종 실행 확인](reports/acceptance/README.md)

## 처음 복제한 저장소에서 실행하기

**Git에는 소스 코드, 평가 보고서, 캐시된 카탈로그 JSON이 포함됩니다. 원본 CSV, 처리된 경기 데이터, 학습된 모델 바이너리는 포함되지 않습니다.** 처음 복제한 뒤에는 아래 명령으로 실제 데이터를 준비하고 모델을 학습해야 합니다. 모델이 없는 상태에서는 503 오류 또는 사용 불가 상태를 표시하며, 예시 승률을 대신 반환하지 않습니다.

필수 환경: Python 3.11 이상, Node.js 20.19 이상(20.x) 또는 22.12 이상, npm. 로컬 macOS에서 실행을 확인했으며 유료 클라우드 서비스는 필요하지 않습니다.

```bash
git clone https://github.com/Immortal-Zhang/lol-worlds-2026-bp-predictor.git
cd lol-worlds-2026-bp-predictor
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock.txt
python -m pip install -e '.[dev]'
npm --prefix frontend ci

worlds-bp download --years 2024 2025 2026
worlds-bp normalize --as-of 2026-10-22T00:00:00Z
worlds-bp train --config configs/train.json
worlds-bp make-replay --as-of 2026-10-22T00:00:00Z

# 기본 공격적 판단도 사용하려면 실험 모델과 지수 규칙을 생성합니다.
python scripts/train_aggressive.py
python scripts/evaluate_aggressive.py

./scripts/start_local.sh --production
```

웹사이트: **http://127.0.0.1:5173** · API 문서: **http://127.0.0.1:8026/docs**

데이터와 두 모델이 이미 준비된 로컬 환경에서는 시작 스크립트만 실행하면 됩니다. 같은 프로젝트의 서비스가 실행 중이면 재사용합니다. 코드를 변경한 경우 기존 백엔드를 재시작해야 합니다. macOS에서 시작 스크립트는 설치되어 있는 경우 Homebrew Node를 우선 사용합니다.

다운로드 출처의 파일이 변경되면 같은 명령이라도 원래 보고서와 동일한 표본·결과가 나오지 않을 수 있습니다. 원본 파일의 출처·다운로드 시각·SHA-256 및 실제 데이터 종료 시점을 기록합니다. 다운로드가 불가능할 때는 임의 데이터를 만들지 말고, [수동 CSV 가져오기 안내](docs/TECHNICAL.zh-CN.md)를 따르세요. 카탈로그를 갱신할 때는 `python scripts/update_catalog.py`를 실행합니다.

## API와 재현 가능한 테스트

- `POST /predict`: 표준 모델의 단일 경기 보정 확률.
- `POST /analyze`: 기존 확률에 모델 비교, 역사 통계, SHAP, `judgment`를 추가합니다. 공격적 판단의 산출물이 없거나 손상되면 그 부분만 사용 불가로 표시하고, 유효한 표준 예측은 유지합니다.
- `GET /health`, `/catalog`, `/teams`, `/teams/{id}/roster`, `/matches`, `/players`: 상태 및 시점별 참고 데이터.
- 주요 입력: `as_of`, `scheduled_start`, `league`, `patch`, `blue`, `red`, `first_pick_side`. 양 팀에 `team_id`, 5명의 `players`(`role/player_id/champion`), `bans`를 지정합니다. `/analyze`의 `draft_context`로 Fearless 이력을 전달합니다.

```bash
# 프로젝트 루트에서, 데이터와 모델을 준비한 후 실행
.venv/bin/python -m pytest -q
npm --prefix frontend run test
npm --prefix frontend run build
cd frontend
npx playwright install chromium webkit
# 앞서 시작한 로컬 프런트엔드와 API가 실행 중이어야 합니다.
npx playwright test --config playwright.aggressive.config.ts
```

실제 개발 환경에서 **Pytest 263개, Vitest 61개, Chrome/WebKit 프로덕션 E2E 16개**와 엄격한 TypeScript 검사·프로덕션 빌드가 통과했습니다. 코드만 복제해 데이터나 모델이 없는 경우 일부 실제 모델 통합 테스트는 건너뛸 수 있습니다. 이것을 예측 검증 성공으로 해석해서는 안 됩니다. 단위 테스트의 합성 입력은 구조 검사용이며 학습·실제 평가에 사용하지 않습니다.

## 데이터, 권리 및 한계

- 주 출처: [ChainCC](https://chaincc.lol/free/data/). 수집 시 페이지에 명시된 조건은 **CC BY 4.0**입니다. 출처 표기: `ChainCC. League of Legends esports match dataset. https://chaincc.lol/free/data/`. 본 프로젝트는 데이터 정제, 격리, 식별자 정규화 및 역사적 특성 변환을 수행했습니다.
- 대체 출처: [Oracle's Elixir](https://oracleselixir.com/tools/downloads). 기록된 수집 시도에서는 HTTP 403을 반환했습니다. 별도로 사용할 때는 해당 출처의 조건을 확인해야 하며, ChainCC의 라이선스를 그대로 적용하지 않습니다.
- 챔피언 자료·이미지: [Riot Data Dragon](https://developer.riotgames.com/docs/lol#data-dragon). [Riot 개발자 정책](https://developer.riotgames.com/policies/general)을 확인해야 합니다. 팀 로고의 재사용 권한을 확인하지 못한 경우 중립적인 약어 배지를 표시합니다.
- 소스 코드의 별도 오픈소스 라이선스는 아직 지정되지 않았습니다. 공개 저장소라는 사실이 데이터나 Riot 자료에 대한 추가 권한을 부여하지 않습니다.
- Riot Games의 공식 제품이 아니며 Riot의 승인·후원과 무관합니다. LoL 관련 자산의 권리는 Riot Games에 있습니다. 연구·오락용 분석 도구이며 도박·베팅 추천을 제공하지 않습니다.
- 자동 입력 선수는 날짜가 표시된 **실제 출전 기록**이며 현재 선발 확정 명단이 아닙니다. 원본에 불변의 선수 ID가 없어, 일부 이름 기반 내부 식별자는 실인물 연결이 검증되지 않았습니다.
- 보정된 승률은 결과 보장이 아닙니다. SHAP는 모델 기여도이며 인과관계가 아닙니다. 검증된 군중 제어·이니시에이팅 점수, 초중후반 파워 곡선, 팀 전술 스타일 상성은 아직 제공하지 않습니다.
- 기본 월드 챔피언십 설정은 `26.20`이며 시작 시 공식 발표를 확인합니다. 원본 데이터의 `16.20`과는 명시적으로 확인한 별칭만 대응시킵니다. 수집 범위를 벗어난 데이터와 향후 규칙 변경은 별도 검증이 필요합니다.

Python/Pandas/DuckDB/CatBoost/Scikit-learn/FastAPI와 React/TypeScript/Vite/Tailwind CSS/Zustand/Recharts를 사용합니다. 구현은 `src/`, 웹은 `frontend/`, 설정은 `configs/`, 검증은 `tests/`와 `reports/`에 있습니다. 상세한 데이터·시간 경계·훈련 방법은 [기술 문서(중국어)](docs/TECHNICAL.zh-CN.md)를 참고하세요.
