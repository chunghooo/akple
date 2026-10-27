import re, io, json, hashlib, requests
from datetime import datetime, timezone, timedelta
import pandas as pd
import streamlit as st
from docx import Document
from docx.shared import Pt, Cm

KST = timezone(timedelta(hours=9))

# ---------- 키워드 (유형: (심각도, [단어])) ----------
RULES = {
    "욕설": (3, ["시발", "씨발", "ㅅㅂ", "ㅆㅂ", "좆", "ㅈ같", "x같", "개새끼", "개색기", "새끼", "병신", "ㅂㅅ", "븅신",
                 "지랄", "ㅈㄹ", "염병", "썅", "엠창", "느금", "니애미", "애미", "애비", "18놈", "18새", "십팔놈", "씹새", "장애새끼", "장애냐", "고아새끼", "고아냐"]),
    "비속어": (1, ["존나", "졸라", "ㅈㄴ", "개같", "뒤진다", "뒤질"]),
    "비난": (1, ["악마", "꼴보기", "퉤", "ㅉㅉ", "존망", "토할", "와꾸", "뇬", "가증", "무지성", "발작버튼", "누칼협", "알빠노", "긁혔", "뇌절", "벌레같", "관종"]),
    "위협": (3, ["죽어라", "뒤져라", "자살해", "죽여버", "찾아간다", "패버"]),
    "인신공격": (2, ["미친놈", "미친년", "또라이", "돌아이", "멍청", "찐따", "한심", "쓰레기", "못생", "정신병자", "싸이코패스", "사이코패스", "양아치", "인간같지", "인간이냐", "금수", "모자란",
                     "정병", "역겹", "꺼져", "닥쳐", "ㄲㅈ", "ㄷㅊ", "상태봐라", "꼬라지", "주제에", "얼굴값", "꼴값", "능지", "뇌빼고", "쿨찐", "방구석여포", "호소인"]),
    "혐오": (3, ["한남충", "한녀", "김치녀", "틀딱", "급식충", "잼민", "맘충", "짱깨", "쪽바리", "스윗한남", "퐁퐁남", "설거지론", "영포티", "오팔륙", "군캉스"]),
    "성적": (3, ["따먹", "몸매보", "ㅗㅜㅑ", "눈요기", "육덕", "헤응", "스폰녀", "오피녀", "조건만남"]),
}
SEP = r"[\s\d._*~!^♡♥,·ㅇㅋㅎㅡ-]*"  # 끼워넣은 숫자·기호·ㅇㅋㅎ 건너뜀


def pat(w):
    return re.compile(SEP.join(map(re.escape, w)), re.I)


PATS = [(c, s, w, pat(w)) for c, (s, ws) in RULES.items() for w in ws]

# ---------- 우회 표기 복원 ----------
CHO, JUNG = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ", "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
JONG = " ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"
KEY = dict(zip("qwertasdfgzxcvyuiophjklbnmQWERTOP", "ㅂㅈㄷㄱㅅㅁㄴㅇㄹㅎㅋㅌㅊㅍㅛㅕㅑㅐㅔㅗㅓㅏㅣㅠㅜㅡㅃㅉㄸㄲㅆㅒㅖ"))
VC = {"ㅗㅏ": "ㅘ", "ㅗㅐ": "ㅙ", "ㅗㅣ": "ㅚ", "ㅜㅓ": "ㅝ", "ㅜㅔ": "ㅞ", "ㅜㅣ": "ㅟ", "ㅡㅣ": "ㅢ"}
ROMAN = {"ssi": "씨", "shi": "시", "si": "시", "c": "시", "bal": "발", "ppal": "빨", "byung": "병", "byeong": "병",
         "shin": "신", "sin": "신", "gae": "개", "sae": "새", "kki": "끼", "ji": "지", "ral": "랄", "jot": "좆"}
TENSE = dict(zip("ㄲㄸㅃㅆㅉㅋㅌㅊ", "ㄱㄷㅂㅅㅈㄱㄷㅈ"))  # 된소리·거센소리 → 예사소리
VOW = dict(zip("ㅢㅟㅐㅙㅞㅚㅑㅘㅕㅝㅛㅠ", "ㅣㅣㅔㅔㅔㅔㅏㅏㅓㅓㅗㅜ"))


def syl(c, v, j=" "):
    return chr(0xAC00 + (CHO.index(c) * 21 + JUNG.index(v)) * 28 + JONG.index(j))


def eng2kor(w):
    """영타 → 한글. 받침 하나만 처리(욕설 복원엔 충분). 낱자가 남으면 실패(None)"""
    j = [KEY.get(ch) or KEY.get(ch.lower()) for ch in w]
    if None in j:
        return None
    out, i = "", 0
    while i < len(j):
        if i + 1 < len(j) and j[i] in CHO and j[i + 1] in JUNG:
            c, v, i = j[i], j[i + 1], i + 2
            if i < len(j) and j[i] in JUNG and v + j[i] in VC:
                v, i = VC[v + j[i]], i + 1
            t = " "
            if i < len(j) and j[i] in JONG and not (i + 1 < len(j) and j[i + 1] in JUNG):
                t, i = j[i], i + 1
            out += syl(c, v, t)
        else:
            return None
    return out


def roman2kor(w):
    w, out = w.lower(), ""
    while w:
        k = next((k for k in sorted(ROMAN, key=len, reverse=True) if w.startswith(k)), None)
        if not k:
            return None
        out, w = out + ROMAN[k], w[len(k):]
    return out


def deob(t):
    """영어 문장 댓글은 건드리지 않음(영어 단어가 엉뚱한 욕으로 바뀌는 것 방지)"""
    words = re.findall(r"[A-Za-z]+", t)
    if len(words) >= 4 and len(re.findall(r"[가-힣ㄱ-ㅣ]", t)) <= len(t) * 0.1:
        return t
    return re.sub(r"[A-Za-z]+", lambda m: roman2kor(m[0]) or eng2kor(m[0]) or m[0], t)


def phon(t):
    """된소리→예사소리, 비슷한 모음 통일 (씌발·쉬발·씨빨 → 시발)"""
    out = ""
    for ch in t:
        n = ord(ch) - 0xAC00
        if 0 <= n < 11172:
            c, v, j = CHO[n // 588], JUNG[n % 588 // 28], JONG[n % 28]
            ch = syl(TENSE.get(c, c), VOW.get(v, v), j)
        out += ch
    return out


CORE = [(w, pat(phon(w))) for w in ["시발", "병신", "븅신", "지랄", "염병", "개새끼", "니애미", "틀딱"]]


# 욕설과 글자가 겹치는 일반 표현 (검사 전에 지움)
SAFE = re.compile(r"새끼\s*(고양이|강아지|손가락|발가락|돼지|새|곰|오리)|쓰레기\s*(분리|봉투|줍|처리|매립|배출|소각|통)|분리수거|"
                  r"시발(점|역|택시|자동차)|병신(년|정변|박해|양요)|애비뉴|썅썅바|금수(저|강산)|능지처참|장애물|정신병원|"
                  r"(땅|딸기|사과|과일|열매|감|귤)\s*따먹|(불|전원|화면|촛불|조명|전기|폰|컴퓨터)[이가]?\s*꺼져|"
                  r"(위기|위험|재난|불행|겨울|추위|시련|운명)[이가]?\s*닥쳐|(잠|시간|돈|용량|공간|일손|인력|재료)[이가]?\s*모자란|주제에\s*(대해|관해|맞)")


def find(p, t):
    """띄어쓰기가 낀 매칭은 앞뒤가 다른 글자와 붙어 있으면 무시
    ('질병 신호'의 '병 신', '그 애 비밀'의 '애 비' 제외 / '병 신 같네'는 잡음)"""
    for m in p.finditer(t):
        a, b = m.start(), m.end()
        if " " not in m[0] or not ((a and re.match("[가-힣]", t[a - 1])) or (b < len(t) and re.match("[가-힣]", t[b]))):
            return True
    return False


# 욕 없이 돌려 까는 집단 비하: '집단을 가리키는 말' + '깎아내리는 일반화'가 한 댓글에 같이 있으면 의심
GROUP = re.compile(r"성별|여자|남자|여초|남초|지역|출신|도민|지방|사투리|외국인|조선족|흑인|백인|동남아|장애|노인|틀니|"
                   r"전라|경상|충청|강원|제주|홍어|과메기|[가-힣o○]{1,2}도\s*(사람|출신|것들)")
SLUR = re.compile(r"(?<=[가-힣])특(?![가-힣])|과학이|걸러야|거르|지능|미개|종특|원래 그렇|답이 없|일반인이랑\s*다|정상인이랑\s*다|수준\s*(잘\s*)?보|"
                  r"(통계|팩트)로?\s*(증명|확인)|역시\s*\S*(들|것들)은|하는 짓")


# 욕 없이 하는 성희롱: '신체 부위' + '성적인 시선' 표현이 같이 있으면 의심
BODY = re.compile(r"몸매|핏이|가슴|엉덩|허벅지|다리|골반|라인|상의|하의|치마|옷이|옷 |쪽이")
LEWD = re.compile(r"야해|야하|야한|꽉\s*차|터질|눈이\s*(감|가)|눈\s*돌아|눈을\s*못\s*떼|꼴리|꼴린|침\s*고|군침|만지고|벗기")


# 구체적 사실 주장(갑질·범죄 등) → 사실이든 거짓이든 명예훼손 검토 대상
FACT = re.compile(r"갑질|사기|횡령|탈세|불륜|바람피|전과|범죄자|폭행|성추행|성폭행|마약|도박|체불|떼먹|학폭|"
                  r"뒷광고|표절|조작|주작|거짓말쟁이|했다더라|했대|라던데|카더라")

# 유형 → (법적 검토, 관련 조항). 참고용이며 최종 판단은 수사기관·법원
LAW = {"욕설": ("모욕 의심", "형법 제311조(모욕)"), "비속어": ("모욕 의심", "형법 제311조(모욕)"),
       "인신공격": ("모욕 의심", "형법 제311조(모욕)"), "비난": ("모욕 의심", "형법 제311조(모욕)"),
       "위협": ("협박 의심", "형법 제283조(협박)"),
       "성적": ("성희롱·모욕 의심", "형법 제311조(모욕), DM이면 성폭력처벌법 제13조(통신매체이용음란)"),
       "명예훼손": ("명예훼손 검토", "정보통신망법 제70조(사실 1항·허위 2항)"),
       "혐오": ("집단 비하(개인 특정 어려우면 고소 어려움)", "개인이 특정되면 형법 제311조(모욕)"),
       "AI 판단": ("검토 필요", ""), "사용자 선택": ("검토 필요", "")}


def law(category):
    ls = [LAW.get(c.strip(), ("검토 필요", "")) for c in category.split(",") if c.strip()]
    return dict(law=", ".join(dict.fromkeys(a for a, _ in ls)), statute=" / ".join(dict.fromkeys(b for _, b in ls if b)))


CHUNG = re.compile(r"[가-힣]{1,4}충(?=들|이|아|[^가-힣]|$)")  # ~충 (멸칭)
CHUNG_OK = ("보충", "확충", "해충", "곤충", "유충", "성충", "회충", "구충", "방충", "살충", "완충", "절충", "충충", "기생충 영화")
HANNAM = re.compile(r"한남(?![자쪽동대산부오])")


def norm(t):
    """늘여 쓰기·숫자 치환 되돌리기: 씨이이이발→씨발, 10새→씹새, 18놈→씨발놈"""
    out = ""
    for ch in t:
        n, p = ord(ch) - 0xAC00, (ord(out[-1]) - 0xAC00) if out else -1
        # 받침 없는 글자 뒤 'ㅇ+같은 모음'은 늘여 쓰기 → 지움, 받침이 있으면 앞 글자로 합침 (씨이이발→씨발, 병시이인→병신)
        if 0 <= n < 11172 and 0 <= p < 11172 and p % 28 == 0 and n // 588 == 11 and n % 588 // 28 == p % 588 // 28:
            if n % 28:
                out = out[:-1] + chr(0xAC00 + p + n % 28)
            continue
        out += ch
    out = re.sub(r"(.)\1{2,}", r"\1", out)  # 같은 글자 3번 이상 → 1번
    out = re.sub(r"(?<!\d)18(?=[놈년새아])", "씨발", out)
    return re.sub(r"(?<!\d)10(?=[새쉐색])", "씹", out)


YOU = re.compile(r"(^|[^가-힣])(너|니|넌|널|네가|님|당신|얘|쟤|느그|니들|너네|너희|이\s*새끼|이\s*놈)([^가-힣]|$|[가는도를랑])")
SELF = re.compile(r"(^|[^가-힣])(나|내|난|날|저|제|전|우리)([^가-힣]|$|[가는도를의])|내\s*자신|탈출")
POS = re.compile(r"맛있|맛도리|좋다|좋네|좋아|웃기|웃김|웃겨|재밌|재미있|귀엽|귀여|예쁘|이쁘|멋있|멋지|최고|사랑|감동|레전드|대박|쩐다|잘한다|잘하네")


def classify(text):
    text = norm(SAFE.sub(" ", text))
    d = deob(text)
    hits = []
    ch = [m[0] for m in CHUNG.finditer(text) if not any(m[0].endswith(x) or x in text for x in CHUNG_OK)]
    if ch:
        hits.append((3, "혐오", f"멸칭 '{ch[0]}'"))
    if HANNAM.search(text):
        hits.append((3, "혐오", "키워드 '한남'"))
    g, sl = GROUP.search(text), SLUR.search(text)
    if g and sl:
        hits.append((1, "혐오", f"집단 비하 의심 '{g[0]}'+'{sl[0]}'"))
    b, l = BODY.search(text), LEWD.search(text)
    if b and l:
        hits.append((3, "성적", f"성희롱 의심 '{b[0].strip()}'+'{l[0]}'"))
    for c, s, w, p in PATS:
        if find(p, text):
            hits.append((s, c, f"키워드 '{w}'"))
        elif d != text and re.search("[가-힣]", w) and find(p, d):
            hits.append((s, c, f"우회 표기 '{w}'"))
    if not hits:
        ph = phon(d)
        hits = [(3, "욕설", f"발음 변형 '{w}'") for w, p in CORE if find(p, ph)][:1]
    f = FACT.search(text)
    if f:
        hits.append((1, "명예훼손", f"사실 주장 '{f[0]}'(진위 확인 필요)"))
    if not hits:
        return dict(label="정상", severity=0, category="", reason="", law="", statute="")
    hits.sort(reverse=True)
    if not YOU.search(text) and (SELF.search(text) or POS.search(text)) and hits[0][1] not in ("위협", "성적"):
        hits = [(1, c, r) for _, c, r in hits] + [(1, hits[0][1], "자기 비하·좋은 뜻 표현일 수 있음")]
    cat = ", ".join(dict.fromkeys(h[1] for h in hits))
    return dict(label="악플", severity=hits[0][0], category=cat,
                reason=", ".join(dict.fromkeys(h[2] for h in hits)), **law(cat))


# ---------- 유튜브 수집 ----------
def video_id(url):
    m = re.search(r"(?:v=|youtu\.be/|shorts/|embed/|live/)([\w-]{11})", url)
    return m[1] if m else None


def row(c, vid):
    s = c["snippet"]
    return dict(id=c["id"], author=s["authorDisplayName"], channel=s.get("authorChannelUrl", ""),
                cid=s.get("authorChannelId", {}).get("value", ""),
                text=s["textOriginal"], time=s["publishedAt"], link=f"https://youtu.be/{vid}?lc={c['id']}")


ERR = {"commentsDisabled": "이 영상은 댓글이 꺼져 있어요.", "videoNotFound": "영상을 찾을 수 없어요. 주소를 확인하세요.",
       "quotaExceeded": "오늘 API 사용량을 다 썼어요. 내일 다시 시도하세요.", "keyInvalid": "API 키가 올바르지 않아요."}


def get(path, **params):
    r = requests.get(f"https://www.googleapis.com/youtube/v3/{path}", params=params, timeout=20)
    if r.status_code != 200:
        e = r.json().get("error", {})
        reason = (e.get("errors") or [{}])[0].get("reason", "")
        raise RuntimeError(ERR.get(reason, e.get("message", "알 수 없는 오류")))
    return r.json()


def fetch(vid, key, limit, prog=lambda n: None):
    rows, raw, token = [], [], ""
    while len(rows) < limit:
        d = get("commentThreads", part="snippet,replies", videoId=vid, maxResults=100,
                textFormat="plainText", key=key, pageToken=token)
        raw.append(d)
        for th in d["items"]:
            top = th["snippet"]["topLevelComment"]
            rows.append(row(top, vid))
            reps = th.get("replies", {}).get("comments", [])
            if th["snippet"]["totalReplyCount"] > len(reps):  # 답글 6개 이상이면 따로 전부 가져옴
                reps, t = [], ""
                while True:
                    r = get("comments", part="snippet", parentId=top["id"], maxResults=100,
                            textFormat="plainText", key=key, pageToken=t)
                    raw.append(r)
                    reps += r["items"]
                    t = r.get("nextPageToken")
                    if not t:
                        break
            rows += [row(c, vid) for c in reps]
        prog(len(rows))
        token = d.get("nextPageToken")
        if not token:
            break
    return rows[:limit], raw


# ---------- 스크린샷 글자 읽기(OCR) ----------
UI = re.compile(r"[답담][글굴]|좋아요|댓글순|추천 댓글|정렬 기준|싫어요|공유|신고|번역 보기|더보기|자세히 보기|\d+\s*(초|분|시간|일|주|개월|년)\s*전")


def ocr(b):
    """스크린샷 → 글자. 작은 글씨는 확대, 다크모드는 반전, 아이콘·버튼 줄은 버리고
    '@아이디' 줄은 다음 줄의 작성자로 붙임 → [@아이디] 내용"""
    try:
        import pytesseract
        from PIL import Image, ImageOps, ImageStat
        im = ImageOps.grayscale(Image.open(io.BytesIO(b)))
        if ImageStat.Stat(im).mean[0] < 128:
            im = ImageOps.invert(im)
        k = max(1, min(3, 1400 / im.width))
        im = im.resize((int(im.width * k), int(im.height * k)), Image.LANCZOS)
        t = pytesseract.image_to_string(im, lang="kor+eng", config="--psm 6")
    except Exception:
        return ""
    out, who = [], ""
    for l in t.splitlines():
        m = re.search(r"@[\w.\-가-힣]+", l)
        if m:
            who = m[0]
            continue
        if "선택됨" in l:
            continue
        l = UI.sub("", l).strip()
        up = len(re.findall(r"[A-Z]", l)) / max(1, len(re.findall(r"[A-Za-z]", l)))
        if len(re.findall(r"[가-힣ㄱ-ㅎ]", l)) >= 2 or (len(re.findall(r"[A-Za-z]{3,}", l)) >= 3 and up < 0.5):
            out.append(f"[{who}] {l}" if who else l)
            who = ""
    return "\n".join(out)


# ---------- 채증 보고서 ----------
def kst(t):
    """작성 시각을 KST와 UTC로 같이 표기"""
    if not t:
        return ""
    u = datetime.fromisoformat(t.replace("Z", "+00:00"))
    return f'{u.astimezone(KST):%Y-%m-%d %H:%M:%S} KST ({u:%Y-%m-%d %H:%M:%S} UTC)'


def report(sel, d, total):
    doc = Document()
    doc.styles["Normal"].font.size = Pt(10)

    def p(t, size=10, bold=False):
        r = doc.add_paragraph().add_run(t)
        r.bold, r.font.size = bold, Pt(size)

    def table(pairs):
        tb = doc.add_table(0, 2, style="Table Grid")
        for k, v in pairs:
            if v not in ("", None):
                a, b = tb.add_row().cells
                a.text, b.text = k, str(v)
        doc.add_paragraph()

    yt = d["src"] == "유튜브"
    p("온라인 악성 댓글 채증 자료", 16, True)
    p("1. 수집 개요", 12, True)
    table([("출처", d["src"]), ("영상 주소", d["url"]), ("수집 일시", kst(d["at"])),
           ("수집 방법", "Google YouTube Data API v3 공식 서버에 직접 요청하여 받은 응답을 가공 없이 원본(JSON)으로 "
                       "저장하고, 그 원본에서 아래 내용을 추출함" if yt else "사용자 직접 입력·스크린샷 글자 인식"),
           ("전체 건수", total), ("증거 선별 수", len(sel))])
    rep = pd.Series([c["author"] for c in sel if c["author"]]).value_counts()
    if (rep >= 2).any():
        p("반복 작성자 (2건 이상 — 지속성·악의성 입증 자료)", 11, True)
        table([(a, f"{n}건") for a, n in rep[rep >= 2].items()])
    p("고소 전 확인 사항", 11, True)
    for t in ["□ 공연성: 여러 사람이 볼 수 있는 공개 댓글인가 (비공개·검토 대기 댓글은 약함)",
              "□ 특정성: 댓글이 고소인을 가리킨다는 것을 알 수 있는가 (영상 속 인물 = 고소인 등)",
              "□ 고소 기간: 모욕죄는 범인을 안 날부터 6개월 이내 고소해야 함 (친고죄)",
              "□ 명예훼손 검토 항목은 해당 주장이 사실인지 거짓인지 구분하여 진술"]:
        p(t, 9)
    p("※ 아래 '법적 검토' 항목은 표현 유형에 따른 참고 분류이며 법률 자문이 아님", 9)
    p("2. 악성 댓글 상세", 12, True)
    for i, c in enumerate(sel, 1):
        p(f"증거 {i}", 10, True)
        table([("작성자", c["author"]), ("채널 주소", c["channel"]), ("채널 고유 ID", c.get("cid", "")),
               ("작성 일시", kst(c["time"])),
               ("내용", c["text"]), ("유형/심각도", f'{c["category"]} / {c["severity"]}'),
               ("법적 검토", c.get("law", "")), ("관련 조항", c.get("statute", "")),
               ("판단 근거", c["reason"]), ("원문 링크", c["link"])])
    n = 3
    if d["imgs"]:
        p("3. 첨부 스크린샷", 12, True)
        for i, b in enumerate(d["imgs"], 1):
            p(f"스크린샷 {i} (SHA-256: {hashlib.sha256(b).hexdigest()})", 9)
            doc.add_picture(io.BytesIO(b), width=Cm(12))
        n = 4
    p(f"{n}. 원본 데이터 무결성", 12, True)
    p(f"원본 SHA-256: {d['sha']}")
    p("※ 최종 판단은 수사기관·법원에 있음. " + ("원문 링크 화면 캡처를 함께 첨부할 것을 권장함." if yt else
      "직접 입력 자료는 작성자·작성 시각이 확인되도록 원본 화면 캡처를 반드시 함께 제출할 것."), 9)
    b = io.BytesIO()
    doc.save(b)
    return b.getvalue()


# ---------- AI 분류 모델 (공개 데이터셋 약 9만 개로 서버에서 직접 학습) ----------
# Smilegate AI UnSmile(2022, CC BY-NC-ND 4.0) + K-MHaS(COLING 2022, CC BY-SA 4.0)
GH = "https://raw.githubusercontent.com/"
UNSMILE = GH + "smilegate-ai/korean_unsmile_dataset/main/unsmile_train_v1.0.tsv"
KMHAS = GH + "adlnlp/K-MHaS/main/data/kmhas_train.txt"
AI_CUT = 0.65  # 검증 결과: 악플 약 70~76% 잡고, 정상을 잘못 잡는 비율 약 6%


@st.cache_resource(show_spinner="AI 모델 학습 중… (처음 한 번만, 1분 정도)")
def model():
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    try:
        u = pd.read_csv(UNSMILE, sep="\t")
        k = pd.read_csv(KMHAS, sep="\t", quoting=3)
    except Exception:
        return None
    x = pd.concat([u["문장"], k["document"].astype(str).str.strip('"')])
    y = pd.concat([u["clean"] == 0, k["label"].astype(str) != "8"])
    vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(1, 4), min_df=3, sublinear_tf=True, max_features=300000)
    m = LogisticRegression(max_iter=3000, C=4, class_weight="balanced").fit(vec.fit_transform(x), y)
    return vec, m


def save(rows, raw, src, url="", vid="직접입력", imgs=()):
    for r in rows:
        r.update(classify(r["text"]))
    vm = model()
    if vm and rows:
        for r, pr in zip(rows, vm[1].predict_proba(vm[0].transform([r["text"] for r in rows]))[:, 1]):
            r["ai"] = round(pr * 100)
            # 글자 2개 미만이거나 자음·모음 낙서(ㅓ버바펴…)가 더 많은 댓글은 AI 판단 제외 (오탐 방지)
            syl, jamo = len(re.findall("[가-힣]", r["text"])), len(re.findall("[ㄱ-ㅣ]", r["text"]))
            if pr >= AI_CUT and r["label"] == "정상" and syl >= 2 and jamo <= syl:
                r.update(label="악플", severity=2 if pr >= 0.8 else 1, category="AI 판단",
                         reason=f"AI 악플 확률 {pr:.0%}", **law("AI 판단"))
    st.session_state.res = dict(rows=rows, raw=raw, sha=hashlib.sha256(raw + b"".join(imgs)).hexdigest(),
                              at=datetime.now(timezone.utc).isoformat(), url=url, vid=vid,
                              src=src, imgs=list(imgs))


# ---------- 화면 ----------
st.set_page_config("악플 수집기", "🛡️", layout="wide")
st.markdown("""<style>[data-testid='stToolbar']{display:none}
.block-container{max-width:1150px;padding-top:2.5rem}</style>""", unsafe_allow_html=True)
st.title("🛡️ 악플 수집기")
st.caption("유튜브 댓글이나 SNS 스크린샷에서 악플을 찾아내고, 고소에 쓸 수 있는 채증 보고서로 정리합니다.")
for col, (h, b) in zip(st.columns(3), [("① 넣기", "유튜브 주소 또는 스크린샷·텍스트"),
                                       ("② 자동 분류", "키워드 + 우회 표기 + AI 모델"),
                                       ("③ 보고서 받기", "검토 후 Word 채증 보고서 다운로드")]):
    col.container(border=True).markdown(f"**{h}**  \n{b}")

t1, t2 = st.tabs(["🔗 유튜브 링크", "📋 텍스트·스크린샷 (인스타·카톡 등)"])
with t1:
    try:
        key = st.secrets["YOUTUBE_API_KEY"]
    except Exception:
        key = st.text_input("YouTube API 키", type="password")
    a, b, c = st.columns([5, 3, 1.3], vertical_alignment="bottom")
    url = a.text_input("유튜브 영상 주소", placeholder="https://youtu.be/...")
    limit = b.number_input("최대 수집 댓글 수 (1만 개 ≈ 1~2분)", 100, 50000, 3000, 1000)
    if c.button("수집 시작", type="primary"):
        vid = video_id(url)
        if not (vid and key):
            st.error("주소와 API 키를 확인하세요.")
            st.stop()
        bar = st.progress(0.0, "댓글 수집 중…")
        try:
            rows, raw = fetch(vid, key, limit, lambda n: bar.progress(min(n / limit, 1.0), f"댓글 {n:,}개 수집 중…"))
        except Exception as e:
            st.error(f"수집 실패: {e}")
            st.stop()
        bar.progress(1.0, "분류 중…")
        save(rows, json.dumps(raw, ensure_ascii=False).encode(), "유튜브", url, vid)
        bar.empty()

with t2:
    a, b = st.columns(2)
    imgs = a.file_uploader("스크린샷 첨부 (여러 장 가능 · 사진은 보고서에 증거로 들어가요)",
                           type=["png", "jpg", "jpeg"], accept_multiple_files=True)
    if imgs and a.button("사진에서 글자 읽기"):
        with st.spinner("글자 읽는 중…"):
            st.session_state.txt = "\n".join(ocr(f.getvalue()) for f in imgs)
    txt = b.text_area("댓글·메시지 (한 줄에 하나씩 · 잘못 읽힌 글자는 고쳐주세요)", key="txt", height=200)
    if b.button("분류하기", type="primary"):
        lines = [l.strip() for l in txt.splitlines() if l.strip()]
        if not lines:
            st.error("내용을 붙여넣거나 사진에서 글자를 읽어주세요.")
            st.stop()
        rows = []
        for i, l in enumerate(lines, 1):
            m = re.match(r"\[(@?[^\]]+)\]\s*(.*)", l)  # [@아이디] 내용 → 작성자 분리
            rows.append(dict(id=f"m{i}", author=m[1] if m else "", channel="", text=m[2] if m else l, time="", link=""))
        save(rows, txt.encode(), "직접 입력", imgs=[f.getvalue() for f in imgs or []])

d = st.session_state.get("res")
if d:
    df = pd.DataFrame(d["rows"])
    st.divider()
    bad = df.label == "악플"
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("출처", d["src"])
    m2.metric("전체", f"{len(df):,}")
    m3.metric("악플 후보", f"{bad.sum():,}")
    m4.metric("그중 AI가 찾은 것", f"{(df.category == 'AI 판단').sum():,}")
    if bad.any():
        with st.expander("📊 악플 현황 (유형 분석 · 상습 작성자)", expanded=True):
            g1, g2 = st.columns(2)
            g1.markdown("**유형별 악플 수**")
            g1.bar_chart(df[bad].category.str.split(", ").explode().value_counts(), color="#FF4B4B")
            g2.markdown("**상습 작성자 Top 5** (2건 이상 = 지속성 입증 자료)")
            rep = df[bad & (df.author != "")].author.value_counts().head(5).rename_axis("작성자").reset_index(name="악플 수")
            if len(rep):
                g2.dataframe(rep, hide_index=True)
            else:
                g2.caption("작성자 정보가 없어 집계할 수 없어요.")
            if (df.time != "").any():
                st.markdown("**날짜별 악플 수**")
                st.line_chart(pd.to_datetime(df[bad].time).dt.tz_convert("Asia/Seoul").dt.date.value_counts().sort_index())

    # 필터: 보고 싶은 단어·유형만 골라보기 (악플이 아닌 댓글도 검색 가능)
    f1, f2, f3 = st.columns([1, 1.3, 2])
    scope = f1.radio("범위", ["악플만", "전체 댓글"], horizontal=True)
    cats = f2.multiselect("유형", list(RULES) + ["명예훼손", "AI 판단"], placeholder="전체")
    q = f3.text_input("검색어 (쉼표로 여러 개, 띄어쓰기·숫자 끼운 변형도 찾음)")
    v = df if scope == "전체 댓글" else df[bad]
    if cats:
        v = v[v["category"].apply(lambda c: any(x in c for x in cats)).astype(bool)]
    words = [w.strip() for w in q.split(",") if w.strip()]
    if words:
        v = v[v["text"].apply(lambda t: any(pat(w).search(t) for w in words)).astype(bool)]
    v = v.sort_values("severity", ascending=False).copy()
    v.insert(0, "포함", (v.label == "악플") & (v.severity >= 2))  # 애매한 것(심각도 1)은 기본 체크 해제
    st.caption(f"{len(v):,}개 표시 · 심각도 1 = 애매함(체크 해제됨, 직접 판단) · 2 = 명백한 모욕 · 3 = 심각(욕설·위협·혐오·성희롱)")
    cols = ["포함", "severity", "law", "author", "text", "reason", "ai", "link"]
    if d["src"] != "유튜브":
        cols = ["포함", "severity", "law", "author", "text", "reason", "ai"]
    ed = st.data_editor(v[[c for c in cols if c in v]], hide_index=True,
                        column_config={"severity": "심각도", "law": "법적 검토", "author": "작성자",
                                       "text": st.column_config.TextColumn("내용", width="large"),
                                       "reason": "판단 근거", "ai": "AI 점수(%)",
                                       "link": st.column_config.LinkColumn("원문", display_text="열기")})
    sel = df.loc[ed[ed["포함"]].index].to_dict("records")
    for c in sel:
        if c["label"] == "정상":
            c.update(category="사용자 선택", reason="검토자가 직접 선택" + (f" (검색어: {q})" if q else ""),
                     **law("사용자 선택"))
    c1, c2, c3 = st.columns(3)
    c1.download_button("📄 채증 보고서(Word)", report(sel, d, len(df)), f"채증_{d['vid']}.docx",
                       disabled=not sel, type="primary")
    c2.download_button("📊 전체 목록(CSV)", df.to_csv(index=False).encode("utf-8-sig"), f"목록_{d['vid']}.csv")
    c3.download_button("🔒 원본 데이터", d["raw"], f"원본_{d['vid']}." + ("json" if d["src"] == "유튜브" else "txt"))
    st.caption(f"원본 SHA-256: {d['sha']}")
