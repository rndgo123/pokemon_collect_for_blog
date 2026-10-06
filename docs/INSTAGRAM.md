# 인스타그램 카드뉴스

사용자 지정 기본 폰트는 **카페24 모야모야 v1.0 Regular**다. 인스타그램
표지와 카드뉴스의 제목·설명에 적용한다. 시스템 설치 대신 로컬 웹폰트를
불러오며, 임의로 다른 폰트로 바꾸지 않는다.

`templates/instagram-photo.html`의 `{{...}}` 값을 HTML에 안전하게 넣어
사용한다. 기본 크기는 1080×1350px이며 원본 사진 위에 하단 음영과 글을
배치한다. 글자가 넘치거나 사진의 주요 부분이 가려지는지 렌더링 후 확인한다.

사용자가 제공한 `Cafe24Moyamoya-v1.0.zip`에서 다음 파일을 로컬에 둔다.

- `templates/fonts/Cafe24Moyamoya-Regular-v1.0.woff2`
- `templates/fonts/License-Moyamoya.pdf`

생성 HTML이 다른 폴더에 있으면 `@font-face`의 상대 경로를 조정한다.
이미지 저장 전에 `document.fonts.ready`와 실제 폰트 로딩 성공을 확인한다.
Regular 원본을 사용하고 합성 굵게는 적용하지 않는다.

동봉 안내는 SNS 이미지 사용을 허용한다. 폰트 바이너리와 라이선스 PDF는
로컬에 보관하고 Git에 등록하지 않는다. 폰트를 별도로 재배포할 때는 해당
저작권 안내와 SIL OFL 전문을 포함해야 한다.
