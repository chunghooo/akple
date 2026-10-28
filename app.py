import re, io, json, hashlib, requests
from datetime import datetime, timezone, timedelta
import pandas as pd
import streamlit as st

KST = timezone(timedelta(hours=9))

# ---------- 키워드 (유형: (심각도, [단어])) ----------
RULES = {
    "욕설": (3, ["시발", "씨발", "ㅅㅂ", "ㅆㅂ", "좆", "ㅈ같", "x같", "개새끼", "개색기", "새끼", "병신", "ㅂㅅ", "븅신",
                 "지랄", "ㅈㄹ", "염병", "썅", "엠창", "느금", "니애미", "애미", "애비", "ㅄ", "ㄴㄱㅁ", "ㅅㄲ", "씨바", "씨팔", "시팔", "ㅅㅍ", "fuck", "shit", "bitch", "asshole", "stfu", "18놈", "18새", "십팔놈", "씹새", "장애새끼", "장애냐", "고아새끼", "고아냐"]),
    "비속어": (1, ["존나", "졸라", "ㅈㄴ", "개같", "뒤진다", "뒤질"]),
    "비난": (1, ["악마", "꼴보기", "퉤", "ㅉㅉ", "존망", "토할", "와꾸", "뇬", "가증", "🖕", "ㅗㅗ", "ㅁㅊ", "씹덕", "무지성", "발작버튼", "누칼협", "알빠노", "긁혔", "뇌절", "벌레같", "관종"]),
    "위협": (3, ["죽어라", "죽으세요", "죽어버려", "죽었으면", "뒤지세요", "디져", "디지세요", "뒤져라", "자살해", "죽여버", "찾아간다", "패버"]),
    "인신공격": (2, ["미친놈", "미친년", "또라이", "돌아이", "멍청", "찐따", "한심", "쓰레기", "못생", "정신병자", "싸이코패스", "사이코패스", "양아치", "인간같지", "인간이냐", "금수", "모자란",
                     "정병", "꽃뱀", "맞을짓", "피해자코스프레", "피해자인척", "자작극", "꺼지세요", "꺼지라", "닥치세요", "닥치라", "돼지같", "돼지년", "오크녀", "오크남", "개저씨", "빻았", "빻은", "역겹", "역겨", "idiot", "stupid", "moron", "loser", "retard", "꺼져", "닥쳐", "ㄲㅈ", "ㄷㅊ", "상태봐라", "꼬라지", "주제에", "얼굴값", "꼴값", "능지", "뇌빼고", "쿨찐", "방구석여포", "호소인"]),
    "혐오": (3, ["한남충", "한녀", "김치녀", "틀딱", "급식충", "잼민", "맘충", "짱깨", "쪽바리", "스윗한남", "퐁퐁남", "설거지론", "영포티", "오팔륙", "군캉스"]),
    "성적": (3, ["따먹", "몸매보", "ㅗㅜㅑ", "눈요기", "육덕", "헤응", "스폰녀", "오피녀", "조건만남"]),
}
SEP = r"[\s\d._*~!^♡♥,·ㅇㅋㅎㅡ-]*"  # 끼워넣은 숫자·기호·ㅇㅋㅎ 건너뜀


def pat(w):
    if w.isascii() and w.isalpha():  # 영어 욕은 단어 앞부분이 맞을 때만 (This hit → s hit 오탐 방지)
        return re.compile(r"(?<![a-z])" + w, re.I)
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
SAFE = re.compile(r"새끼줄|새끼[를가]?\s*(낳|배|품|쳤)|지랄발광\s*17세|새끼\s*(고양이|강아지|손가락|발가락|돼지|새|곰|오리)|쓰레기\s*(분리|봉투|줍|처리|매립|배출|소각|통)|분리수거|"
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
GROUP = re.compile(r"성별|나이대|국적|집단|세대|여자|남자|여초|남초|지역|출신|도민|지방|사투리|외국인|조선족|흑인|백인|동남아|장애|노인|틀니|"
                   r"전라|경상|충청|강원|제주|홍어|과메기|[가-힣o○]{1,2}도\s*(사람|출신|것들)")
SLUR = re.compile(r"(?<=[가-힣])특(?![가-힣])|과학이|걸러야|거르|지능|미개|종특|원래 그렇|답이 없|일반인이랑\s*다|정상인이랑\s*다|수준\s*(잘\s*)?보|"
                  r"(통계|팩트)로?\s*(증명|확인)|역시\s*\S*(들|것들)은|하는 짓|믿을\s*수\s*없|생각이\s*없|내보내|"
                  r"뻔하|모두\s*같은|다\s*똑같|문제를\s*일으")


# 욕 없이 하는 성희롱: '신체 부위' + '성적인 시선' 표현이 같이 있으면 의심
BODY = re.compile(r"몸매|핏이|가슴|엉덩|허벅지|다리|골반|몸\s*라인|상의|하의|치마|옷이|옷 |쪽이")
LEWD = re.compile(r"(^|[^가-힣]|너무|넘|좀|개|존나)야[해하한]|꽉\s*차|터질|눈이\s*(감|가)|눈\s*돌아|눈을\s*못\s*떼|꼴리|꼴린|침\s*고|군침|만지고|벗기")


# 구체적 사실 주장(갑질·범죄 등) → 사실이든 거짓이든 명예훼손 검토 대상
FACT = re.compile(r"갑질|사기|횡령|탈세|불륜|바람피|전과|범죄자|폭행|성추행|성폭행|마약|도박|체불|떼먹|학폭|"
                  r"뒷광고|표절|조작|주작|거짓말쟁이|했다더라|했대|라던데|카더라|숨겼|빼돌|개인적으로\s*썼|"
                  r"소문|의혹|(다는|다고|라는)\s*(글|댓글|말|얘기|주장)")

# 유형 → (법적 검토, 관련 조항). 참고용이며 최종 판단은 수사기관·법원
LAW = {"욕설": ("모욕 의심", "형법 제311조(모욕)"), "비속어": ("모욕 의심", "형법 제311조(모욕)"),
       "인신공격": ("모욕 의심", "형법 제311조(모욕)"), "비난": ("모욕 의심", "형법 제311조(모욕)"),
       "위협": ("협박 의심", "형법 제283조(협박)"),
       "성적": ("성희롱·모욕 의심", "형법 제311조(모욕), DM이면 성폭력처벌법 제13조(통신매체이용음란)"),
       "명예훼손": ("명예훼손 검토", "정보통신망법 제70조(사실 1항·허위 2항)"),
       "혐오": ("집단 비하(개인 특정 어려우면 고소 어려움)", "개인이 특정되면 형법 제311조(모욕)"),
       "AI 판단": ("검토 필요", ""), "사용자 선택": ("검토 필요", ""),
       "신상노출": ("신상 노출 의심 (즉시 삭제 요청 권장)", "플랫폼 신고·삭제 요청, 내용에 따라 정보통신망법 제70조 검토")}


def law(category):
    ls = [LAW.get(c.strip(), ("검토 필요", "")) for c in category.split(",") if c.strip()]
    return dict(law=", ".join(dict.fromkeys(a for a, _ in ls)), statute=" / ".join(dict.fromkeys(b for _, b in ls if b)))


CHUNG = re.compile(r"[가-힣]{1,4}충(?=들|이|아|[^가-힣]|$)")  # ~충 (멸칭)
CHUNG_OK = ("대충", "이충", "보충", "충돌", "충격", "충성", "충전", "충분", "확충", "해충", "곤충", "유충", "성충", "회충", "구충", "방충", "살충", "완충", "절충", "충충", "기생충 영화")
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


EXCL = {"시발", "씨발", "ㅅㅂ", "ㅆㅂ", "존나", "졸라", "ㅈㄴ", "개같", "fuck", "shit"}  # 감탄사·강조로도 쓰이는 욕
YOU = re.compile(r"\byou\b|(^|[^가-힣])(너|니|넌|널|네가|님|당신|얘|쟤|느그|니들|너네|너희|이\s*새끼|이\s*놈)([^가-힣]|$|[가는도를랑])")
SELF = re.compile(r"(^|[^가-힣])(나|내|난|날|저|제|전|우리)([^가-힣]|$|[가는도를의])|내\s*자신|탈출")
QUOTE = re.compile(r"(이)?라고\s*(했|하|쓴|한|하네|하더|댓글)|무슨\s*뜻|뜻이\s*뭐|뜻이에요|라는\s*(말|댓글)|신고했|신고합")
THING = re.compile(r"날씨|게임|버스|지하철|편집|음질|화질|광고|서버|렉|와이파이|폰|컴퓨터|과제|시험|월요일|출근|회사|알고리즘|자막|썸네일")
POS = re.compile(r"amazing|awesome|love|great|best|goat|fire|insane|지린다|지리네|지렸|지림|찢었|찢었다|찢어|미쳤다|미쳤네|미쳤어|쩐다|쩔어|쩔었|명곡|띵곡|소름|역대급|천재|갓|"
                 r"찢|오진다|오지네|개좋|개쩔|개웃|개맛|맛있|맛도리|좋다|좋네|좋아|웃기|웃김|웃겨|재밌|재미있|귀엽|귀여|예쁘|이쁘|멋있|멋지|최고|사랑|감동|레전드|대박|쩐다|잘한다|잘하네")


# 전화번호·동호수·학교+학년 등 신상 정보 노출
DOX = re.compile(r"01[016789][-\s.]?\d{3,4}[-\s.]?\d{4}|\d{3,4}동\s*\d{3,4}호")
SCHOOL = re.compile(r"[가-힣]{2,}(초|중|고|대학교|대)\s*(다니|재학|\d\s*학년)")


# 욕 없이 정중하게 하는 공격 — 키워드로 확정하지 않고 '의심(심각도 1)'으로만 올림 → 사람·생성형 AI 검토
WHO = re.compile(r"당신|너\b|너는|넌|니가|네가|저\s*(사람|분|인간|놈|채널|업체)|이\s*(사람|인간|놈|채널)|만든\s*사람|사람(이|은|들은)|인간(이|은)")
LOW = re.compile(r"수준\s*(낮|이하|보니|하고는|을\s*보니)|무식|자격(도|이)?\s*없|답이\s*없|부끄럽지\s*않|부끄러운\s*줄|아는\s*척|"
                 r"이해(도|력)?\s*없|생각(이라는\s*걸|이)?\s*(없|하나|좀)|자체가\s*문제|저급|저질|쓸모\s*없|어리석|창피한\s*줄")
STALK = re.compile(r"어디\s*사는지|사는\s*곳|집\s*(주소|앞)|학교\s*앞|회사\s*앞|출퇴근|다니는\s*(길|곳)")
THREAT = re.compile(r"가만\s*(두지|안\s*둬|안\s*있)|두고\s*보자|어떻게\s*되는지\s*보자|알게\s*해\s*줄|찾아가서|찾아갈|"
                    r"밖에서\s*만나|조심해|다\s*안다|알고\s*있으니|기다리면\s*되")
SEX2 = re.compile(r"(몸매|부위|옷차림|외모|가슴|엉덩|허벅지).{0,15}(만\s*(계속\s*)?(보|눈)|눈이\s*가|눈에\s*들어|시선을\s*끌|"
                  r"야하게|성적인|농담거리)|야하게\s*찍")


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
    if (STALK.search(text) and THREAT.search(text)) or re.search(r"가만\s*(두지|안\s*둬)|두고\s*보자|어떻게\s*되는지\s*보자", text):
        hits.append((2, "위협", "위협 의심 (거주지·동선 언급 또는 경고)"))
    elif THREAT.search(text) and WHO.search(text):
        hits.append((1, "위협", f"위협 의심 '{THREAT.search(text)[0]}'(문맥 확인 필요)"))
    if SEX2.search(text):
        hits.append((1, "성적", "성적 대상화 의심(문맥 확인 필요)"))
    lo = LOW.search(text)
    if lo:
        hits.append((1, "인신공격", f"비하 의심 '{lo[0]}'(문맥 확인 필요)"))
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
        how = "추측·의견 표현" if re.search(r"것\s*같|듯|아닐까|아니냐|일까|인가|\?", text) else "단정 표현"
        hits.append((1, "명예훼손", f"사실 주장 '{f[0]}'({how}, 진위 확인 필요)"))
    dox, sch = DOX.search(text), SCHOOL.search(text)
    if dox or sch:  # 번호·동호수는 확실(3), 학교는 본인 얘기일 수도 있어 애매(1)
        hits.append((3 if dox else 1, "신상노출", f"개인정보 노출 '{(dox or sch)[0]}'"))
    if not hits:
        return dict(label="정상", severity=0, category="", reason="", law="", statute="")
    hits.sort(reverse=True)
    used = {w for h in hits for w in re.findall(r"'([^']+)'", h[2])}
    if not YOU.search(text) and POS.search(text) and used <= EXCL:
        # 대상 없이 감탄·칭찬에 섞인 욕 ("노래 지린다 ㅅㅂ") → 모욕 대상이 없어 정상 처리
        return dict(label="정상", severity=0, category="", reason="칭찬·감탄 속 욕설(대상 없음)", law="", statute="")
    why = ("남의 말을 인용·신고하는 문장일 수 있음" if QUOTE.search(text) else
           "자기 비하·좋은 뜻 표현일 수 있음" if SELF.search(text) or POS.search(text) else
           "사람이 아닌 상황·사물에 대한 욕일 수 있음" if THING.search(text) else "")
    if why and not YOU.search(text) and hits[0][1] not in ("위협", "성적", "명예훼손", "신상노출"):
        hits = [(1, c, r) for _, c, r in hits] + [(1, hits[0][1], why)]
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
                text=s["textOriginal"], time=s["publishedAt"], link=f"https://www.youtube.com/watch?v={vid}&lc={c['id']}")


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


FONT_PATHS = ["/usr/share/fonts/truetype/nanum/NanumGothic.ttf", "/usr/share/fonts/truetype/nanum/NanumBarunGothic.ttf",
              "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", "C:/Windows/Fonts/malgun.ttf"]


@st.cache_resource
def kr_font():
    """한글 폰트 등록 (서버는 packages.txt의 fonts-nanum). 없으면 기본 폰트(한글 깨짐)"""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    import os
    for f in FONT_PATHS:
        if os.path.exists(f):
            pdfmetrics.registerFont(TTFont("KR", f, subfontIndex=0) if f.endswith(".ttc") else TTFont("KR", f))
            return "KR", set(pdfmetrics.getFont("KR").face.charToGlyph)
    return "Helvetica", None


def report(sel, d, case, total):
    """EVIDA 증거 정리 보고서 (PDF) — 사건 기본정보 → 증거일람표 → 증거 상세 → 첨부 → 안내"""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, Image, PageBreak
    from xml.sax.saxutils import escape
    font, glyphs = kr_font()

    def clean(t):  # 폰트에 없는 글자(이모지 등)는 □로, 빈 값은 '미확인'
        t = str(t).strip() if t not in (None, "") and str(t) != "nan" else "미확인"
        return "".join(ch if glyphs is None or ord(ch) in glyphs or ch in "\n\t " else "□" for ch in t)

    S = lambda size=9, bold=False, color="#000000": ParagraphStyle("s", fontName=font, fontSize=size,
                                                                     leading=size * 1.45, textColor=color, wordWrap="CJK")
    P = lambda t, *a: Paragraph(escape(clean(t)).replace("\n", "<br/>"), S(*a))
    H = lambda t: [Spacer(1, 8), P(t, 12, True, "#1F3A5F"), Spacer(1, 4)]
    grid = TableStyle([("FONTNAME", (0, 0), (-1, -1), font), ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                       ("VALIGN", (0, 0), (-1, -1), "TOP"), ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F2F4F7"))])

    def kv(pairs):
        t = Table([[P(k, 9), P(v, 9)] for k, v in pairs], colWidths=[3.6 * cm, 13.4 * cm])
        t.setStyle(grid)
        return [t, Spacer(1, 6)]

    yt = d["src"] == "유튜브"
    times = sorted(c["time"] for c in sel if c.get("time"))
    authors = pd.Series([c["author"] for c in sel if c.get("author")]).value_counts()
    laws = pd.Series([c.get("law") or "검토 필요" for c in sel]).value_counts()
    summary = (f"{d['src']} 게시물에서 수집한 댓글 {total:,}건 중 사용자가 검토·선택한 {len(sel)}건을 증거로 정리함. "
               + (f"선택 댓글 작성 시각 범위: {kst(times[0])} ~ {kst(times[-1])}. " if times else "작성 시각: 미확인. ")
               + (f"작성자 {len(authors)}명" + (f"(2건 이상 작성: {', '.join(f'{a} {n}건' for a, n in authors[authors >= 2].items())})"
                                              if (authors >= 2).any() else "") + ". " if len(authors) else "작성자: 미확인. ")
               + "참고 분류: " + ", ".join(f"{k} {v}건" for k, v in laws.items()) + ".")

    el = [P("EVIDA 증거 정리 보고서", 18, True, "#1F3A5F"), P("신고 준비용 참고자료 · 경찰 공식 고소장이 아님", 10, False, "#666666"),
          Spacer(1, 10)]
    el += H("1. 사건 기본정보")
    el += kv([("보고서 생성일", datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST")),
              ("사건명", case.get("title") or "온라인 댓글 관련 증거 정리"),
              ("고소인(선택)", case.get("name") or "미기재"), ("연락처(선택)", case.get("contact") or "미기재"),
              ("피해 기간", case.get("period") or (f"미기재 (참고: 선택 댓글 작성일 {case['auto']})" if case.get("auto") else "미기재")), ("플랫폼 / 게시물 URL", f"{d['src']} / {case.get('url') or d['url']}"),
              ("수집 일시", kst(d["at"])),
              ("수집 방법", "Google YouTube Data API v3 공식 서버 응답을 가공 없이 원본(JSON)으로 저장하고 그 원본에서 추출"
               if yt else "사용자 직접 입력·스크린샷 글자 인식(작성자·시각은 원본 화면으로 확인 필요)"),
              ("선택된 증거 건수", f"{len(sel)}건"), ("사건 경위 (사용자 작성)", case.get("story") or "미기재"),
              ("피해 내용 (사용자 작성)", case.get("harm") or "미기재"), ("추가 설명", case.get("note") or "미기재"),
              ("사건 요약 (자동 정리)", summary)])
    el += H("고소 전 확인 사항")
    for t in ["□ 공연성: 여러 사람이 볼 수 있는 공개 댓글인가 (비공개·검토 대기 댓글은 약함)",
              "□ 특정성: 댓글이 고소인을 가리킨다는 것을 알 수 있는가 (영상 속 인물 = 고소인 등)",
              "□ 고소 기간: 모욕죄는 범인을 안 날부터 6개월 이내 고소해야 함 (친고죄)",
              "□ 사실 주장이 담긴 댓글은 그 내용이 사실인지 거짓인지 구분하여 진술"]:
        el.append(P(t, 9))

    el += [PageBreak()] + H("2. 증거일람표")
    rows = [[P(h, 8, True) for h in ["번호", "작성자", "작성 시각(KST)", "원문", "출처"]]]
    for i, c in enumerate(sel, 1):
        rows.append([P(f"EV-{i:03d}", 8), P(c.get("author"), 8), P(kst(c.get("time"))[:19], 8), P(c["text"], 8),
                     P("YouTube API" if yt else "직접 입력", 8)])
    t = Table(rows, colWidths=[1.6 * cm, 2.8 * cm, 2.6 * cm, 8 * cm, 2 * cm], repeatRows=1)
    t.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, -1), font), ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                           ("VALIGN", (0, 0), (-1, -1), "TOP"), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EDF3"))]))
    el.append(t)

    el += [PageBreak()] + H("3. 증거 상세")
    for i, c in enumerate(sel, 1):
        el.append(P(f"EV-{i:03d}", 10, True))
        el += kv([("댓글 ID", c.get("id") if yt else "미확인 (직접 입력)"), ("작성자", c.get("author")),
                  ("작성자 채널 ID / URL", f"{c.get('cid') or '미확인'} / {c.get('channel') or '미확인'}"),
                  ("작성 시각", kst(c.get("time"))), ("원문 (수정 없음)", c["text"]),
                  ("원본 링크", c.get("link") or "미확인"), ("사용자 메모", c.get("memo") or "없음"),
                  ("[참고] 자동 분류", f"{c.get('law') or '검토 필요'} / 관련 조항: {c.get('statute') or '-'}"),
                  ("[참고] 판단 근거", f"{c.get('reason') or '-'} · AI 점수 {c['ai'] if pd.notna(c.get('ai')) else '-'}%"
                   + (f" · 생성형 AI: {c['gem']}" if c.get("gem") and str(c["gem"]) != "nan" else ""))])
    if d["imgs"]:
        el += H("4. 첨부 스크린샷")
        for i, b in enumerate(d["imgs"], 1):
            el.append(P(f"스크린샷 {i} · SHA-256 {hashlib.sha256(b).hexdigest()}", 8))
            im = Image(io.BytesIO(b))
            k = min(15 * cm / im.imageWidth, 20 * cm / im.imageHeight)
            im.drawWidth, im.drawHeight = im.imageWidth * k, im.imageHeight * k
            el += [im, Spacer(1, 6)]
    el += H(("5" if d["imgs"] else "4") + ". 안내 및 자료의 한계")
    for t in ["본 문서는 EVIDA가 생성한 신고 준비용 참고자료이며, 경찰 공식 고소장이나 법적 판단 문서가 아님.",
              "'[참고]' 항목은 키워드 규칙·AI가 표현 유형을 분류한 것으로, 범죄 성립 여부는 수사기관·법원이 판단함.",
              "원문은 수집 당시 그대로이며, 증거의 진정성 확인을 위해 원본 링크 화면 캡처를 함께 제출할 것을 권장함.",
              "'미확인'은 원본 데이터에 해당 값이 없음을 뜻함.",
              f"원본 데이터 SHA-256: {d['sha']} (원본 파일과 대조하여 수집 후 변경 여부 확인 가능)"]:
        el.append(P("- " + t, 8.5))
    b = io.BytesIO()
    SimpleDocTemplate(b, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=1.8 * cm, bottomMargin=1.8 * cm,
                      title="EVIDA 증거 정리 보고서").build(el)
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


# ---------- 2차: 생성형 AI(Gemini) 재검토 — 애매한 댓글만 묶어서 한 번에 ----------
GEM = "https://generativelanguage.googleapis.com/v1beta/"
GEM_PROMPT = """너는 한국어 온라인 댓글이 특정인을 향한 악플인지 판단하는 검토자야.
악플: 특정인·집단을 겨냥한 모욕, 비하, 조롱, 비꼬기·반어, 외모 비하, 위협, 성희롱, 2차 가해, 근거 없는 의혹 제기.
악플 아님: 칭찬·감탄 속 욕(예: 노래 지린다 ㅅㅂ), 혼잣말 감탄(예: 죽는 줄 알았다 이새끼), 자기 비하, 사물·상황에 대한 욕(예: 날씨 시발),
게임·스포츠의 플레이 묘사(예: 상대를 죽여버림, 라인전), 남의 말 인용·신고, 경기력·실력에 대한 예의 있는 비판.
욕이 섞여도 특정인을 깎아내리지 않으면 아님, 욕이 없어도 특정인을 깎아내리면 악플.
각 댓글에 대해 JSON 배열로만 답해: [{"i": 번호, "v": "악플" 또는 "아님", "r": "15자 이내 이유"}]
댓글:
"""


def gem_model(key):
    """무료로 쓸 수 있는 Flash-Lite 계열 모델을 자동 선택 (모델 이름이 바뀌어도 동작)"""
    if st.secrets.get("GEMINI_MODEL"):
        return st.secrets["GEMINI_MODEL"]
    ms = requests.get(GEM + "models", params={"key": key}, timeout=20).json().get("models", [])
    ok = [m["name"] for m in ms if "generateContent" in m.get("supportedGenerationMethods", [])]
    pick = [n for n in ok if "flash-lite" in n] or [n for n in ok if "flash" in n] or ok
    return sorted(pick)[-1]


def gem_review(texts, key):
    """같은 내용은 한 번만, 이미 검토한 내용은 다시 안 보냄(캐시). 50개씩 묶어 요청 1번 → {원문: (악플 여부, 이유)}"""
    cache = st.session_state.setdefault("gcache", {})
    todo = [t for t in dict.fromkeys(texts) if t not in cache]
    model = gem_model(key) if todo else ""
    for i in range(0, len(todo), 50):
        part = [{"text": t} for t in todo[i:i + 50]]
        body = "\n".join(f'{j}. {r["text"][:300]}' for j, r in enumerate(part))
        r = requests.post(f"{GEM}{model}:generateContent", params={"key": key}, timeout=60, json={
            "contents": [{"parts": [{"text": GEM_PROMPT + body}]}],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json"}})
        if r.status_code == 429:
            raise RuntimeError("오늘 Gemini 무료 사용량을 다 썼어요. 내일 다시 시도하세요.")
        if r.status_code != 200:
            raise RuntimeError(r.json().get("error", {}).get("message", "Gemini 오류"))
        txt = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        for x in json.loads(txt[txt.find("["):txt.rfind("]") + 1]):
            if 0 <= int(x["i"]) < len(part):
                cache[part[int(x["i"])]["text"]] = (x.get("v") == "악플", x.get("r", ""))
    return cache


def save(rows, raw, src, url="", vid="직접입력", imgs=()):
    names = [n.strip() for n in st.session_state.get("victim", "").split(",") if n.strip()]
    for r in rows:
        r.update(classify(r["text"]))
        hit = [n for n in names if pat(n).search(r["text"])]
        r["target"] = "✓ " + ", ".join(hit) if hit else ""
    vm = model()
    if vm and rows:
        for r, pr in zip(rows, vm[1].predict_proba(vm[0].transform([r["text"] for r in rows]))[:, 1]):
            r["ai"] = round(pr * 100)
            # 글자 2개 미만이거나 자음·모음 낙서(ㅓ버바펴…)가 더 많은 댓글은 AI 판단 제외 (오탐 방지)
            syl, jamo = len(re.findall("[가-힣]", r["text"])), len(re.findall("[ㄱ-ㅣ]", r["text"]))
            if pr >= AI_CUT and r["label"] == "정상" and syl >= 2 and jamo <= syl:
                r.update(label="악플", severity=2 if pr >= 0.8 else 1, category="AI 판단",
                         reason=f"AI 악플 확률 {pr:.0%}", **law("AI 판단"))
    st.session_state.sel = {r["id"] for r in rows if r["label"] == "악플" and r["severity"] >= 2}
    st.session_state.memo, st.session_state.ver = {}, st.session_state.get("ver", 0) + 1
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
                                       ("② 자동 분류", "키워드 + 학습 AI → 애매한 것만 생성형 AI"),
                                       ("③ 보고서 받기", "선택 → 사건 정보 입력 → PDF 증거 보고서")]):
    col.container(border=True).markdown(f"**{h}**  \n{b}")

st.text_input("피해자 이름·별명 (선택, 쉼표로 여러 개) — 이 이름을 언급한 댓글에 '지목' 표시가 붙어 특정성 입증에 도움돼요",
              key="victim", placeholder="예: 홍길동, 길동이, 홍쌤")
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
    df["when"] = pd.to_datetime(df.time, errors="coerce", utc=True).dt.tz_convert("Asia/Seoul")
    st.divider()
    bad = df.label == "악플"
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("출처", d["src"])
    m2.metric("전체", f"{len(df):,}")
    m3.metric("악플 후보", f"{bad.sum():,}")
    m4.metric("그중 AI가 찾은 것", f"{(df.category == 'AI 판단').sum():,}")
    with st.expander("📊 악플 현황 (유형 · 상습 작성자 · 날짜별 추이)", expanded=True):
        if not bad.any():
            st.caption("악플 후보가 없어요.")
        else:
            g1, g2 = st.columns(2)
            g1.markdown("**유형별 악플 수**")
            g1.bar_chart(df[bad].category.str.split(", ").explode().value_counts(), color="#FF4B4B")
            g2.markdown("**상습 작성자 Top 5** (2건 이상 = 지속성 입증 자료)")
            rep = df[bad & (df.author != "")].author.value_counts().head(5).rename_axis("작성자").reset_index(name="악플 수")
            if len(rep):
                g2.dataframe(rep, hide_index=True)
            else:
                g2.caption("작성자 정보가 없어 집계할 수 없어요.")
            dup = df[df.text.str.len() >= 5].text.value_counts()
            if (dup >= 3).any():
                st.warning("📋 같은 내용 반복 — 도배·조직적 공격 의심: " +
                           ", ".join(f"'{t[:20]}' {n}건" for t, n in dup[dup >= 3].head(3).items()))
            if df.when.notna().any():
                st.markdown("**날짜별 댓글 수 (전체 vs 악플 후보)** — 피해 기간 확인용")
                st.bar_chart(pd.DataFrame({"전체": df.when.dt.date.value_counts(),
                                           "악플 후보": df[bad].when.dt.date.value_counts()}).fillna(0).sort_index(),
                             color=["#C9D1DC", "#FF4B4B"], stack=False)

    # ---------- 2차 재검토 (Gemini) — 사용량 절약: 범위 선택 + 같은 내용 1번만 + 검토한 건 캐시 ----------
    ai_ = df.get("ai", pd.Series(0, index=df.index)).fillna(0)
    doubt = ((df.label == "악플") & ((df.severity == 1) | (ai_ < 50))) | ((df.label == "정상") & ai_.between(40, 64))
    try:
        gkey = st.secrets["GEMINI_API_KEY"]
    except Exception:
        gkey = ""
    with st.expander("🤖 생성형 AI 2차 검토 (Gemini)", expanded=False):
        st.caption("Gemini가 문맥으로 다시 판단해요. 악플이 아니라고 보면 선택이 풀려요 (참고용)")
        a, b, c = st.columns([2.2, 2, 1], vertical_alignment="bottom")
        mode = a.radio("검토 범위", ["애매한 것만 (절약)", "악플 후보 전부 (정밀)"], horizontal=True)
        tgt = df[doubt] if mode.startswith("애매") else df[(df.label == "악플") | doubt]
        texts = list(dict.fromkeys(tgt.sort_values("severity", ascending=False).text))[:200]
        new = [t for t in texts if t not in st.session_state.get("gcache", {})]
        b.caption(f"대상 {len(tgt):,}개 → 중복 제외 {len(texts):,}개, 그중 새로 보낼 것 {len(new):,}개 "
                  f"(요청 약 {-(-len(new) // 50)}회 · 무료 하루 수백 회)")
        agree = d["src"] == "유튜브" or a.checkbox("직접 입력한 내용이 구글(Gemini)로 전송되는 것에 동의해요")
        if c.button("재검토 실행", disabled=not (gkey and texts and agree)):
            try:
                with st.spinner("Gemini가 검토 중…"):
                    res = gem_review(texts, gkey)
                for r in d["rows"]:
                    if r["text"] in res and r["text"] in texts:
                        bad_, why = res[r["text"]]
                        r["gem"] = ("🔴 악플: " if bad_ else "🟢 아님: ") + why
                        if bad_:
                            r.update(label="악플", severity=max(r.get("severity", 0), 2),
                                     category=r.get("category") or "AI 판단", **law(r.get("category") or "AI 판단"))
                            st.session_state.sel.add(r["id"])
                        elif r["label"] == "악플" and r["category"] != "신상노출":
                            r["severity"] = 1
                            st.session_state.sel.discard(r["id"])
                st.session_state.ver += 1
                st.rerun()
            except Exception as e:
                st.error(f"재검토 실패: {e}")
        if not gkey:
            st.caption("GEMINI_API_KEY가 설정되지 않아 사용할 수 없어요.")

    # ---------- 필터 + 선택 (선택은 댓글 ID로 기억 → 필터를 바꿔도 유지) ----------
    f1, f2, f3, f4 = st.columns([1.2, 1.2, 1.6, 1.4])
    scope = f1.radio("범위", ["악플만", "전체 댓글", "선택한 것만"], horizontal=True)
    cats = f2.multiselect("유형", list(RULES) + ["명예훼손", "신상노출", "AI 판단"], placeholder="전체")
    q = f3.text_input("검색어 (쉼표로 여러 개, 변형도 찾음)")
    days = df.when.dropna().dt.date
    rng = f4.date_input("작성 날짜", (days.min(), days.max()), days.min(), days.max()) if len(days) else ()
    sel_ids, memo = st.session_state.sel, st.session_state.memo
    v = {"전체 댓글": df, "악플만": df[bad], "선택한 것만": df[df.id.isin(sel_ids)]}[scope]
    if len(rng) == 2:
        v = v[v.when.dt.date.between(*rng) | v.when.isna()]
    if cats:
        v = v[v["category"].apply(lambda c: any(x in c for x in cats)).astype(bool)]
    words = [w.strip() for w in q.split(",") if w.strip()]
    if words:
        v = v[v["text"].apply(lambda t: any(pat(w).search(t) for w in words)).astype(bool)]
    v = v.sort_values("severity", ascending=False).copy()
    v.insert(0, "포함", v.id.isin(sel_ids))
    v["memo"] = v.id.map(memo).fillna("")
    v["when"] = v.when.dt.strftime("%Y-%m-%d %H:%M").fillna("")
    st.caption(f"{len(v):,}개 표시 · ✅ 현재 선택 {len(sel_ids)}건 · 심각도 1 = 애매함(직접 판단) · 2 = 명백한 모욕 · 3 = 심각")
    cols = ["포함", "severity", "law", "target", "author", "when", "text", "memo", "reason", "ai", "gem", "link"]
    if d["src"] != "유튜브":
        cols.remove("link")
    ed = st.data_editor(v[[c for c in cols if c in v]], hide_index=True, key=f"ed{st.session_state.ver}{scope}{cats}{q}{rng}",
                        disabled=[c for c in cols if c not in ("포함", "memo")],
                        column_config={"severity": "심각도", "law": "법적 검토", "target": "지목", "author": "작성자", "when": "작성 시각(KST)",
                                       "text": st.column_config.TextColumn("내용", width="large"), "memo": "메모(보고서에 들어감)",
                                       "reason": "판단 근거", "ai": "AI 점수(%)", "gem": "생성형 AI 의견",
                                       "link": st.column_config.LinkColumn("원문", display_text="열기")})
    for i, r in ed.iterrows():
        cid = v.at[i, "id"]
        (sel_ids.add if r["포함"] else sel_ids.discard)(cid)
        if r["memo"]:
            memo[cid] = r["memo"]
        else:
            memo.pop(cid, None)
    order = {cid: n for n, cid in enumerate(df.sort_values("time").id)}
    sel = sorted(df[df.id.isin(sel_ids)].to_dict("records"), key=lambda c: order[c["id"]])
    for c in sel:
        c["memo"] = memo.get(c["id"], "")
        if c["label"] == "정상":
            c.update(category="사용자 선택", reason="검토자가 직접 선택", **law("사용자 선택"))

    # ---------- 사건 정보 입력 → 미리보기 → PDF ----------
    sd = sorted(kst(c["time"])[:10] for c in sel if c.get("time"))
    auto = f"{sd[0]} ~ {sd[-1]}" if sd else ""
    box = st.expander(f"📝 증거 보고서 만들기 (선택 {len(sel)}건)", expanded=True)
    k1, k2 = box.columns(2)
    case = dict(title=k1.text_input("사건명", placeholder="미입력 시 '온라인 댓글 관련 증거 정리'"),
                period=k2.text_input("피해 기간 (비우면 선택 댓글 날짜를 참고로 표기)", placeholder=auto or "예: 2026-10-20 ~ 2026-10-27"),
                url=k1.text_input("게시물 URL", value=d["url"]),
                name=k2.text_input("고소인 이름 (선택)"), contact=k2.text_input("연락처 (선택)"),
                story=box.text_area("사건 경위 (직접 작성 · AI가 만들지 않아요)", height=90),
                harm=box.text_area("피해 내용 (직접 작성)", height=90), note=box.text_input("추가 설명 (선택)"), auto=auto)
    with box.popover("📄 보고서 미리보기 (증거일람표)"):
        st.dataframe(pd.DataFrame([dict(번호=f"EV-{i:03d}", 작성자=c["author"] or "미확인", 작성시각=kst(c["time"])[:19] or "미확인",
                                        원문=c["text"], 메모=c["memo"]) for i, c in enumerate(sel, 1)]), hide_index=True)
    c1, c2, c3 = box.columns(3)
    if sel:
        c1.download_button("📄 증거 정리 보고서 PDF 다운로드", report(sel, d, case, len(df)), "EVIDA_증거정리보고서.pdf",
                           "application/pdf", type="primary")
    else:
        c1.button("📄 PDF 다운로드 (증거를 1건 이상 선택하세요)", disabled=True)
    c2.download_button("📊 전체 목록(CSV)", df.to_csv(index=False).encode("utf-8-sig"), f"목록_{d['vid']}.csv")
    c3.download_button("🔒 원본 데이터", d["raw"], f"원본_{d['vid']}." + ("json" if d["src"] == "유튜브" else "txt"))
    st.caption(f"원본 SHA-256: {d['sha']}")
