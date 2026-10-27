"""
악플 수집기 (YouTube)
주소 입력 → 댓글 수집 → 악플 분류 → 채증 자료(Word/Excel/원본 JSON) 다운로드

실행:  streamlit run app.py
"""
import hashlib
import json
import re
from datetime import datetime, timezone, timedelta

import pandas as pd
import requests
import streamlit as st

from evidence import build_evidence_docx, build_excel
from classifier import add_custom, classify_llm, classify_rule, load_custom

KST = timezone(timedelta(hours=9))
YT_API = "https://www.googleapis.com/youtube/v3"


# ---------------------------------------------------------------- 유튜브 ----
def extract_video_id(url: str) -> str | None:
    """youtu.be / watch?v= / shorts / embed / live 주소에서 영상 ID 추출"""
    url = url.strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", url):
        return url
    m = re.search(r"(?:v=|youtu\.be/|shorts/|embed/|live/)([A-Za-z0-9_-]{11})", url)
    return m.group(1) if m else None


def fetch_video_info(video_id: str, api_key: str) -> dict:
    r = requests.get(f"{YT_API}/videos", params={
        "part": "snippet,statistics", "id": video_id, "key": api_key}, timeout=20)
    r.raise_for_status()
    items = r.json().get("items", [])
    if not items:
        raise ValueError("영상을 찾을 수 없어요. 주소를 확인하거나 비공개 영상인지 확인하세요.")
    sn, stt = items[0]["snippet"], items[0].get("statistics", {})
    return {
        "video_id": video_id,
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "title": sn.get("title", ""),
        "channel": sn.get("channelTitle", ""),
        "published": sn.get("publishedAt", ""),
        "comment_count": stt.get("commentCount", "?"),
    }


def _row(c: dict, video_id: str, is_reply: bool, parent_id: str = "") -> dict:
    sn = c["snippet"]
    return {
        "comment_id": c["id"],
        "parent_id": parent_id,
        "is_reply": is_reply,
        "author": sn.get("authorDisplayName", ""),
        "author_channel": sn.get("authorChannelUrl", ""),
        "text": sn.get("textOriginal", ""),
        "likes": sn.get("likeCount", 0),
        "published": sn.get("publishedAt", ""),
        "updated": sn.get("updatedAt", ""),
        "link": f"https://www.youtube.com/watch?v={video_id}&lc={c['id']}",
    }


def fetch_comments(video_id: str, api_key: str, max_comments: int,
                   include_replies: bool, progress=None) -> tuple[list[dict], list[dict]]:
    """댓글 수집. (정리된 행 목록, API 원본 응답 목록)을 반환"""
    rows, raw_pages, token = [], [], None
    while len(rows) < max_comments:
        params = {"part": "snippet,replies", "videoId": video_id, "maxResults": 100,
                  "textFormat": "plainText", "order": "time", "key": api_key}
        if token:
            params["pageToken"] = token
        r = requests.get(f"{YT_API}/commentThreads", params=params, timeout=20)
        if r.status_code == 403:
            reason = r.json().get("error", {}).get("errors", [{}])[0].get("reason", "")
            if reason == "commentsDisabled":
                raise ValueError("이 영상은 댓글이 꺼져 있어요.")
            raise ValueError(f"API 접근 거부: {reason or r.text[:200]}")
        r.raise_for_status()
        data = r.json()
        raw_pages.append(data)

        for th in data.get("items", []):
            top = th["snippet"]["topLevelComment"]
            rows.append(_row(top, video_id, False))
            if include_replies and th["snippet"].get("totalReplyCount", 0):
                rows.extend(_fetch_replies(top["id"], video_id, api_key, raw_pages,
                                           th.get("replies", {}).get("comments", []),
                                           th["snippet"]["totalReplyCount"]))
        if progress:
            progress(min(len(rows) / max_comments, 1.0), f"{len(rows)}개 수집 중…")
        token = data.get("nextPageToken")
        if not token:
            break
    return rows[:max_comments], raw_pages


def _fetch_replies(parent_id, video_id, api_key, raw_pages, inline, total):
    # 답글이 5개 이하면 commentThreads 응답에 다 들어있음
    if len(inline) >= total:
        return [_row(c, video_id, True, parent_id) for c in inline]
    out, token = [], None
    while True:
        params = {"part": "snippet", "parentId": parent_id, "maxResults": 100,
                  "textFormat": "plainText", "key": api_key}
        if token:
            params["pageToken"] = token
        r = requests.get(f"{YT_API}/comments", params=params, timeout=20)
        r.raise_for_status()
        data = r.json()
        raw_pages.append(data)
        out.extend(_row(c, video_id, True, parent_id) for c in data.get("items", []))
        token = data.get("nextPageToken")
        if not token:
            return out


def secret(name: str) -> str:
    try:
        return st.secrets.get(name, "")
    except Exception:  # noqa: BLE001  secrets.toml 없으면 빈 값
        return ""


# ---------------------------------------------------------------- 화면 ------
st.set_page_config(page_title="악플 수집기", page_icon="🛡️", layout="wide")
st.title("🛡️ 악플 수집기")
st.caption("유튜브 주소를 넣으면 댓글을 모아 악플을 골라내고, 채증 자료로 정리합니다.")

with st.sidebar:
    st.subheader("설정")
    # 서버(Secrets)에 키가 있으면 입력칸을 숨김 → 사용자는 주소만 넣으면 됨
    yt_key = secret("YOUTUBE_API_KEY") or st.text_input("YouTube Data API 키", type="password")
    mode = st.radio("분류 방식", ["키워드 (무료·빠름)", "AI (Claude, 정확·유료)"])
    claude_key = ""
    if mode.startswith("AI"):
        claude_key = secret("ANTHROPIC_API_KEY") or st.text_input("Anthropic API 키", type="password")
    max_c = st.slider("최대 수집 댓글 수", 100, 5000, 1000, step=100)
    replies = st.checkbox("답글(대댓글)까지 수집", value=True)
    st.divider()
    victim = st.text_input("피해자(고소인) 이름 · 선택", help="채증 문서 표지에 들어갑니다.")
    collector = st.text_input("수집자 이름 · 선택")

url = st.text_input("유튜브 영상 주소", placeholder="https://youtu.be/...")
go = st.button("수집 시작", type="primary", use_container_width=True)

if go:
    vid = extract_video_id(url)
    if not vid:
        st.error("유튜브 주소 형식이 아니에요.")
        st.stop()
    if not yt_key:
        st.error("사이드바에 YouTube API 키를 넣어주세요.")
        st.stop()
    try:
        bar = st.progress(0.0, "영상 정보 확인 중…")
        info = fetch_video_info(vid, yt_key)
        rows, raw = fetch_comments(vid, yt_key, max_c, replies,
                                   progress=lambda p, t: bar.progress(p, t))
        collected_at = datetime.now(KST)

        bar.progress(1.0, "악플 분류 중…")
        if mode.startswith("AI"):
            if not claude_key:
                st.error("AI 분류를 쓰려면 Anthropic API 키가 필요해요.")
                st.stop()
            labels = classify_llm(rows, claude_key,
                                  progress=lambda p, t: bar.progress(p, t))
        else:
            labels = classify_rule(rows)
        for r_ in rows:
            r_.update(labels.get(r_["comment_id"], {"label": "정상", "category": "", "severity": 0, "reason": ""}))
        bar.empty()

        raw_bytes = json.dumps({"video": info, "collected_at": collected_at.isoformat(),
                                "api_responses": raw}, ensure_ascii=False, indent=1).encode("utf-8")
        st.session_state.update(
            info=info, rows=rows, raw_bytes=raw_bytes,
            raw_hash=hashlib.sha256(raw_bytes).hexdigest(),
            collected_at=collected_at, method=mode)
    except Exception as e:  # noqa: BLE001
        st.error(f"오류: {e}")
        st.stop()

if "rows" in st.session_state:
    info, rows = st.session_state.info, st.session_state.rows
    df = pd.DataFrame(rows)

    st.subheader(info["title"])
    st.caption(f'{info["channel"]} · 수집 {st.session_state.collected_at:%Y-%m-%d %H:%M} KST')
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("수집 댓글", len(df))
    c2.metric("악플", int((df.label == "악플").sum()))
    c3.metric("비판(악플 아님)", int((df.label == "비판").sum()))
    c4.metric("정상", int((df.label == "정상").sum()))

    st.markdown("**악플 후보 검토** — 증거에 넣을 댓글만 체크된 상태로 두세요.")
    bad = df[df.label == "악플"].copy().sort_values("severity", ascending=False)
    bad.insert(0, "포함", True)
    edited = st.data_editor(
        bad[["포함", "severity", "category", "author", "text", "reason", "published", "link"]],
        column_config={
            "포함": st.column_config.CheckboxColumn(),
            "severity": st.column_config.NumberColumn("심각도", help="1 낮음 · 3 높음"),
            "category": "유형", "author": "작성자", "text": st.column_config.TextColumn("댓글", width="large"),
            "reason": "판단 근거", "published": "작성 시각(UTC)",
            "link": st.column_config.LinkColumn("원문 링크", display_text="열기"),
        },
        hide_index=True, use_container_width=True, key="editor")

    with st.expander("악플로 분류되지 않은 댓글 보기 (놓친 악플이 있으면 여기서 확인)"):
        rest = df[df.label != "악플"][["label", "author", "text", "link"]]
        add = st.multiselect("추가로 증거에 넣을 댓글",
                             options=rest.index.tolist(),
                             format_func=lambda i: f'{df.at[i, "author"]}: {df.at[i, "text"][:50]}')
        st.dataframe(rest, hide_index=True, use_container_width=True,
                     column_config={"link": st.column_config.LinkColumn(display_text="열기")})

        st.markdown("**새 우회 표현을 사전에 등록** — 다음 수집부터 자동으로 잡아요. "
                    "띄어쓰기·숫자·기호 끼우기, 모음 바꾸기 변형까지 같이 잡힙니다.")
        w1, w2, w3 = st.columns([3, 2, 1])
        new_word = w1.text_input("표현 (예: 니유미)", label_visibility="collapsed",
                                 placeholder="표현 입력 (예: 니유미)")
        new_cat = w2.selectbox("유형", ["욕설", "패드립", "인신공격", "외모비하", "혐오", "성적", "위협", "조롱"],
                               label_visibility="collapsed")
        if w3.button("등록", use_container_width=True) and new_word.strip():
            add_custom(new_word, new_cat)
            # 지금 결과에도 바로 반영 (정상/비판 → 악플로만 올림)
            for cid, v in classify_rule(st.session_state.rows).items():
                for r_ in st.session_state.rows:
                    if r_["comment_id"] == cid and r_["label"] != "악플":
                        r_.update(v)
            st.rerun()
        custom = load_custom()
        if custom:
            st.caption("등록된 표현: " + " · ".join(f"{w}({c})" for c, ws in custom.items() for w in ws))

    chosen_idx = list(edited[edited["포함"]].index) + list(add)
    chosen = df.loc[chosen_idx].to_dict("records")
    for c in chosen:
        if c["label"] != "악플":
            c.update(label="악플", category=c.get("category") or "수동 추가",
                     reason=c.get("reason") or "검토자가 직접 선택")

    st.divider()
    st.markdown(f"**채증 자료 만들기** — 선택된 댓글 {len(chosen)}개")
    meta = dict(info=info, collected_at=st.session_state.collected_at,
                method=st.session_state.method, raw_hash=st.session_state.raw_hash,
                total=len(df), victim=victim, collector=collector)
    d1, d2, d3 = st.columns(3)
    stamp = f"{st.session_state.collected_at:%Y%m%d_%H%M}"
    d1.download_button("📄 채증 보고서 (Word)", build_evidence_docx(chosen, meta),
                       f"악플채증_{info['video_id']}_{stamp}.docx", use_container_width=True,
                       disabled=not chosen)
    d2.download_button("📊 전체 댓글 + 분류 (Excel)", build_excel(df, chosen, meta),
                       f"댓글분류_{info['video_id']}_{stamp}.xlsx", use_container_width=True)
    d3.download_button("🔒 API 원본 데이터 (JSON)", st.session_state.raw_bytes,
                       f"원본_{info['video_id']}_{stamp}.json", use_container_width=True)
    st.caption(f"원본 JSON SHA-256: `{st.session_state.raw_hash}` — 보고서에도 같은 값이 기록돼 위·변조 여부를 확인할 수 있어요.")
