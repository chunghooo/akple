"""
우회 표기 복원
  1) 영타 → 한글   : tlqkf → 시발, qudtls → 병신
  2) 로마자 → 한글 : sibal → 시발, ssibal → 씨발, byungsin → 병신
  3) 발음 정규화   : 씌발·쉬발·씨빨 → 시발 (된소리→예사소리, 비슷한 모음 통일)
  ※ 끼워 넣은 숫자·기호·ㅇ·ㅋ 같은 군더더기는 classifier 의 구분자 규칙이 건너뜀
"""
import re

# ------------------------------------------------------------ 한글 조합 -----
CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
JUNG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
JONG = ["", "ㄱ", "ㄲ", "ㄳ", "ㄴ", "ㄵ", "ㄶ", "ㄷ", "ㄹ", "ㄺ", "ㄻ", "ㄼ", "ㄽ", "ㄾ", "ㄿ", "ㅀ",
        "ㅁ", "ㅂ", "ㅄ", "ㅅ", "ㅆ", "ㅇ", "ㅈ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ"]
V_COMB = {("ㅗ", "ㅏ"): "ㅘ", ("ㅗ", "ㅐ"): "ㅙ", ("ㅗ", "ㅣ"): "ㅚ", ("ㅜ", "ㅓ"): "ㅝ",
          ("ㅜ", "ㅔ"): "ㅞ", ("ㅜ", "ㅣ"): "ㅟ", ("ㅡ", "ㅣ"): "ㅢ"}
C_COMB = {("ㄱ", "ㅅ"): "ㄳ", ("ㄴ", "ㅈ"): "ㄵ", ("ㄴ", "ㅎ"): "ㄶ", ("ㄹ", "ㄱ"): "ㄺ", ("ㄹ", "ㅁ"): "ㄻ",
          ("ㄹ", "ㅂ"): "ㄼ", ("ㄹ", "ㅅ"): "ㄽ", ("ㄹ", "ㅌ"): "ㄾ", ("ㄹ", "ㅍ"): "ㄿ", ("ㄹ", "ㅎ"): "ㅀ",
          ("ㅂ", "ㅅ"): "ㅄ"}
C_SPLIT = {v: k for k, v in C_COMB.items()}


def _syl(c, v, j=""):
    return chr(0xAC00 + (CHO.index(c) * 21 + JUNG.index(v)) * 28 + JONG.index(j))


def compose(jamos: list[str]) -> str:
    """두벌식 자판으로 친 자모 나열을 글자로 조립"""
    out, c, v, j = [], None, None, None

    def flush():
        nonlocal c, v, j
        if c and v:
            out.append(_syl(c, v, j or ""))
        else:
            out.extend(x for x in (c, v) if x)
        c = v = j = None

    for x in jamos:
        if x in JUNG:
            if c and v is None:
                v = x
            elif c and v and j is None and (v, x) in V_COMB:
                v = V_COMB[(v, x)]
            elif c and v and j:  # 받침이 다음 글자 초성으로 넘어감
                if j in C_SPLIT:
                    j1, j2 = C_SPLIT[j]
                    j = j1
                    flush()
                    c = j2
                else:
                    nc, j = j, None
                    flush()
                    c = nc
                v = x
            else:
                flush()
                out.append(x)
        else:  # 자음
            if c is None:
                c = x
            elif v is None:
                flush()
                c = x
            elif j is None and x in JONG:
                j = x
            elif j and (j, x) in C_COMB:
                j = C_COMB[(j, x)]
            else:
                flush()
                c = x
    flush()
    return "".join(out)


# ------------------------------------------------------------ 1) 영타 -------
KEYMAP = dict(zip("qwertasdfgzxcvyuiophjklbnm",
                  "ㅂㅈㄷㄱㅅㅁㄴㅇㄹㅎㅋㅌㅊㅍㅛㅕㅑㅐㅔㅗㅓㅏㅣㅠㅜㅡ"))
KEYMAP.update({"Q": "ㅃ", "W": "ㅉ", "E": "ㄸ", "R": "ㄲ", "T": "ㅆ", "O": "ㅒ", "P": "ㅖ"})


def eng_to_kor(word: str) -> str:
    jamos = []
    for ch in word:
        k = KEYMAP.get(ch) or KEYMAP.get(ch.lower())
        if not k:
            return word
        jamos.append(k)
    return compose(jamos)


# ------------------------------------------------------------ 2) 로마자 -----
ROMAN = {
    "ssi": "씨", "shi": "시", "si": "시", "c": "시", "ssy": "씨",
    "bal": "발", "bbal": "빨", "pal": "팔", "ppal": "빨",
    "byung": "병", "byeong": "병", "byeng": "병", "shin": "신", "sin": "신",
    "gae": "개", "kae": "개", "sae": "새", "sse": "쌔", "kki": "끼", "ggi": "끼", "ki": "기",
    "ji": "지", "ral": "랄", "rral": "랄", "jot": "좆", "jon": "존", "na": "나",
    "nie": "니애", "ni": "니", "ae": "애", "mi": "미", "em": "엠", "chang": "창",
    "dak": "닥", "chyeo": "쳐", "chyo": "쳐", "kkeo": "꺼", "jyeo": "져", "jyo": "져",
    "michin": "미친",
}
_ROMAN_KEYS = sorted(ROMAN, key=len, reverse=True)


def roman_to_kor(word: str) -> str:
    """단어 전체가 사전 조각으로만 이뤄질 때만 변환 (영어 단어 오변환 방지)"""
    w, out, i = word.lower(), [], 0
    while i < len(w):
        for k in _ROMAN_KEYS:
            if w.startswith(k, i):
                out.append(ROMAN[k])
                i += len(k)
                break
        else:
            return word
    return "".join(out)


# ------------------------------------------------------------ 3) 발음 -------
TENSE = {"ㄲ": "ㄱ", "ㄸ": "ㄷ", "ㅃ": "ㅂ", "ㅆ": "ㅅ", "ㅉ": "ㅈ", "ㅍ": "ㅂ"}
VOWEL = {"ㅢ": "ㅣ", "ㅟ": "ㅣ", "ㅐ": "ㅔ", "ㅒ": "ㅖ", "ㅙ": "ㅔ", "ㅞ": "ㅔ", "ㅚ": "ㅔ",
         "ㅑ": "ㅏ", "ㅘ": "ㅏ", "ㅕ": "ㅓ", "ㅝ": "ㅓ", "ㅛ": "ㅗ", "ㅠ": "ㅜ"}


def phonetic(text: str) -> str:
    out = []
    for ch in text:
        code = ord(ch) - 0xAC00
        if 0 <= code < 11172:
            c, v, j = CHO[code // 588], JUNG[(code % 588) // 28], JONG[code % 28]
            out.append(_syl(TENSE.get(c, c), VOWEL.get(v, v), j))
        else:
            out.append(TENSE.get(ch, ch))
    return "".join(out)


# ------------------------------------------------------------ 종합 ----------
_ASCII_RUN = re.compile(r"[A-Za-z]+")


def deobfuscate(text: str) -> str:
    """영문 덩어리를 로마자 → 영타 순으로 한글 복원 (복원 안 되면 그대로)"""
    def repl(m):
        s = m.group(0)
        r = roman_to_kor(s)
        if r != s:
            return r
        r = eng_to_kor(s)
        return r if sum("가" <= ch <= "힣" for ch in r) >= 2 else s
    return _ASCII_RUN.sub(repl, text)
