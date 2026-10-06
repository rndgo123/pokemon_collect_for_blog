# 인스타그램 카드뉴스

계정은 **MuliGo (@muli.goo)**이며 신규 굿즈 소개를 다룬다. 포켓몬에
한정하지 않는다. 프로필은 사용자가 선택한 MG 로고다.

사용자 지정 폰트 기준(2026-10-06):

- 첫 페이지 표지·썸네일 제목과 설명: **카페24 모야모야 v1.0 Regular**.
- 2페이지부터 상품 소개·본문: **카페24 PRO Slim Max v2.0**.
- 모든 카드 하단 중앙: 사용자가 선택한 **MG + 별 로고**의 흰색 투명 PNG 워터마크 (`templates/assets/mg-white.png`). 텍스트 MuliGo로 대체하지 않는다.
- 이미지 출처: 워터마크 아래에 작게, PRO Slim Max 폰트.

시스템 설치 대신 로컬 웹폰트를 불러오며, 임의로 다른 폰트로 바꾸지 않는다.
표지는 기본 `class="card"`, 2페이지부터는 `class="card content"`로 지정한다.

`templates/instagram-photo.html`의 `{{...}}` 값을 HTML에 안전하게 넣어
사용한다. 기본 크기는 1080×1350px이며 원본 사진 위에 하단 음영과 글을
배치한다. 글자가 넘치거나 사진의 주요 부분이 가려지는지 렌더링 후 확인한다.

사용자가 제공한 `Cafe24Moyamoya-v1.0.zip`에서 다음 파일을 로컬에 둔다.

- `templates/fonts/Cafe24Moyamoya-Regular-v1.0.woff2`
- `templates/fonts/License-Moyamoya.pdf`

`Cafe24PROSlimMax_v2.0.zip`에서 추가로 다음 파일을 둔다.

- `templates/fonts/Cafe24PROSlimMax.woff2`
- `templates/fonts/License-PRO SLIM Max.pdf`

생성 HTML이 다른 폴더에 있으면 `@font-face`의 상대 경로를 조정한다.
이미지 저장 전에 `document.fonts.ready`와 실제 폰트 로딩 성공을 확인한다.
Regular 원본을 사용하고 합성 굵게는 적용하지 않는다.

동봉 안내는 SNS 이미지 사용을 허용한다. 폰트 바이너리와 라이선스 PDF는
로컬에 보관하고 Git에 등록하지 않는다. 폰트를 별도로 재배포할 때는 해당
저작권 안내와 SIL OFL 전문을 포함해야 한다.
