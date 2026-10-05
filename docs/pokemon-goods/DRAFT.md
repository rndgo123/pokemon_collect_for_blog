# 초안 출력

작성 전에 Git에 등록된 [문체·글감 선별 기준](EDITORIAL.md)을 먼저 읽는다. 로컬 SEO 지침만 기억에 의존해 적용하지 않는다.

2026-10-05. 템플릿 기반 평서형 문체, 정보 표, 출처, 해시태그를 출력한다.
LLM이나 자동 번역이 아닌 고정 템플릿이다. 긴 상품 설명은 출처를 검토한 편집 메모가 있어야 한다.

```powershell
python main.py draft --id EVENT_ID
python main.py draft --id EVENT_ID --output reports/draft.md
python main.py draft --id EVENT_ID --notes config/draft_kakao.example.toml --output reports/kakao-draft.md
```

마지막 명령의 메모는 해당 카카오 상품 URL의 항목에만 적용할 수 있다.
`EVENT_ID`는 events/digest 결과에서 가져온다. 예제의 가격은 2026-10-05 확인 기록이며
새 발행 시 다시 확인한다. 직접 만든 사실·문장·출처를 TOML로 넣을 수 있다.

- 입력 메모는 `reviewed=true`와 동일 `source_url`이 필요하다.
- `title`, `intro`(문단 목록), `facts`(표 항목), `sections`(제목·문단), `sources`(이름·URL)를 지원한다.
- 수집된 공지 게시일과 행사 일정을 판매 시작일로 바꾸지 않는다.
- 공지 게시일은 한국 시간으로 표시한다. 현지 날짜와 다를 수 있다.
- 디지털 굿즈에 없는 장소·행사 기간을 채우지 않는다.
- 원문 설명을 그대로 복제하지 않고 기본 초안에는 사실만 사용한다.
- `reviewed=true` 자체가 진위를 보장하지 않는다. 작성자가 실제 출처를 확인해야 한다.
- 결과는 UTF-8 Markdown이고 기존 파일은 덮어쓰지 않는다.
- 이미지 다운로드·매칭·네이버 입력·발행은 하지 않는다.
- 네이버 소제목 크기·정렬은 Markdown이 아니라 편집기 적용 단계다.
- 개인 문체 기준은 `나왔다`, `올라와 있다`, `확인하는 게 좋겠다` 등 짧은 평서형이다.
  감상·구매·방문 경험은 자동 생성하지 않는다.
