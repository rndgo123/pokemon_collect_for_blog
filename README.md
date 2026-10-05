# Pokémon Event Data Pipeline

공식 포켓몬 사이트의 이벤트·뉴스를 개인용으로 수집·정규화하여 블로그 소재를 찾는 데이터 파이프라인이다.

> 현재 상태: **RSS 수집 연결 및 굿즈·콜라보 글감 선별 구현** (2026-10-05, Asia/Seoul). 기존 Phase 1~15 기록은 2026-09-18 기준의 개발 이력이다. 실제 공식 RSS는 아직 활성화하지 않았다.

## 개발 원칙

- 공식 소스만 사용한다.
- 신규 소스는 사용 가능한 RSS/Feed → 공식 공개 API → 정책 허용 HTML 순으로 검토한다. 기존 사이트 내부 JSON endpoint는 공식 공개 API와 구분하며, RSS 실패 시 자동 fallback하지 않는다.
- robots.txt와 이용약관이 충돌하면 더 엄격한 조건을 따른다.
- 로그인, 캡차, 접근 제어, 속도 제한을 우회하지 않는다.
- 원문과 이미지를 재배포하지 않고, 출처 URL과 사실 정보 중심으로 저장한다.

## Phase 1 — 공식 소스 조사

### 결론

Phase 3의 첫 Collector는 **Pokémon Japan (`pokemon.co.jp`)**으로 한다. 목록 화면이 실제로 사용하는 비인증 JSON endpoint가 있고, 이벤트 카테고리가 명시적이며, JavaScript 렌더링이 필요 없다.

Pokémon GO와 Pokémon Center Online은 기술적으로 수집 가능하지만 현재 약관이 자동 수집을 금지하므로 **비활성 소스**로 관리한다. Playwright로 우회하지 않는다.

### 소스 매트릭스

| source id | 공식 목록 URL | 확인된 방식 | JS 필수 | 정책 판정 | 난이도 | 초기 처리 |
|---|---|---|---:|---|---|---|
| `pokemon_japan` | <https://www.pokemon.co.jp/info/cat_event/> | 사이트 내부 JSON endpoint + 상세 HTML | 아니오 | robots.txt에서 `/info/`, `/api/info/` 미차단 | 낮음 | **Phase 3 우선** |
| `pokemon_unite_jp` | <https://www.pokemonunite.jp/ja/topics/> | 서버 렌더 HTML | 아니오 | robots.txt는 upload/attachment만 차단 | 낮음 | 활성 후보 |
| `pokemon_korea` | <https://www.pokemonkorea.co.kr/news> | 초기 HTML + `POST /ajax/news` | 아니오 | `/robots.txt`가 robots 문서 대신 HTML을 반환; 약관에서 자동 수집 문구는 발견하지 못함 | 중간 | 활성 후보, 매우 낮은 빈도 |
| `pokemon_asia_sg` | <https://sg.portal-pokemon.com/topics/> | Next.js RSC HTML에 목록 데이터 내장 | 아니오 | robots.txt상 `/topics/` 허용; 약관은 콘텐츠 복제·게시·전송 제한 | 중간 | 메타데이터만 활성 후보 |
| `yadon_kagawa` | <https://yadon.my-kagawa.jp/> | 정적 HTML 허브와 캠페인별 페이지 | 아니오 | robots.txt 404; 개인정보 정책만 확인됨 | 높음 | 링크 변경 감시만 검토 |
| `pokemon_go` | <https://pokemongo.com/ko/news> | 서버 렌더 HTML + JSON-LD `ItemList` | 아니오 | 연결된 Scopely Explore 약관이 scraping/indexing과 bot/crawler 접근 금지 | 기술적으로 낮음 | **비활성: 허가 필요** |
| `pokemon_center_jp` | <https://www.pokemoncenter-online.com/feature-list/> | 서버 렌더 HTML | 아니오 | robots.txt는 허용하지만 이용약관 제6조가 bot·crawling·scraping 금지 | 기술적으로 낮음 | **비활성: 허가 필요** |

### 소스별 조사 메모

#### 1. Pokémon Japan

- 전체 뉴스: <https://www.pokemon.co.jp/info/>
- 이벤트: <https://www.pokemon.co.jp/info/cat_event/>
- 샵/포켓몬센터: <https://www.pokemon.co.jp/info/cat_pokecen/>
- 카드: <https://www.pokemon.co.jp/info/cat_card/>
- robots.txt: <https://www.pokemon.co.jp/robots.txt>
- 사이트 JavaScript가 목록을 구성할 때 사용하는 endpoint:

  ```text
  GET https://www.pokemon.co.jp/api/info/index/?limit=20&page=1&flg[]=11
  ```

  `flg[]=11`은 이벤트, `flg[]=8`은 샵, `flg[]=3`은 카드이다. 응답에 `results`, `paging`, `title`, `term`, `start_date`, `full_uniq`, `flags`가 포함된다.
- 공개 개발자 API로 문서화된 endpoint는 아니므로, 응답 스키마 변경을 감지하고 HTML 목록을 fallback으로 둘 가치가 있다.
- 상세 본문은 일반 HTML이다. 게시일과 이벤트 기간은 다르므로 본문에서 별도 추출해야 한다.

#### 2. Pokémon Korea

- 목록: <https://www.pokemonkorea.co.kr/news>
- 약관: <https://www.pokemonkorea.co.kr/terms>
- 초기 목록은 HTML에 있고, 더보기는 `POST /ajax/news` 호출이다. 페이지는 `pn`, `cate`, `sword`, `rcode=menu_news`를 전송한다.
- RSS, Atom, JSON-LD, 공개 API는 발견하지 못했다.
- `/robots.txt`가 `text/html`로 홈페이지 fallback을 반환하므로 크롤링 허용 선언으로 해석하지 않는다.
- AJAX 응답 앞에 내부 SQL 문자열이 포함되는 현상이 확인됐다. parser는 `#|#` 구분자 앞 문자열을 신뢰하지 않아야 한다.

#### 3. Pokémon GO

- 기존 <https://pokemongolive.com/ko/news>는 <https://pokemongo.com/ko/news>로 리디렉션된다.
- 목록은 서버 HTML과 JSON-LD `ItemList`에 포함되어 Playwright가 필요 없다.
- 연결된 약관: <https://explore.scopely.com/terms>
- 약관이 서비스/ucf58텐츠의 extract, scrape, index와 bot, spider, crawler, data-mining tool을 이용한 접근을 명시적으로 금지한다. 초기 버전에서는 Collector를 만들지 않는다.
- 향후 공식 RSS/API 제공 또는 서면 허가가 확인되면 활성화한다.

#### 4. Pokémon Center Online Japan

- 특집 목록: <https://www.pokemoncenter-online.com/feature-list/>
- 공지: <https://www.pokemoncenter-online.com/news/>
- robots.txt: <https://www.pokemoncenter-online.com/robots.txt>
- 이용약관: <https://www.pokemoncenter-online.com/terms.html>
- HTML은 서버에서 렌더되고 robots.txt는 차단 경로가 없다. 그러나 이용약관 제6조 17·18항이 자동화 수단으로의 정보 취득과 crawling/scraping을 금지한다.
- 포켓몬센터 이벤트는 가능한 범위에서 `pokemon.co.jp` 샵 카테고리(`flg[]=8`)로 대체한다.

#### 5. 야돈 파라다이스 in 가가와

- 허브: <https://yadon.my-kagawa.jp/>
- 굿즈: <https://yadon.my-kagawa.jp/goods/>
- 개인정보 정책: <https://yadon.my-kagawa.jp/privacy/>
- 뉴스 목록, API, RSS, 구조화 데이터를 발견하지 못했다. 홈페이지에서 현재 캠페인(예: `stamp2026/`, `marugame2026/`)을 직접 링크한다.
- robots.txt는 404다. 사이트가 현재 행사를 통합 목록으로 제공하지 않아, 홈 링크 변경 감시와 개별 캠페인 parser가 필요하다.
- 정확한 일정 필드를 안정적으로 뽑기 어려워 초기 우선순위는 낮춘다.

#### 6. Pokémon Asia Topics

- 영문 싱가포르 목록: <https://sg.portal-pokemon.com/topics/>
- robots.txt: <https://sg.portal-pokemon.com/robots.txt>
- 이용약관: <https://sg.portal-pokemon.com/termofuse/>
- Next.js RSC HTML에 `postId`, `slug`, `title`, `category`, 게시일, 페이지 정보가 들어 있다. 기본 6건이며 `page`, `limit`, `total`을 확인할 수 있다.
- robots.txt는 `/images/`, `/_next/static/media/`만 차단한다.
- 약관은 콘텐츠 데이터의 복제·수정·게시·전송·배포를 제한한다. 활성화하더라도 원문/이미지를 저장하지 않고 최소 메타데이터와 링크만 다루며, 블로그에 원문을 재게시하지 않아야 한다.

#### 7. Pokémon UNITE

- 목록: <https://www.pokemonunite.jp/ja/topics/>
- robots.txt: <https://www.pokemonunite.jp/robots.txt>
- 목록과 상세 본문은 서버 렌더 HTML이다.
- HTML에 RSS 링크가 표시되지만, 표시된 `/ja/./topics/feed/`와 정규화한 `/ja/topics/feed/`는 조사 시점에 모두 404였다. RSS Collector로 구현하면 안 된다.
- robots.txt는 `/wp-content/uploads/`, `/?attachment_id=`만 차단한다. 이미지는 수집하지 않는다.

### 수집 정책 초안

실제 Collector에는 다음 제한을 둔다.

- 기본 수집 주기: 소스별 1일 1회
- 요청 간격: 최소 2초, 동시 요청 없음
- HTTP timeout: 20초, 최대 2회 재시도
- 403/429 응답 시 즉시 중단하고 해당 소스를 잠정 비활성화
- `ETag`/`Last-Modified`가 제공되면 조건부 요청 사용
- 상세 페이지는 신규 URL이거나 목록 메타데이터가 변경된 경우에만 요청
- 자동 수집 금지 소스는 기본 `enabled=false`
- User-Agent에 프로젝트명과 연락처를 넣도록 향후 설정 필드 제공

### Phase 1에서 발견한 문제

1. robots.txt 허용과 약관 허용은 같지 않다. Pokémon Center Online이 대표적인 예다.
2. Pokémon GO는 수집이 쉽지만 약관상 자동 Collector를 만들어서는 안 된다.
3. `pokemon.co.jp` JSON endpoint는 공개 개발자 API가 아니므로 변경 가능성이 있다.
4. 게시일은 이벤트 시작일이 아니다. 일본어·한국어 본문의 날짜 범위 추출과 모호성 처리가 필요하다.
5. 한 공지에 여러 세부 행사·기간·장소가 포함될 수 있다. 초기에는 공지 1건을 Event 1건으로 저장하고, 필요가 확인될 때만 세부 이벤트 분할을 추가한다.

### 재현 방법

Phase 1은 코드를 만드는 단계가 아니다. 브라우저 또는 HTTP client로 아래 URL을 확인하면 핵심 결과를 재현할 수 있다.

```text
https://www.pokemon.co.jp/api/info/index/?limit=3&page=1&flg[]=11
https://www.pokemon.co.jp/robots.txt
https://www.pokemoncenter-online.com/terms.html
https://explore.scopely.com/terms
https://www.pokemonunite.jp/ja/topics/
```

## Phase 2 — 프로젝트 기반

### 구현 내용

```text
src/pokemon_events/
├── collectors/
│   └── base.py
├── models/
│   └── event.py
└── storage/
    └── repository.py
tests/
└── test_repository.py
```

- Python 3.11 표준 라이브러리만 사용한다.
- `PokemonEvent`, `Category`, `EventStatus`를 dataclass/enum으로 구현했다.
- 필수 문자열, ISO 국가 코드, timezone-aware datetime, 시작·종료일 순서를 검증한다.
- 새 소스가 구현할 동기식 `BaseCollector.collect()` 계약을 추가했다.
- `SQLiteRepository`가 DB 초기화, 소스 저장, 이벤트 추가·조회를 담당한다.
- `events`, `event_history`, `collection_runs`, `sources` 테이블을 생성한다. `event_history`의 기록 로직은 Phase 4에서 추가한다.
- 이벤트 중복 ID는 조용히 덮어쓰지 않고 SQLite 기본 제약으로 실패한다. Phase 4의 변경 감지기가 update 여부를 결정하게 한다.

### 실행 방법

PowerShell:

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

예상 결과:

```text
Ran 1 test
OK
```

### 발견된 문제

- 현재는 신규 이벤트 `INSERT`만 지원한다. 업데이트와 이력 기록은 Change Detection과 함께 하나의 transaction으로 구현해야 한다.
- 외부 HTTP client, ORM, migration framework는 아직 필요하지 않아 추가하지 않았다.
- PostgreSQL용 Repository interface는 실제 두 번째 구현체가 필요해질 때 추출한다.

## Phase 3 — Pokémon Japan Collector

### 구현 내용

- 소스 URL과 요청 제한을 [`config/sources.toml`](config/sources.toml)에서 관리한다.
- [`PokemonJapanCollector`](src/pokemon_events/collectors/pokemon_japan.py)가 `flg[]=11` 이벤트 목록을 페이지별로 수집한다.
- Python 표준 라이브러리 `urllib`, `json`, `tomllib`, `hashlib`만 사용했다.
- timeout, 요청 간격, 최대 2회 재시도를 적용했다. HTTP 403/429는 재시도하지 않고 즉시 중단한다.
- 외부 JSON의 필수 필드와 형식을 검증하고 예상하지 못한 스키마면 실패한다.
- 공지 ID를 `pokemon_japan:{id}`로 정규화하고, 목록에서 확인된 내용으로 SHA-256 `content_hash`를 만든다.
- API의 `start_date` 필드는 행사일이 아니라 게시일이므로 JST `published_at`으로만 저장한다.
- 행사 기간·장소·상태는 목록에 없으므로 추측하지 않고 `None`/`UNKNOWN`으로 둔다.

### 실제 수집 검증

2026-09-18에 공식 endpoint의 첫 페이지 20건을 실제로 수집·정규화했다.

```text
pokemon_japan:11784 | 2026-09-11 | 「ポケモンワールドチャンピオンシップス2026」の優勝者を発表！
pokemon_japan:11785 | 2026-09-11 | 「#カビゴンと眠活 presented by AEON」が開催中！
pokemon_japan:11786 | 2026-09-11 | 睡眠応援大使のピカチュウとカビゴンが日本の「ねむる」を応援！
```

PowerShell에서 1페이지만 재현:

```powershell
$env:PYTHONPATH = "src"
$env:PYTHONIOENCODING = "utf-8"
python -c "from pokemon_events.collectors import PokemonJapanCollector; events = PokemonJapanCollector(max_pages=1).collect(); print(len(events)); [print(e.id, e.title) for e in events[:3]]"
```

`max_pages`를 지정하지 않으면 API의 `nextPage`가 끝날 때까지 전체 이벤트 목록을 수집한다.

### 검증

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

repository 왕복 저장과 Collector JSON 정규화를 검증하는 2개 테스트가 통과한다.

### 발견된 문제

- API 결과에는 `pokemon.co.jp` 밖의 공식·공공기관 상세 URL도 포함된다. URL을 임의로 변경하지 않고 출처 값으로 보존한다.
- Windows에 시스템 IANA timezone DB가 없을 수 있어, DST가 없는 JST는 표준 라이브러리의 UTC+09:00 고정 offset을 사용한다.
- 일본어 콘솔 출력은 Windows CP949에서 실패할 수 있으므로 `PYTHONIOENCODING=utf-8`을 사용한다.
- 상세 HTML parser는 아직 없다. 행사 기간·장소·포켓몬 추출은 실제 본문 패턴을 더 확인한 뒤 추가한다.

## Phase 4 — 중복 제거와 Change Detection

### 구현 내용

- [`detect_change`](src/pokemon_events/services/change_detector.py)가 기존·신규 Event를 비교해 `NEW`, `UPDATED`, `UNCHANGED`, `ENDED`를 반환한다.
- 동일 ID의 `content_hash`와 `status`가 같으면 `UNCHANGED`다.
- 기존 상태가 `ENDED`가 아닌데 신규 상태가 `ENDED`면 별도 `ENDED` 변경으로 기록한다.
- [`deduplicate_events`](src/pokemon_events/services/deduplicate.py)가 한 배치 안의 동일 ID·동일 내용을 하나로 합친다. 동일 ID에 서로 다른 hash/status가 들어오면 임의로 하나를 고르지 않고 실패한다.
- `SQLiteRepository.save_event()`가 변경 판정, `events` 갱신, `event_history` 추가를 하나의 transaction에서 수행한다.
- `NEW`, `UPDATED`, `ENDED`는 전체 Event snapshot을 이력에 남긴다. `UNCHANGED`는 `collected_at`, `last_seen_at`만 갱신하고 이력을 남기지 않는다.
- `first_seen_at`은 최초 수집 시각을 계속 보존한다.

### 실제 데이터 통합 검증

2026-09-18에 Pokémon Japan 공식 데이터 1페이지를 수집하여 중복 제거 후 메모리 SQLite에 두 번 저장했다.

```text
events=20
first={'NEW': 20}
second={'UNCHANGED': 20}
history=20
```

같은 데이터를 다시 수집해도 `events`나 `event_history`가 중복 증가하지 않는다.

### 검증

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

3개 테스트가 다음을 검증한다.

- SQLite 스키마와 Event 왕복 저장
- Pokémon Japan JSON 정규화
- 배치 중복 제거, `NEW → UNCHANGED → UPDATED → ENDED`, 이력과 관측 시각

### 발견된 문제

- 목록에서 사라진 것만으로 이벤트 종료를 판정하지 않는다. 뉴스 페이지네이션 변경·일시 장애·삭제를 종료로 오판할 수 있다.
- 현재 `ENDED`는 Collector가 명시적으로 종료 상태를 제공할 때만 발생한다. 일정 추출이 추가되면 종료일을 기준으로 status를 산출한다.
- hash에 포함되는 필드는 Collector가 결정한다. Phase 5의 추가 Collector도 사용자에게 의미 있는 콘텐츠 필드만 hash해야 한다.

## Phase 5 — 추가 공식 Collector

### 구현 내용

- [`PokemonKoreaCollector`](src/pokemon_events/collectors/pokemon_korea.py)가 `POST /ajax/news`의 실제 `#|#` 구분 형식에서 HTML과 총 페이지 수를 읽는다.
- Pokémon Korea 목록의 제목, 카테고리, 게시일, 상세 URL만 정규화한다. SQL debug prefix와 이미지는 무시한다.
- 내부 공지 URL의 게시물 ID를 사용하고, 외부 공식 특설 URL은 canonical URL hash로 안정적인 ID를 만든다.
- [`PokemonUniteCollector`](src/pokemon_events/collectors/pokemon_unite.py)가 UNITE 공식 Topics의 서버 렌더 HTML에서 URL, 게시일, 제목을 읽는다.
- 두 Collector는 상세 본문·이미지·JavaScript를 요청하지 않는다.
- 세 Collector의 재시도·403/429 중단 로직을 [`fetch_bytes`](src/pokemon_events/collectors/http.py)로 공유한다.
- SHA-256 생성은 [`hash_content`](src/pokemon_events/services/content_hash.py)로 통합했다.
- 활성·비활성 소스와 사유를 [`config/sources.toml`](config/sources.toml)에 기록했다.

### 실제 수집 검증

2026-09-18 기준 공식 사이트에서 수집한 결과:

```text
pokemon_korea    count=20  first=pokemon_korea:190c8d18088603e1
pokemon_unite_jp count=15  first=pokemon_unite_jp:notice:20260616-1
SQLite events=35, changes={'NEW'}
```

Pokémon Korea는 검증 시 `max_pages=1`로 제한했다. 제한을 제거하면 응답이 알려 준 총 페이지 수까지 2초 간격으로 순차 수집한다.

### 검증

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

5개 테스트가 통과한다. Korea AJAX HTML, UNITE Topics HTML, Japan JSON, SQLite 저장, Change Detection을 포함한다.

### 제외한 소스

| source | 상태 | 사유 |
|---|---|---|
| Pokémon GO | `enabled=false` | 약관이 scraping/indexing과 crawler 접근을 금지 |
| Pokémon Center Online Japan | `enabled=false` | 약관이 자동 수집·crawling·scraping을 금지 |
| Pokémon Asia Topics | `enabled=false` | 약관이 콘텐츠 데이터의 복제·게시·전송·배포를 제한 |
| 야돈 파라다이스 in 가가와 | `enabled=false` | 안정적인 뉴스 목록/Feed가 없고 robots.txt도 제공되지 않음 |

Playwright로 정책 제약을 우회하거나 보류 소스를 임의로 활성화하지 않았다.

### 발견된 문제

- Pokémon Korea는 robots.txt 경로에서 robots 문서 대신 HTML을 반환한다. 따라서 1일 1회, 2초 간격의 보수적 수집 정책을 유지한다.
- Korea AJAX 응답에 내부 SQL 문자열이 포함되지만 출력·저장하지 않고 HTML 구간만 파싱한다.
- UNITE 목록은 고정 공지가 날짜순을 벗어날 수 있다. Collector는 표시 순서를 신규순으로 가정하지 않는다.
- 두 소스도 목록 게시일만 알 수 있어, 행사 시작·종료일과 장소는 아직 비어 있다.

## Phase 6 — CLI와 블로그 소재 조회

### 구현 내용

- 루트 [`main.py`](main.py)에서 별도 패키지 설치 없이 CLI를 실행할 수 있다.
- `collect`가 활성 Collector를 실행하고, 배치 중복을 제거한 뒤 SQLite에 저장한다.
- 소스별 시작·완료 시각, `SUCCESS`/`FAILED`, 수집 건수, 오류를 `collection_runs`에 기록한다.
- 한 소스가 실패해도 다른 소스를 계속 수집하고 CLI는 non-zero exit code를 반환한다.
- `events`가 현재 진행, 최근 발견, 종료 임박, 주간 시작·종료, 포켓몬, 국가, 카테고리 필터를 제공한다.
- 출력에 `[NEW]`, `[ENDING SOON]`, 기간, 지역, 공식 소스와 URL을 포함한다.
- Windows CP949 콘솔에서 일본어·`Pokémon`이 깨지지 않도록 `main.py`가 stdout/stderr를 UTF-8로 설정한다.

### 실행 방법

전체 활성 소스 수집:

```powershell
python main.py collect
```

특정 소스만 수집:

```powershell
python main.py collect --source pokemon_korea
python main.py collect --source pokemon_japan
python main.py collect --source pokemon_unite_jp
```

기본 DB는 `data/pokemon_events.db`이다. 다른 경로를 쓰려면 subcommand 앞에 `--db`를 둔다.

```powershell
python main.py --db data/test.db collect --source pokemon_unite_jp
```

블로그 소재 조회:

```powershell
python main.py events
python main.py events --active
python main.py events --new
python main.py events --ending-soon --days 4
python main.py events --starts-this-week
python main.py events --ends-this-week
python main.py events --pokemon 야돈
python main.py events --country KR
python main.py events --country JP --category GAME
python main.py events --category TCG --limit 100
```

최근 Pokémon Japan 글 한 건의 목록 정규화, 상세 보강, 변경 판정, 블로그 출력을 DB 저장 없이 확인한다.

```powershell
python main.py preview
```

`--new`는 기본으로 최근 7일 안에 처음 발견된 이벤트를 뜻한다. `--days`로 기간을 바꿀 수 있다. 조건은 여러 개를 조합할 수 있다.

### 실제 CLI 검증

2026-09-18에 Pokémon UNITE Collector를 CLI로 두 번 실행했다.

```text
1차: pokemon_unite_jp: collected=15 NEW=15
2차: pokemon_unite_jp: collected=15 UNCHANGED=15

events=15
event_history=15
collection_runs=2 (SUCCESS 2건)
```

`python main.py events --new --country JP --limit 3`으로 신규 블로그 후보의 제목·게시일·지역·출처·URL 출력을 확인했다.

### 검증

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

6개 테스트가 모델·Collector·저장·변경 감지·CLI 출력을 검증한다.

### 알려진 제약

- 현재 활성 Collector는 목록 메타데이터만 수집하므로 대부분의 `start_date`, `end_date`, `pokemon`, `venue`, `status`가 비어 있다. 따라서 해당 필터는 상세 parser가 추가되기 전까지 결과가 적거나 없을 수 있다.
- 최근 신규 기준은 수집 시각이다. 과거 글을 첫 DB 적재할 때는 모두 `NEW`로 보이므로, 최초 적재 후에는 게시일 또는 국가 필터를 함께 사용하는 것이 좋다.
- 조회는 개인용 SQLite 규모에 맞게 메모리에서 필터링한다. 수만 건 이상이 되면 SQL 조건과 index로 옮긴다.

## MVP 완료 범위

Phase 1~6이 완료되어 다음 흐름을 로컬에서 실행할 수 있다.

```text
공식 소스 수집 → 공통 Event 정규화 → 중복/변경 감지
→ SQLite 현재값+이력 저장 → CLI 필터 → 블로그 소재 출력
```

세부 기간·장소·포켓몬 추출이 실제로 필요해질 때 각 사이트의 상세 HTML parser를 하나씩 추가한다.

## Phase 7 — Pokémon Japan 상세 페이지 보강

### 구현 내용

- 신규 Pokémon Japan 글 중 게시 후 30일 이내인 공식 `/info/` 상세 페이지만 추가 요청한다.
- 상세 표의 `開催期間`·`実施期間` 계열 행에서 단일 연속 기간을, `開催場所`·`実施場所` 계열 행에서 단일 장소를 추출한다.
- 시작·종료일을 JST로 저장하고 현재 날짜에 따라 `UPCOMING`·`ACTIVE`·`ENDED`를 계산한다.
- 저장된 상세 필드는 다음 목록 수집 때 유지하고, 날짜가 지나면 상태 변경을 이력에 남긴다.
- 상세 요청이 실패해도 목록 수집과 저장은 계속한다.

### 실행 방법

기존 명령을 그대로 사용한다.

```powershell
python main.py collect --source pokemon_japan
python main.py events --active --country JP
python main.py events --ending-soon --country JP
```

상세 조회 기간은 [`config/sources.toml`](config/sources.toml)의 `detail_lookback_days`로 조정한다.

### 실제 페이지 구조 확인

- `2026/05/260529_e01.html`: `開催期間` 한 행에 `2026年8月28日～30日`, `開催場所` 한 곳이 있어 자동 추출 가능했다.
- `2026/06/260626_e01.html`: 한 기사에 여러 행사 기간과 장소가 있어 단일 Event로 합치면 오정보가 된다.
- `2026/07/260731_e01.html`: 두 개의 개별 실시일이 있어 연속 기간으로 해석하지 않았다.
- Pokémon Korea 내부 상세 글은 본문이 이미지 중심인 사례가 있어 이번 단계에서 제외했다.

### 검증

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

단일 기간·장소 추출, script 내부 중복 마크업 무시, 복수 기간·장소 보류를 테스트한다.

2026-09-18 실수집 결과는 다음과 같다.

```text
pokemon_japan: collected=332 NEW=332
상세 필드 반영=2
테스트=7 passed
```

반영된 두 글에서 `2026-08-28 ~ 2026-08-30`, `2026-08-28 ~ 2026-09-01` 기간과 `ENDED` 상태를 확인했다.

### 알려진 제약

- 목록에 처음 나타난 최근 글만 상세 조회한다. 상세 본문 자체의 후속 수정 감지는 별도 source fingerprint를 저장할 때 추가한다.
- 한 기사에 여러 독립 행사가 있으면 잘못 합치지 않기 위해 기간·장소를 비워 둔다. 향후 parent-child Event 모델이 필요하다.
- 일본어 날짜의 단일 연속 범위만 처리하며 운영 시간, 추첨 신청 기간, 여러 회차는 자동 기간으로 저장하지 않는다.

## Phase 8 — 개최국과 소스 국가 분리

### 구현 내용

- `country`는 실제 개최국, `source_country`는 공식 사이트의 시장 코드로 분리했다.
- 기존 SQLite에는 `source_country` 열을 자동 추가하고 기존 `country` 값을 복사한다.
- 검증된 상세 장소 문자열 `アメリカ`는 개최국 `US`로 정규화한다.
- `events --country`는 개최국을, `events --source-country`는 공식 소스 국가를 조회한다.

### 실행 및 실제 검증

```powershell
python main.py events --country US --source-country JP
```

2026-09-18 재수집에서 332건 중 328건은 `UNCHANGED`, 국가·상세 정보가 달라진 4건은 `UPDATED`로 기록됐다. WCS 글은 `country=US`, `source_country=JP`로 확인했고 마이그레이션 후 `source_country IS NULL`은 0건이다.

### 알려진 제약

- 개최국 자동 판정은 실제로 확인한 미국 표기만 지원한다. 다른 해외 개최 사례가 수집되면 검증된 표기만 매핑에 추가한다.
- 상세 장소가 없으면 개최국은 소스 국가를 기본값으로 사용한다.

## Phase 9 — 상세 페이지 변경 감지

### 구현 내용

- `source_hash`로 목록의 제목·설명·분류·URL·게시일 변경을 추적한다.
- `detail_hash`로 상세 표의 기간·장소 관련 행 변경을 추적한다.
- `detail_checked_at`으로 마지막 상세 확인 시각을 저장한다.
- 최근 30일 글과 `UPCOMING`·`ACTIVE` 이벤트는 기본 24시간 간격으로 상세를 다시 확인한다.
- 목록 해시가 바뀌면 재조회 간격과 관계없이 상세를 즉시 확인한다.
- 상세 요청 실패 시 기존 상세값을 보존하고 다음 수집에서 다시 시도한다.
- 기존 SQLite에는 세 필드를 자동 추가하며 현재 이벤트를 잃지 않는다.

재조회 정책은 [`config/sources.toml`](config/sources.toml)에서 조정한다.

```toml
detail_lookback_days = 30
detail_refresh_hours = 24
```

`preview`는 목록과 상세 해시 및 상세 확인 시각도 출력한다.

```powershell
python main.py preview
```

### 실제 검증

2026-09-18 기준 최근 공식 상세 4건에 `detail_hash`와 `detail_checked_at`이 저장됐다. 수정 후 동일 목록을 다시 수집한 결과는 다음과 같다.

```text
pokemon_japan: collected=332 UNCHANGED=332
source_hash 저장=347건
detail_hash 저장=4건
plain_hash_mismatch=0건
테스트=9 passed
```

### 알려진 제약

- 상세 해시는 원문 전체가 아니라 기간·장소 표의 정규화된 행을 대상으로 한다. 원문 문장만 바뀐 경우에는 `UPDATED`로 보지 않는다.
- 상세 갱신은 전체 332건이 아니라 최근 또는 진행 중인 공식 `/info/` 글만 수행한다.

## Phase 10 — Pokémon Korea 상세 보강

### 구현 내용

- `pokemonkorea.co.kr/news/{category}/{id}` 형식의 공식 내부 상세 글만 추가 요청한다.
- 실제 `bx-board` 본문에서 공유 버튼 영역을 제외하고 텍스트와 이미지 URL을 정규화한다.
- 텍스트형 공지는 블로그 후보 확인용 설명을 최대 300자로 저장한다.
- `개최 기간`·`행사 기간`·`이벤트 기간`·`운영 기간`이 한 번만 명시된 경우에만 기간을 추출한다.
- `개최 장소`·`행사 장소`·`이벤트 장소`가 한 곳만 명시된 경우에만 장소를 추출한다.
- 이미지형 공지는 내용을 추측하지 않고 이미지 URL을 포함한 `detail_hash`만 저장해 교체 여부를 감지한다.
- 같은 외부 URL을 공유하는 서로 다른 공지는 `URL+제목+게시일` 기반 ID로 구분한다.
- Phase 9와 동일하게 최근 30일 및 진행 중 이벤트만 24시간 간격으로 다시 확인한다.

### 실행 방법

```powershell
python main.py collect --source pokemon_korea
python main.py events --source-country KR --new
```

### 실제 검증

공식 AJAX가 알려 준 30페이지를 2초 간격으로 수집했다.

```text
1차: pokemon_korea: collected=598 NEW=598
2차: pokemon_korea: collected=598 UNCHANGED=598
상세 확인=3건
텍스트 설명 보강=2건
이미지형 상세 해시=1건
테스트=11 passed
```

### 발견된 문제와 제약

- 첫 실수집에서 서로 다른 공지가 같은 외부 URL을 사용해 ID가 충돌했다. 외부 링크 ID에 제목과 게시일을 포함해 해결했다.
- 로컬에 Tesseract OCR이 없어 이미지 안의 날짜·장소는 추출하지 않았다. OCR은 이미지형 공지의 중요도가 확인되고 한국어 OCR 실행 환경이 준비될 때 선택적으로 추가한다.
- 날짜는 명시적인 행사 기간 라벨과 완전한 일자 범위가 모두 있을 때만 저장한다. 신청·제재·약관 적용 기간을 이벤트 기간으로 오인하지 않는다.
- 외부 마이크로사이트는 사이트별 구조와 정책 확인이 필요하므로 이번 단계에서 상세 파싱하지 않는다.

## Phase 11 — 변경 이력 블로그 후보 조회

### 구현 내용

- 최근 실제 내용이 변경된 이벤트를 `events --updated`로 조회한다.
- 최근 수집에서 `ENDED`로 전환된 이벤트를 `events --ended`로 조회한다.
- 출력 제목에 `[UPDATED]`와 `[ENDED]`를 표시하며 같은 기간에 처음 발견된 이벤트는 `[NEW]`도 함께 표시한다.
- `event_history.snapshot`의 제목, 설명, 분류, 포켓몬, 개최국, 지역, 장소, 기간, URL, 게시일, 상태만 비교한다.
- `content_hash`·`source_hash`·`detail_hash`처럼 내부 관리 필드만 바뀐 스키마 마이그레이션은 블로그 변경 후보에서 제외한다.

### 실행 방법

```powershell
python main.py events --updated
python main.py events --updated --days 30 --country KR
python main.py events --ended --days 7
```

`--ended`는 현재 상태가 종료인 모든 이벤트가 아니라 지정 기간 안에 종료 상태로 **전환된 이벤트**를 뜻한다.

### 실제 검증

```text
--updated: WCS2026 글 1건 ([NEW][UPDATED])
--ended: 조건에 맞는 이벤트 없음
테스트=13 passed
```

WCS2026 글은 장소 기반 개최국이 `JP`에서 `US`로 교정된 실제 필드 변경이므로 후보에 포함됐다. Phase 9 해시 마이그레이션으로 생성된 비즈니스 필드 무변경 이력은 제외됐다.

### 알려진 제약

- 개인용 SQLite 규모에 맞춰 이력 snapshot을 메모리에서 비교한다. 이력이 수만 건 이상으로 커지면 material change 여부를 저장하거나 SQL index를 추가한다.

## Phase 12 — 포켓몬 다국어 태깅

### 구현 내용

- 제목과 상세 설명에서 한국어·영어·일본어 별칭을 찾아 공통 `pokemon` 목록에 저장한다.
- 수집 시 자동 태깅하며, 기존 DB는 네트워크 요청 없이 `tag` 명령으로 다시 처리한다.
- 태그 변화는 이력 snapshot에는 남지만 공식 원문 변경을 뜻하는 `[UPDATED]` 후보에서는 제외한다.
- 별칭은 [`config/pokemon_aliases.toml`](config/pokemon_aliases.toml)에서 직접 추가·수정할 수 있다.
- 초기 설정에는 야돈, 피카츄, 이브이, 메타몽, 잠만보, 리자몽, 뮤츠, 꼬부기, 파이리, 이상해씨, 코라이돈, 미라이돈, 레쿠쟈를 포함한다.

### 실행 방법

기존 이벤트를 재태깅한 뒤 원하는 포켓몬을 조회한다.

```powershell
python main.py tag
python main.py events --pokemon 야돈
python main.py events --pokemon 피카츄 --country KR
```

별칭을 추가한 뒤 `python main.py tag`를 다시 실행하면 된다.

```toml
[pokemon]
"야돈" = ["야돈", "Slowpoke", "ヤドン"]
```

### 실제 검증

```text
1차: scanned=945 tagged=63
2차: scanned=945 tagged=0
야돈 관련=2건 (한국 1건, 일본 1건)
포켓몬 태그 보유 이벤트=63건
테스트=14 passed
```

### 알려진 제약

- 초기 별칭은 블로그 우선 관심 포켓몬만 포함한다. 전체 전국도감이 필요해질 때 공식 도감 데이터에서 설정 파일을 생성한다.
- 단순 문자열 일치 방식이므로 문맥상 포켓몬을 가리키지 않는 동음이의어가 생기면 해당 별칭을 더 구체적으로 조정한다.
- 이미지 안에만 등장하는 포켓몬은 OCR 또는 이미지 분석을 추가하기 전까지 태깅되지 않는다.

## Phase 13 — 사실 기반 블로그 초안 생성

### 구현 내용

- `draft --id`가 저장된 Event 한 건을 네이버 블로그용 Markdown 초안으로 출력한다.
- 제목, 공식 게시일, 상태, 기간, 장소, 관련 포켓몬, 설명, 공식 URL과 해시태그를 사용한다.
- 기간·장소가 없으면 임의로 추정하지 않고 추가 확인이 필요한 정보로 표시한다.
- 300자로 잘린 설명은 마지막 완성 문장까지만 사용해 문장이 중간에서 끊기지 않게 한다.
- `events` 출력에 복사 가능한 Event ID를 추가했다.
- 외부 LLM이나 API를 사용하지 않아 같은 데이터에서는 같은 초안이 생성된다.

### 실행 방법

먼저 후보의 ID를 확인한 뒤 초안을 생성한다.

```powershell
python main.py events --new --limit 5
python main.py draft --id pokemon_korea:21094
```

Markdown 파일로 저장하려면 PowerShell 리다이렉션을 사용한다.

```powershell
python main.py draft --id pokemon_korea:21094 > wcs2027.md
```

### 실제 검증

`pokemon_korea:21094`로 WCS2027 Pokémon GO 안내 초안을 생성했다. 3대3 팀전과 팀 구성 정보는 저장된 공식 설명에서 반영했고, 확정되지 않은 기간과 상세 장소는 누락 정보로 표시했다.

```text
테스트=15 passed
```

### 알려진 제약

- 현재 초안은 사실 정리 템플릿이며 문체 변형, SEO 제목 후보, 도입부 확장은 하지 않는다.
- 수집된 설명이 없거나 이미지형 공지이면 핵심 정보와 출처 중심의 짧은 초안만 생성된다.
- LLM 초안 보강은 원문 사실과 생성 문장을 분리해 검증할 수 있는 단계에서 선택적으로 추가한다.

## Phase 14 — 운영용 블로그 후보 digest

### 구현 내용

- `digest`가 최근 게시된 `NEW`·`UPDATED` 이벤트와 종료 임박 이벤트를 한 번에 보여준다.
- 최초 DB 적재 때 발견된 오래된 과거 글은 게시일이 조회 기간 밖이면 후보에서 제외한다.
- 과거 글이라도 현재 `UPCOMING`·`ACTIVE`이고 최근 실제 변경이 있으면 후보에 포함한다.
- 포켓몬 태그 백필처럼 파생 메타데이터만 바뀐 이력은 `[UPDATED]`로 표시하지 않는다.
- 각 후보에 Event ID를 출력해 바로 `draft --id`로 연결할 수 있다.

### 실행 방법

```powershell
python main.py digest
python main.py digest --days 14 --ending-days 5 --limit 30
python main.py digest --source-country KR
```

후보를 확인한 뒤 원하는 글의 초안을 생성한다.

```powershell
python main.py draft --id pokemon_korea:21033
```

### 실제 검증

2026-09-18 기준 `--days 7` 실행에서 945건 전체 중 최근 게시·변경 조건을 만족한 5건만 출력됐다. 2021년 야돈 상품처럼 최초 적재 때문에 `NEW`가 된 오래된 글은 제외됐다.

```text
최근 후보=5건
테스트=16 passed
```

### 알려진 제약

- 후보 우선순위는 `UPDATED` → `NEW` → 게시일 순의 단순 규칙이다. 클릭률이나 개인 선호 데이터를 축적하기 전에는 별도 점수 모델을 두지 않는다.
- `ENDING SOON`은 상세 parser가 종료일을 확보한 이벤트에만 적용된다.

## Phase 15 — 일일 운영 스크립트

### 구현 내용

- [`scripts/daily.ps1`](scripts/daily.ps1)이 전체 수집 후 digest를 날짜별 Markdown 파일로 저장한다.
- 수집 또는 digest가 실패하면 non-zero 종료로 처리해 작업 스케줄러가 실패를 감지할 수 있다.
- 보고서는 `reports/digest-YYYYMMDD-HHMMSS.md`에 저장하며 Git에서는 제외한다.
- `-SkipCollect`로 네트워크 요청 없이 현재 DB의 보고서 생성만 검증할 수 있다.
- Python 실행 경로가 PATH에 없으면 `-Python`으로 지정할 수 있다.

### 실행 방법

프로젝트 루트에서 일일 전체 실행:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/daily.ps1
```

수집 없이 보고서만 생성:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/daily.ps1 -SkipCollect
```

조회 범위와 후보 수 조정:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/daily.ps1 `
  -Days 14 -EndingDays 5 -Limit 30
```

Windows 작업 스케줄러 등록 예시다. 아래 명령은 자동 실행하지 않았으며, 원하는 실행 시각으로 `08:00`을 변경한 뒤 직접 실행한다.

```powershell
schtasks /Create /TN "Pokemon Event Pipeline" /SC DAILY /ST 08:00 `
  /TR "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"C:\Users\seo\Documents\ChatGPT\블로그\scripts\daily.ps1`"" /F
```

### 검증

`-SkipCollect -Limit 5`로 실제 Markdown 보고서를 생성하고 UTF-8 한글·일본어와 후보 ID가 보존되는지 확인한다.

### 알려진 제약

- 스크립트는 사용자 로그인 환경의 `python` 명령을 사용한다. 작업 스케줄러에서 PATH가 다르면 가상환경 또는 Python 실행 파일의 절대 경로를 `-Python`에 지정한다.
- 시스템 작업 스케줄러 등록은 사용자 PC 상태를 변경하므로 프로젝트에서 자동 수행하지 않는다.

## RSS 수집 확장 — 2026-10-05

RSS 2.0 / Atom 메타데이터 수집을 기존 SQLite·변경 감지·CLI에 연결했다.
추가 패키지 없이 Python 3.11 표준 라이브러리를 사용한다.
사용법과 정책·구현 한계는 [수집 안내](docs/pokemon-goods/COLLECTION.md)를 참고한다.

```powershell
python main.py --db data/goods.db collect --config config/my_rss.toml --source goods_rss
python main.py --db data/goods.db events --category GOODS
```

`config/rss_sources.example.toml`은 비활성 예제이며 실제 공식 피드가 아니다.
새 피드는 정책 검토 후 실제 URL을 등록하고 `enabled=true`, `policy_approved=true`로 설정한다.
수집 과정에서 원문 본문·이미지를 내려받지 않는다.
기존 HTML/API 수집기를 자동으로 RSS로 대체하거나 실패 시 fallback하지 않는다.
이제 전체 수집에서도 설정의 비활성 소스를 건너뛴다.

## 굿즈·콜라보 글감 선별 — 2026-10-05

`digest`는 기본적으로 굿즈·콜라보 후보를 우선 선별한다.
선정 이유, 편집 점수, 실제 변경 항목과 추가 확인 과제를 표시한다.
같은 국가의 동일 링크를 묶되 서로 다른 상품이나 국가 정보는 합치지 않는다.
이전의 전체 주제 조회는 `--focus all`로 사용할 수 있다.

```powershell
python main.py digest --days 7 --limit 10
python main.py digest --source-country KR --limit 10
python main.py digest --focus all --limit 10
```

상세 규칙과 제한은 [글감 선별 안내](docs/pokemon-goods/CURATION.md)를 참고한다.
이미지 확보는 아직 별도 개발 단계다.

## 평서형 초안 출력 — 2026-10-05

```powershell
python main.py draft --id EVENT_ID
python main.py draft --id EVENT_ID --output reports/draft.md
python main.py draft --id EVENT_ID --notes config/draft_kakao.example.toml --output reports/kakao-draft.md
```

마지막 메모는 해당 카카오 상품 URL의 항목에만 적용된다. 자세한 입력 형식은
[초안 출력 안내](docs/pokemon-goods/DRAFT.md)를 참고한다.
템플릿 기반 평서형 문체·정보 표·출처를 지원하고, 기존 파일을 덮어쓰지 않는다.
가격·설명은 원문을 검토한 편집 메모로 보강하며 자동 생성·자동 번역하지 않는다.
