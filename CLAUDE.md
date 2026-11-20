# Simweb-Core 개발 안내 (Claude Code 용)

FEM-LLM-web, SPH-LLM-web 등이 함께 쓰는 공통 모듈. 화면 디자인 기준은 FEM-LLM-web.

## 작업 방식
- 대화와 화면 문구는 한국어 존댓말. 코드에 주석을 달지 않음. 큰 파일은 필요한 곳만 수정
- 단위 mm · tonne · s · N · MPa
- 이 저장소를 고치면 쓰는 앱(SPH-LLM-web 등)의 시험도 같이 돌려 깨지지 않는지 확인
- 앱 하나에만 필요한 기능은 앱 저장소에 둠. 두 앱 이상이 쓰게 될 때 이곳으로 옮김
- 확인하지 못한 것은 확인하지 못했다고 보고

## 구조
- `simweb/app.py`: `create_app(plugin)`. 플러그인 계약은 README 참고. `apply_ops` 는 순수 함수여야 함 (사본을 받아 새 스펙 반환)
- `simweb/llm.py`: 환경 변수 접두사는 `PREFIXES` (앱이 앞에 자기 접두사를 넣음)
- `simweb/geometry.py`: `Geometry` (vertices, faces, face_group, lines, line_group, hinges), `load`, `to_view`, `to_dict`
- `simweb/web/`: `style.css`, `theory.css`, `js/{util,viewer,panel,chart,fields}.js`, `vendor/` (three.js). `fields.js` 는 격자 결과 표시(단면·벡터·유선·와도·Q 등치면)
- 시험: `python -m pytest tests -q`

## 커밋
- 커밋 메시지는 한국어 한 줄 요약 + 항목
