# SimWeb 통합 플랫폼 설계 (FEM · SPH · LBM)

작성 2026-11-20 · 상태: 설계안 (구현 전), 10절 결정 반영

여러 LLM-web 시뮬레이터를 하나의 플랫폼에서 오가며 쓰고, 같은 형상과 결과를 서로 넘겨 주는 구조를 정리한 문서입니다.

---

## 1. 목표

| 수준 | 사용자가 할 수 있는 것 |
|---|---|
| ① 포털 | 한 주소에서 상단 탭으로 FEM · SPH · LBM을 오감. 테마·LLM 설정을 한 번만 입력 |
| ② 공통 코어 | 세 앱이 같은 화면 틀·뷰어·LLM·채팅·단위·형상 입력을 씀. 새 해석기는 플러그인 하나로 추가 |
| ③ 연성 | 같은 형상으로 유체 해석(LBM·SPH) 결과 하중을 구조 해석(FEM) 하중으로 넘김 (단방향 → 이후 양방향) |

비목표: 해석기 내부(솔버 알고리즘)를 하나로 합치는 것. 각 해석기는 자기 저장소에서 독립적으로 발전합니다.

## 2. 현황 (2026-11-20)

| 저장소 | 실행 방식 | 화면 | LLM 처리 | 상태 |
|---|---|---|---|---|
| FEM-LLM-web | Python 서버 (CalculiX 등) | FEM 3-pane (기준) | Python `rules.py` + `llm.py`, ops JSON | 운영 중, `NOTE_SimWeb-Core.txt`에 이관 계획 |
| SPH-LLM-web | Python 서버 + Simweb-Core | FEM 3-pane | Simweb-Core `create_app(plugin)` | `stage1/wip`, `stage2/core` 진행 중 |
| Simweb-Core | Python 패키지 + `/core` 정적 파일 | `style.css`, `viewer.js`, `panel.js`, `chart.js`, `fields.js` | `simweb.llm` (OpenAI 호환) | `stage1/wip`, `stage2/results` 진행 중, main은 비어 있음 |
| lbm-flow-lab (→ LBM-LLM-web) | **정적 페이지** (GitHub Pages), 계산은 브라우저 WebGPU/Worker | FEM 3-pane (2026-11-20 전환) | JS `rules.js` + 브라우저 직접 LLM 호출 (A안) | main 반영 완료 |

공통점: 세 앱 모두 **같은 화면 구성**, **같은 ops 계약** (`{"ops":[...],"reply":"..."}`), **같은 LLM 방식 4종**(규칙 우선 / LLM 우선 / LLM만 / 규칙만), **되돌리기**를 이미 공유합니다.

차이점: FEM·SPH는 서버형, LBM은 정적형. 규칙 파서 언어가 Python / JS로 나뉨. LBM 화면 단위는 mm · m/s · Pa, 코어 단위는 mm · tonne · s · N · MPa.

## 3. 목표 구조

```
                    ┌──────────────── simweb-platform (Python 서버 1개) ────────────────┐
 브라우저 ─────────▶ │  /            포털: 앱 탭, 프로젝트 열기/저장, 공통 LLM 설정      │
                    │  /core/*      Simweb-Core 정적 파일 (style, viewer, panel, fields…)  │
                    │  /fem/*       FEM 플러그인 (서버 계산: CalculiX)                     │
                    │  /sph/*       SPH 플러그인 (서버 계산)                              │
                    │  /lbm/*       LBM 플러그인 (정적 파일 제공, 계산은 브라우저 WebGPU)  │
                    │  /api/project 공통 프로젝트 (형상·단위·앱별 스펙·결과 참조)         │
                    │  /api/llm/*   공통 LLM 설정·중계 (키는 서버 환경변수 또는 사용자 입력) │
                    └──────────────────────────────────────────────────────────────────┘
```

- 플랫폼 서버는 Simweb-Core의 `create_app(plugin)`을 앱마다 마운트해 하나로 묶습니다 (`simweb.platform.mount(app, plugins)` 추가 예정).
- 각 앱 저장소는 지금처럼 단독 실행도 계속 가능해야 합니다 (`python -m femweb`, `python -m sphweb`, LBM은 GitHub Pages).

### 3.1 플러그인 두 종류

| 종류 | 대상 | 계산 위치 | ops 적용 위치 | 규칙 파서 |
|---|---|---|---|---|
| 서버 플러그인 | FEM, SPH | 서버 | 서버 `apply_ops` (순수 함수) | Python `plugin.rules` |
| 클라이언트 플러그인 | LBM | 브라우저 | 브라우저 `adapter.apply` | JS `adapter.rules` |

`panel.js`의 채팅 흐름은 두 종류가 같고, **전송 계층만** 다릅니다.

```
mountRight(aside, { transport: 'server' })            → POST /api/chat (FEM, SPH)
mountRight(aside, { transport: 'client', adapter })   → adapter.rules → (필요 시) LLM → adapter.apply (LBM)
```

클라이언트 어댑터 계약 (LBM `js/simweb/panel.js` 기준, 그대로 코어로 옮김):

| 항목 | 내용 |
|---|---|
| `system` | LLM 시스템 프롬프트 (ops 문법) |
| `rules(text)` | `{ops, reply, ask[], unknown[], run, undo, answered, complete}` |
| `context()` | LLM에 보낼 현재 상태 요약 문자열 (`SPEC:` · `PARAMS:` · `STATE:` · `EXAMPLES:`) |
| `apply(ops)` | 검증 후 적용, 실패 시 예외 (메시지는 LLM 재요청에 그대로 사용) |
| `snapshot()` / `restore(s)` | 되돌리기·실패 복원 |
| `run()` | 해석 실행 |
| `chips`, `placeholder`, `welcome` | 화면 문구 |

클라이언트 플러그인의 LLM 호출은 두 경로를 모두 지원합니다.
- 플랫폼 안: `/api/llm/chat` 중계 (키를 서버에 둠, CORS 문제 없음)
- 단독 정적 실행: 브라우저 직접 호출 (A안, 키는 사용자 브라우저)

## 4. 공통 데이터

### 4.1 프로젝트 파일 `project.simweb.json`

```json
{
  "version": 1,
  "units": "mm-tonne-s-N-MPa",
  "geometry": { "...": "Geometry.to_dict() — vertices, faces, face_group, lines, line_group, hinges" },
  "frames": { "world": "Rhino 월드 좌표 그대로, z 위" },
  "apps": {
    "fem": { "spec": {}, "results": ["results/fem_static.npz"] },
    "lbm": { "spec": {}, "results": ["results/lbm_surface_loads.json"] },
    "sph": { "spec": {}, "results": [] }
  },
  "links": [
    { "from": "lbm", "kind": "surface_pressure", "to": "fem", "groups": ["roof", "wall_n"], "stat": "mean", "factor": 1.0 }
  ]
}
```

- 형상은 한 벌만 두고, 앱별 스펙은 그 형상의 **그룹 이름**(`face_group`)으로 위치를 가리킵니다. 그래서 탭을 바꿔도 같은 면을 같은 이름으로 부릅니다.
- 대용량 메쉬·결과는 파일로 두고 프로젝트에는 경로만 둡니다.

### 4.2 단위 정책

- 내부·파일·앱 간 전달: 코어 단위 **mm · tonne · s · N · MPa** (`simweb.units`)
- 화면 표시·문장 해석: 분야 관례 단위 허용 (유체: m/s, Pa, kg/m³ / 구조: N, MPa)
- 변환은 **앱 경계에서 한 번만** 합니다 (LBM 어댑터가 프로젝트로 내보낼 때 Pa → MPa, m/s → mm/s)

### 4.3 좌표

모든 앱이 Rhino 월드 좌표(mm, z 위)를 그대로 씁니다. LBM 도메인 원점·SPH 탱크·FEM 모델 모두 같은 좌표계라 별도 변환이 없습니다.

## 5. 앱 간 이동 (①·②)

- 포털 상단 탭: `FEM · SPH · LBM · Theory`. 탭 전환 시 현재 프로젝트를 유지하고, 각 앱은 `GET /api/project`로 형상·자기 스펙을 불러옵니다.
- 형상을 한 앱에서 바꾸면 (예: FEM에서 STL 교체) 다른 앱에 "형상이 바뀌었습니다 · 다시 불러오기" 배지를 띄웁니다. 자동 덮어쓰기는 하지 않습니다.
- LLM 설정(엔드포인트·모델·키·방식)은 포털 한 곳에서 관리하고 앱 패널은 읽기만 합니다.

## 6. 연성 (③)

### 6.1 단방향: 유체 → 구조 (1차 목표)

```
LBM/SPH 해석 → 객체 표면 하중 추출 → project.links → FEM 하중 생성 → FEM 해석
```

| 단계 | 담당 | 내용 |
|---|---|---|
| 표면 하중 추출 | LBM | 운동량 교환 링크를 객체 삼각형에 귀속 → 삼각형별 평균 압력 · 전단(시간 평균 구간 지정), 단위 MPa |
| 내보내기 형식 | 코어 | `surface_loads.json`: `{faces:[i…], p:[MPa…], t:[[MPa,MPa,MPa]…], area:[mm²…], stat:"mean"|"max"|"rms", window:[t0,t1]}` |
| 하중 매핑 | 코어 | 형상이 같으면 면 번호 그대로, 다르면 최근접 면 투영 + 합력·합모멘트 보존 보정 |
| 하중 적용 | FEM | 그룹별 분포압 / 절점력으로 변환, 합력 표시 |

검증 기준: 유체 쪽 객체 합력과 FEM 쪽 반력의 차이 1% 이내 (매핑 오차 확인용).

### 6.2 양방향 (이후)

- 준정적 반복: 유체 → 구조 변형 → 형상 갱신 → 유체 재계산 (2~5회)
- LBM 내부의 간이 FSI(강체 1축 회전)는 그대로 두고, 변형체 FSI는 이 경로로만 다룹니다.

## 7. LLM 통합

- 앱 안 지시: 지금처럼 각 앱의 규칙 파서 + 시스템 프롬프트.
- 플랫폼 수준 지시: 포털 채팅에 조정용 op 두 개를 추가합니다.

| op | 예 |
|---|---|
| `{"op":"switch_app","app":"lbm"}` | "LBM으로 가서 바람 조건 잡아줘" |
| `{"op":"transfer","from":"lbm","to":"fem","kind":"surface_pressure","groups":[…],"stat":"mean"}` | "방금 풍압을 FEM 지붕 하중으로 넘겨줘" |

- 포털은 문장을 앱 지시와 조정 지시로 나눠, 앱 지시는 해당 앱 플러그인에 그대로 넘깁니다.
- LLM에는 형상 메쉬·결과 배열을 보내지 않습니다 (요약과 그룹 이름만).

## 8. 호스팅

| 실행 형태 | 내용 | 대상 |
|---|---|---|
| 플랫폼 서버 | `python -m simweb.platform` (또는 Docker) — 세 앱 + 프로젝트 + LLM 중계 | 사내 PC·서버, 통합 사용 |
| 앱 단독 서버 | `python -m femweb`, `python -m sphweb` | 개별 개발 |
| LBM 정적 | GitHub Pages | 설치 없이 데모·공유 |

LBM은 두 형태를 모두 유지합니다. 같은 `web/` 파일을 플랫폼은 `/lbm/`으로 제공하고, 정적 배포는 그대로 Pages에 둡니다. 경로는 모두 상대경로입니다.

## 9. 단계별 계획

| 단계 | 작업 | 완료 기준 |
|---|---|---|
| ① 포털 | `simweb.platform`: 앱 마운트, 상단 탭, 공통 LLM 설정 (사용자 입력) | 한 주소에서 세 앱 전환, LLM 설정 1회 입력 |
| ②-a 코어 화면 | `panel.js`에 `transport: 'client'` 추가 (LBM `js/simweb/` 이관), `simweb.css` 차이 흡수 | LBM이 `/core` 파일만으로 동작 |
| ②-b 코어 데이터 | `project.simweb.json` 읽기·쓰기, `/api/project`, 그룹 이름 기반 참조 | FEM에서 올린 형상이 LBM·SPH에 그대로 열림 |
| ②-c FEM 이관 | `NOTE_SimWeb-Core.txt` 순서대로 FEM을 플러그인으로 | FEM 기존 시험 통과 |
| ③-a 표면 하중 | LBM 삼각형별 표면 압력 추출·내보내기 | 구 · 원기둥 표면 Cp 분포 문헌 비교 |
| ③-b 매핑·적용 | 코어 매핑, FEM 하중 적용, 합력 검증 | 합력 차 1% 이내 |
| ③-c 지시 | `switch_app`, `transfer` op, 포털 채팅 | "풍압을 FEM으로" 한 문장으로 연성 1회 |

①과 ②-a는 현재 구조로 바로 시작할 수 있습니다. ②-c는 SPH 쪽 `stage2` 안정화 뒤에 진행합니다.

## 10. 결정 사항 (2026-11-20)

| 항목 | 결정 | 반영 |
|---|---|---|
| 플랫폼 위치 | **Simweb-Core 안** `simweb.platform` 모듈 | 별도 저장소 만들지 않음 |
| LLM 키 | **사용자 입력** (엔드포인트·모델·키 모두 빈칸 기본, 누구나 자기 API로 교체) | 서버 환경변수는 선택 사항으로만 유지, 포털 LLM 설정 칸이 기본 |
| 규칙 파서 | **하나로 병합** (Python / JS 병행 안 함) | 아래 10.1 |
| 유체 하중 통계 | 미정 — 아래 10.2 설명 후 결정 | |

### 10.1 규칙 파서 병합 방향 (안)

- 공통 엔진 하나: 절 분리, 숫자·단위 해석, 면·방향·선택 표현, 조사·어미 처리, 남은 말 판정 → `simweb` 공통 규칙 엔진
- 앱별로는 문법 표(어떤 표현이 어떤 op가 되는지)만 플러그인으로 둠
- 언어는 플랫폼 서버 기준 Python 하나로 두고, LBM도 플랫폼 안에서는 서버 규칙 엔진을 호출 (`/api/rules`)
- LBM 정적 배포(GitHub Pages)는 서버가 없으므로 현재 JS 규칙을 유지하되 기능 추가는 공통 엔진에만 함 (정적 판은 데모용)

### 10.2 유체 하중 통계값이란

유체 하중은 시간에 따라 흔들립니다 (와류 방출, 난류). FEM은 보통 하나의 정적 하중을 받으므로 어떤 값을 넘길지 정해야 합니다.

| 값 | 의미 | 쓰임 |
|---|---|---|
| 평균 | 일정 구간 시간 평균 | 평균 변형, 장기(크리프) 검토 |
| 최대 | 구간 중 가장 큰 순간값 | 해석 길이에 따라 달라져 재현성 낮음 |
| RMS | 평균 주위 흔들림 크기 | 피로, 진동 검토 |
| 피크 = 평균 + g·RMS (g ≈ 3~3.5) | 풍하중 기준에서 쓰는 설계 피크 | 강도 검토 (권장) |

제안: 기본은 **평균**과 **피크(평균 + 3.5·RMS)** 두 하중 케이스를 함께 넘기고, FEM에서 케이스 이름에 표기.

## 11. 위험과 대응

| 위험 | 대응 |
|---|---|
| 앱마다 스펙 형식이 계속 달라짐 | 형상·단위·그룹 이름만 공통으로 강제하고, 앱 스펙 내부는 자유 |
| 코어 변경이 앱을 깨뜨림 | 코어 CI에서 SPH·LBM·FEM 시험을 함께 실행 (CLAUDE.md 규칙 유지) |
| 대용량 형상(수백 MB STL) | 프로젝트에는 경로만, 앱은 자체 단순화(LBM: Δx/2 정점 클러스터링) 후 사용 |
| 사내망에서 LLM CORS·인증서 | 플랫폼 서버 중계(`simweb.llm`의 프록시·사내 인증서 처리) 사용 |
| 유체 하중의 시간 변동 | 평균·최대·RMS를 함께 내보내고, 어느 값을 넘겼는지 FEM 하중 이름에 표기 |
