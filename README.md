# Simweb-Core

LLM-web 시뮬레이터들(FEM-LLM-web, SPH-LLM-web, 이후 LBM 등)이 함께 쓰는 공통 모듈입니다. 화면 디자인, 3D 뷰어, LLM 연결, 지오메트리 입력, 선택 문법, 단위를 한 곳에 둡니다. FEM-LLM-web (`feat/bh-web`, 2026-11-19) 에서 복사해 분리했습니다.

## 들어 있는 것

| 모듈 | 내용 | 출처 |
|---|---|---|
| `simweb.app` | `create_app(plugin)`: 상태·예제·업로드·수정 지시·채팅(규칙 우선 → LLM)·되돌리기·LLM 설정·케이스 내보내기 엔드포인트, `/core` 정적 파일 | FEM `server.py` |
| `simweb.llm` | OpenAI 호환 `/chat/completions` 호출, 프록시·사내 인증서, 중단, 연결 확인·응답 테스트 | FEM `llm.py` |
| `simweb.geometry` | OBJ(면·선·그룹·`hinge_` 접힘선)·STL 읽기, 정점 합치기, 파일 단위 변환, 닫힘 검사, 덩어리 분리, 특징 엣지 | FEM `io_obj.py`, `io_stl.py` |
| `simweb.select` | `group`, `plane`, `box`, `nearest`, `nodes`, `corners`, `and`/`or` | FEM `select.py` |
| `simweb.units` | mm · tonne · s · N · MPa 변환과 문장 속 단위 찾기, 유체 물성 | 새로 작성 |
| `simweb.progress` | 진행 표시 훅 | FEM `progress.py` |
| `web/style.css`, `web/theory.css` | FEM 화면·원리 문서 스타일 | FEM |
| `web/js/viewer.js` | three.js 뷰어 (조명, 축 기즈모, 화면 맞춤, 형상 그리기, 박스·화살표·점, PNG) | FEM `app.js` |
| `web/js/panel.js` | 오른쪽 패널: LLM 설정·상태·응답 테스트, 채팅, 예시 칩 | FEM `index.html`, `app.js` |
| `web/js/chart.js` | SVG 그래프 | FEM `app.js` |
| `web/js/fields.js` | 격자 결과 표시: 색 지도(turbo·발산형), 자동 범위, 단면 색·벡터·유선, 단면 수직 와도, Q-criterion 과 등치면(사면체 행진), 이진 프레임 해독 | lbm-flow-lab `results3d.js`, `flowviz.js`, `analysis3d.js` |

## 앱에서 쓰는 법

```python
from simweb import app as core

class Plugin:
    name = "myapp"; title = "My-LLM-web"; web_dir = ".../web"; examples_dir = ".../examples"
    llm_system = "..."
    def default_spec(self, geom): ...
    def apply_ops(self, spec, ops, geom): return spec, log
    def warnings(self, spec, geom): return []
    def rules(self, text, geom, spec): return ops, reply, {"complete": bool, "ask": [...], "unknown": [...], "action": None}
    def llm_context(self, geom, spec, result): return "MODEL: ...\nSPEC: ..."
    def state(self, S): return {}
    def examples(self): return []

app = core.create_app(Plugin())
```

화면은 `<link rel="stylesheet" href="/core/style.css">`, import map `{"three": "/core/vendor/three.module.js"}`, `import { createViewer } from '/core/js/viewer.js'` 처럼 씁니다. 사용 예: [SPH-LLM-web](https://github.com/MunkyunLEE/SPH-LLM-web).

## 방향

- 지금은 SPH-LLM-web 이 처음으로 사용합니다. FEM-LLM-web 은 건드리지 않았고, 안정된 뒤 따로 옮깁니다 (FEM 저장소의 `NOTE_SimWeb-Core.txt`)
- 결과 표시 항목(속도·압력·와도·벡터·단면·유선·Q-criterion)은 lbm-flow-lab 것을 옮겨 `web/js/fields.js` 에 두었습니다 (SPH 2단계). 격자 형식은 `{n:[nx,ny,nz], origin, h, u(3N), p(N), occ(N)}`, x 가 가장 빨리 변하는 순서
- 최종 목표: 앱끼리 같은 지오메트리(`Geometry.to_dict`)를 공유하고 바꿔 불러오는 통합 화면

## 설치·시험

```bash
pip install -e .
python -m pytest tests -q
```

## 라이선스

MIT. `web/vendor` 의 three.js 는 MIT (`THREE_LICENSE`).
