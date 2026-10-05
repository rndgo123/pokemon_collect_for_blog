# Python RSS 수집 — 첫 단계

2026-10-05 / Python 3.11+ / 추가 패키지 없음.

기존 이벤트 수집·SQLite·변경 이력·조회 CLI에 RSS 2.0 및 Atom을 연결했다.
원문 본문·이미지는 내려받지 않고 제목·링크·게시 시각만 저장한다.
실제 포켓몬 굿즈 공식 RSS는 아직 검증·활성화하지 않았다. 예제 URL은 공식 피드가 아니다.

## 실행

프로젝트 루트에서 실행한다. 피드 제공과 자동 수집·저장 조건을 확인한 후
`config/rss_sources.example.toml`을 별도 설정 파일로 복사하고 값을 수정한다.
`enabled=true`, `policy_approved=true`, 실제 `feed_url`, 검토한 `policy_url`이 필요하다.

```powershell
python main.py --db data/goods.db collect --config config/my_rss.toml --source goods_rss
python main.py --db data/goods.db events --category GOODS
python main.py --db data/goods.db digest --days 7
```

기존 기본 설정은 유지했다. 신규 RSS만 실행하려면 별도 설정 파일을 사용한다.
전체 collect도 이제 `enabled=false` 소스를 요청하지 않는다.
RSS는 한번에 피드 1개를 읽는다. 상세 기사·이미지·이전 페이지를 추가 요청하지 않는다.
수집 시각은 해시에서 제외하며, GUID/Atom id(없으면 링크)로 동일 항목을 식별한다.
피드에서 사라진 항목을 삭제하거나 종료 처리하지 않는다.
`country`는 발행 소스 국가이며 국내 출시·직배송 가능 여부를 의미하지 않는다.

## 안전 장치 및 한계

- 비승인·비활성 소스는 HTTP 요청 전에 중단한다.
- 403/429는 즉시 중단하고 HTML 또는 브라우저로 우회하지 않는다.
- HTML 응답, 빈 피드, 잘못된 날짜·링크, DTD는 실패 처리한다.
- 최대 2 MiB; 네트워크 일시 오류 재시도는 기존 HTTP 함수의 3회 정책을 재사용한다.
- 항목 파싱이 끝난 뒤 저장하여 잘못된 피드가 기존 데이터를 덮어쓰지 않게 한다.
- `policy_approved`는 검토 기록을 반영하는 수동 설정이지 법적 허가 판정기가 아니다.
- 지원 범위는 RSS 2.0 / Atom이다. RSS 1.0, 자동 발견, ETag, 페이지 추적은 미구현이다.
- UTC 시각으로 정규화한다. 게시 시각을 행사·판매 시작일로 추정하지 않는다.
- 검증은 가상 피드 기반이며 실서비스 수집 성공을 뜻하지 않는다.

## 테스트

```powershell
$env:PYTHONPATH = 'src'
python -m unittest discover -s tests -v
```

RSS/Atom 정규화, 신규→동일→변경, 실패 시 기존 데이터 보존,
비활성 소스 요청 차단, 403/429 중단, 응답 크기 제한을 검증한다.

## 다음에 필요한 입력

수집 정책을 검토할 공식 피드 URL 또는 운영자의 이용 허가가 필요하다.
검색 결과만으로 RSS 부재나 수집 허가를 단정하지 않는다.
일본 공식 [이용 안내](https://www.pokemon.co.jp/rules/)에는 콘텐츠 복제·재게시 제한이 있으므로
이번 단계에서 본문·이미지 복제나 상업적 이용을 승인된 것으로 취급하지 않는다.
RSS 미확인 사이트의 HTML/API 수집은 별도 검토 후 추가한다.
