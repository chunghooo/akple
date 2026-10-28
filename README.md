# EVIDA — 악플 증거 정리 서비스

유튜브 댓글(또는 직접 입력·스크린샷)에서 악플 후보를 찾고, 사용자가 선택한 댓글을 사건 정보와 함께 **증거 정리 보고서(PDF)**로 만드는 Streamlit 웹앱.
경찰 공식 고소장이 아닌 **신고 준비용 참고자료**를 만든다.

## 흐름
유튜브 URL 입력 → 댓글 수집(YouTube Data API v3) → 1차 분류(키워드·우회 표기 규칙 + 학습형 분류 모델) → (선택) 2차 검토(Gemini) → 사용자 선택 → 사건 정보 입력 → PDF 다운로드

## 분류 구조
- 규칙: 욕설·우회 표기(영타·로마자·늘여쓰기·숫자) 복원, 오탐 예외(시발점·금수저 등), 칭찬·자기비하·인용·사물 대상 완화, 욕 없는 비하·위협·성적 대상화는 '의심(심각도 1)'으로만 표시
- 학습형 분류 모델: TF-IDF(문자 n-gram) + 로지스틱 회귀, 공개 데이터셋 약 9.4만 문장으로 서버에서 학습
  - Smilegate AI UnSmile (2022, CC BY-NC-ND 4.0), K-MHaS (COLING 2022, CC BY-SA 4.0)
- 생성형 AI(선택): Google Gemini Flash-Lite 계열, 사용자가 버튼을 눌렀을 때만 호출. 같은 내용은 1번만, 이미 검토한 내용은 캐시
- 최종 판단은 사용자. '[참고]' 분류는 법적 판단이 아님

## 파일
- `app.py` — 앱 전체
- `requirements.txt` — 파이썬 패키지
- `packages.txt` — 서버 프로그램(글자 인식 tesseract, 한글 폰트 fonts-nanum)

## Streamlit Secrets
```
YOUTUBE_API_KEY = "..."
GEMINI_API_KEY = "..."   # 선택
```
