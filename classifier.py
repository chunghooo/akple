"""악플 분류: 키워드 방식(무료) / Claude API 방식(정확)"""
import json
import re
from pathlib import Path

import requests

from normalize import deobfuscate, phonetic

# ------------------------------------------------------------ 키워드 방식 ----
# 변형 표기(자음, 띄어쓰기, 숫자 섞기)를 어느 정도 잡도록 정규식으로 작성.
# 프로젝트에서 계속 보강하세요.
RULES = {
    "욕설": (3, [r"시\s*[0-9]*\s*발", r"씨\s*[0-9]*\s*발", r"ㅅ\s*ㅂ", r"ㅆ\s*ㅂ", r"좆", r"ㅈ\s*같",
                 r"개\s*새\s*(끼|기|꺄|퀴)", r"개\s*색\s*(기|히)", r"ㄱ\s*ㅅ\s*ㄲ", r"새\s*끼", r"색\s*기",
                 r"병\s*신", r"ㅂ\s*ㅅ", r"븅\s*신", r"지\s*랄", r"ㅈ\s*ㄹ", r"염\s*병", r"썅", r"엠\s*창",
                 r"느\s*금", r"니\s*애\s*미", r"애\s*미", r"애\s*비"]),
    "비속어": (1, [r"존\s*나", r"졸\s*라", r"ㅈ\s*ㄴ"]),
    "위협": (3, [r"죽\s*어\s*라", r"뒤\s*져", r"뒤\s*지", r"자\s*살\s*해", r"죽\s*여\s*버", r"찾\s*아\s*간\s*다",
                 r"칼\s*로\s*(찌|쑤)", r"패\s*버"]),
    "인신공격": (2, [r"미\s*친\s*(놈|년|새|것)", r"또\s*라\s*이", r"돌\s*아\s*이", r"멍\s*청", r"찐\s*따",
                     r"한\s*심", r"쓰\s*레\s*기", r"추\s*하", r"못\s*생", r"돼\s*지", r"정\s*신\s*병",
                     r"정\s*병", r"관\s*종", r"역\s*겹", r"꺼\s*져", r"닥\s*쳐", r"ㄲ\s*ㅈ", r"ㄷ\s*ㅊ"]),
    "혐오": (3, [r"한남(?![자쪽동대산부])", r"한녀", r"김\s*치\s*녀", r"틀\s*딱", r"급\s*식\s*충", r"맘\s*충",
                 r"짱\s*깨", r"쪽\s*바\s*리", r"흑\s*형", r"장\s*애\s*인\s*같", r"게\s*이\s*새"]),
    "성적": (3, [r"따\s*먹", r"보\s*지(?!\s*[마도는않를만못])", r"자\s*지(?!\s*[마도는않를만못])", r"몸\s*매\s*보",
                 r"벗\s*어\s*(봐|줘|라)"]),
}
# 글자 사이에 끼워 넣는 군더더기(띄어쓰기·숫자·기호·ㅇ·ㅋ·ㅎ)를 건너뛰도록 구분자 확장
#   병1신, 시.발, 시ㅇㅇ발, 씨ㅋㅋ발 → 모두 매칭
_SEP = r"[\s\d._*~!^♡♥☆★,·ㅇㅋㅎㅡ-]*"


def _compile(pattern: str) -> re.Pattern:
    return re.compile(pattern.replace(r"\s*", _SEP))


_COMPILED = {cat: (sev, [_compile(p) for p in pats]) for cat, (sev, pats) in RULES.items()}

# 발음 정규화 비교용 핵심 욕설 (씌발·쉬발·씨빨·븅씬 등 모음/된소리 바꾸기 대응)
#   정규화하면 무해한 단어와 겹칠 수 있어서 확실한 단어만 넣음
PHONETIC_CORE = ["시발", "병신", "븅신", "지랄", "염병", "개새끼", "좆같", "니애미", "엠창"]
_PHON = [(w, _compile(r"\s*".join(phonetic(w)))) for w in PHONETIC_CORE]

# ------------------------------------------------------------ 사용자 사전 ---
# 검토자가 앱에서 추가한 신조어 우회 표현이 여기 쌓임
CUSTOM_PATH = Path(__file__).with_name("custom_words.json")


def load_custom() -> dict:
    try:
        return json.loads(CUSTOM_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def add_custom(word: str, category: str) -> None:
    data = load_custom()
    words = data.setdefault(category, [])
    word = re.sub(r"\s+", "", word)
    if word and word not in words:
        words.append(word)
    CUSTOM_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def _custom_compiled():
    out = []
    for cat, words in load_custom().items():
        for w in words:
            pat = r"\s*".join(re.escape(ch) for ch in w)
            out.append((cat, w, _compile(pat), _compile(r"\s*".join(re.escape(ch) for ch in phonetic(w)))))
    return out


def classify_rule(rows: list[dict]) -> dict:
    custom = _custom_compiled()
    out = {}
    for r in rows:
        raw = r["text"]
        deob = deobfuscate(raw)          # 영타·로마자 복원
        phon = phonetic(deob)            # 발음 정규화
        hits = []   # (심각도, 유형, 근거)

        for cat, (sev, pats) in _COMPILED.items():
            for p in pats:
                m = p.search(raw)
                if m:
                    hits.append((sev, cat, f"키워드 '{m.group(0)}'"))
                    break
                if deob != raw and (m := p.search(deob)):
                    hits.append((sev, cat, f"우회 표기 복원 '{m.group(0)}'"))
                    break

        if not any(h[1] == "욕설" for h in hits):
            for word, p in _PHON:
                if p.search(phon):
                    hits.append((3, "욕설", f"발음 변형 → '{word}'"))
                    break

        for cat, word, p, pp in custom:
            if p.search(raw) or p.search(deob) or pp.search(phon):
                hits.append((2, cat, f"사용자 사전 '{word}'"))

        if hits:
            hits.sort(key=lambda h: -h[0])
            out[r["comment_id"]] = {
                "label": "악플", "severity": hits[0][0],
                "category": ", ".join(dict.fromkeys(h[1] for h in hits)),
                "reason": ", ".join(dict.fromkeys(h[2] for h in hits)),
            }
    return out


# ------------------------------------------------------------ AI 방식 -------
MODEL = "claude-haiku-5-5"
PROMPT = """너는 한국어 온라인 댓글을 검토하는 모더레이터야. 아래 유튜브 댓글들을 하나씩 분류해.

label:
- "악플": 욕설, 인신공격, 외모·가족 비하, 혐오표현, 성희롱, 위협, 허위사실로 명예훼손, 조롱·비꼬기로 특정인을 깎아내림
- "비판": 내용·행동에 대한 비판이지만 모욕 없이 의견을 말함 (악플 아님)
- "정상": 그 외

category (악플일 때만, 여러 개면 쉼표): 욕설, 인신공격, 외모비하, 패드립, 혐오, 성적, 위협, 명예훼손, 조롱
severity (악플일 때만): 1 가벼움 / 2 명백한 모욕 / 3 심각(위협·성적·혐오·허위사실)
reason: 한 문장, 왜 그렇게 판단했는지

작성자들은 필터를 피하려고 표기를 비틀어. 글자가 아니라 "읽는 사람이 무슨 뜻으로 받아들이나"로 판단해:
- 군더더기 끼우기: 시ㅇㅇbal, 병1신, 씨ㅋㅋ발, 시.발
- 영타로 치기: tlqkf(시발), qudtls(병신)  /  로마자: sibal, c bal
- 모음·된소리 바꾸기: 씌발, 쉬발, 븅씬
- 발음 비틀기 + 덕담 위장: "니유미만수무강"은 '니 애미'를 비튼 패드립을 축복처럼 포장한 것 → 악플(패드립)
- 칭찬·존댓말로 위장한 조롱: "얼굴 보니 마음이 편해지네요 ㅎㅎ 저보다 못생긴 사람도 있구나" → 악플(외모비하)
- 초성·은어·밈으로 돌려 말하기, 특정 집단 멸칭의 변형
"hint" 필드가 있으면 영타·로마자를 한글로 복원한 결과니 참고해.
반대로 단순히 거친 말투라도 특정인을 겨냥하지 않으면("존나 웃기네") 악플이 아닐 수 있어.

JSON 배열로만 답해. 예:
[{"id":"…","label":"악플","category":"욕설, 인신공격","severity":2,"reason":"…"}]

댓글:
"""


def _call_claude(batch, api_key):
    items = []
    for r in batch:
        x = {"id": r["comment_id"], "text": r["text"][:800]}
        hint = deobfuscate(x["text"])
        if hint != x["text"]:
            x["hint"] = hint
        items.append(json.dumps(x, ensure_ascii=False))
    payload = "\n".join(items)
    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": api_key, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
        json={"model": MODEL, "max_tokens": 8000,
              "messages": [{"role": "user", "content": PROMPT + payload}]},
        timeout=120)
    resp.raise_for_status()
    text = "".join(b.get("text", "") for b in resp.json()["content"])
    m = re.search(r"\[.*\]", text, re.S)
    return json.loads(m.group(0)) if m else []


def classify_llm(rows: list[dict], api_key: str, batch_size: int = 40, progress=None) -> dict:
    rule_hits = classify_rule(rows)   # 키워드·사용자 사전 결과도 같이 반영
    out = {}
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        try:
            results = _call_claude(batch, api_key)
        except Exception:  # noqa: BLE001  한 묶음 실패 시 키워드 방식으로 대체
            out.update(classify_rule(batch))
            continue
        for x in results:
            if x.get("label") in ("악플", "비판"):
                out[x["id"]] = {"label": x["label"], "category": x.get("category", ""),
                                "severity": int(x.get("severity") or 0), "reason": x.get("reason", "")}
        if progress:
            progress(min((i + batch_size) / len(rows), 1.0), f"AI 분류 중… {min(i + batch_size, len(rows))}/{len(rows)}")
    # AI가 놓쳤지만 규칙·사용자 사전에 걸린 댓글은 악플 후보로 올려서 사람이 보게 함
    for cid, v in rule_hits.items():
        if out.get(cid, {}).get("label") != "악플":
            out[cid] = {**v, "reason": v["reason"] + " (AI는 악플 아님으로 판단 — 검토 필요)"}
    return out
