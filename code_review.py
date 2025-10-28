import os
import sys
import textwrap
import json
import time
import requests
from typing import List, Tuple, Iterator, Optional
 
# ====== 환경설정 ======
GITHUB_API = "https://api.github.com"

def getenv_any(*names):
    for n in names:
        v = os.getenv(n)
        if v:
            return v
    return None

GITHUB_TOKEN = getenv_any("GITHUB_TOKEN", "INPUT_GITHUB_TOKEN")
OPENAI_KEY   = getenv_any("OPENAI_KEY", "INPUT_OPENAI_KEY")
OPENAI_MODEL = getenv_any("OPENAI_MODEL", "INPUT_OPENAI_MODEL") or "gpt-5-mini"
 
if not GITHUB_TOKEN:
    print("ERROR: GITHUB_TOKEN env is required")
    sys.exit(1)
 
if not OPENAI_KEY:
    print("ERROR: OPENAI_KEY env is required")
    sys.exit(1)
# =====================

HEADERS = {
    "Accept": "application/vnd.github+json",
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "X-GitHub-Api-Version": "2022-11-28",
}
 
# ====== 사용자 파라미터 ======
event_path = os.getenv("GITHUB_EVENT_PATH")

with open(event_path, "r") as f:
    event = json.load(f)

OWNER = event["repository"]["owner"]["login"]
REPO = event["repository"]["name"]
PR_NUMBER = event["pull_request"]["number"]
 
# 과도한 코멘트 방지: 파일별 최대 단락 수 (0이면 제한 없음)
MAX_PARAGRAPHS_PER_FILE = 0
 
# 단락 프롬프트 컨텍스트: 앞/뒤로 몇 줄씩 붙여줄지 (diff 기준, 접두사 제거 전 기준)
CONTEXT_BEFORE = 2
CONTEXT_AFTER = 2
 
# OpenAI 프롬프트 정책
MAX_SNIPPET_CHARS = 2000  # 단락+컨텍스트 최대 길이 (토큰 폭주 방지)
SYSTEM_PROMPT = (
    "You are a senior code reviewer. Provide concise, actionable review comments "
    "for each code change. Prefer specific suggestions, edge cases, bug risks, "
    "readability, security, and performance. Use bullet points when helpful. "
    "Answer in Korean.\n\n"
    "IMPORTANT:\n"
    "- You will only see partial code snippets, not complete files.\n"
    "- NEVER comment on missing imports, undefined symbols, or external context.\n"
    "- ONLY review what is visible inside the provided snippet.\n"
)
 
USER_PROMPT_TEMPLATE = """\
You are given a partial code snippet (not a full file).
Review ONLY the code between <snippet> and </snippet>.
 
<snippet>
{code}
</snippet>
"""
 
def _extract_text_from_responses_api(data: dict) -> str | None:
    # 1) 편의 필드
    if isinstance(data, dict) and data.get("output_text"):
        return data["output_text"].strip()

    # 2) 일반 구조: data["output"] -> [ { "content": [ { "type": "output_text", "text": "..." }, ... ] }, ... ]
    out = []
    for item in data.get("output", []) or []:
        for c in item.get("content", []) or []:
            # 주로 type == "output_text"
            t = c.get("text")
            if isinstance(t, str) and t.strip():
                out.append(t)
    if out:
        return "\n".join(out).strip()

    # 3) 혹시 서버가 예전 chat 스타일로 응답한 경우 대비(방어적)
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        msg = choices[0].get("message", {})
        if isinstance(msg, dict) and isinstance(msg.get("content"), str):
            return msg["content"].strip()

    return None

def call_openai_review(text: str) -> str:
    """
    OpenAI Responses API 호출 (gpt-5-mini 권장)
    - 환경변수 OPENAI_KEY 필요
    - 모델명: OPENAI_MODEL (기본: gpt-5-mini)
    - temperature 미지원 → 포함하지 않음
    - 429/5xx 재시도
    """
    api_key = OPENAI_KEY
    if not api_key:
        return "OPENAI_KEY 환경변수가 필요합니다."

    model = OPENAI_MODEL
    url = "https://api.openai.com/v1/responses"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "instructions": SYSTEM_PROMPT,
        "input": text
    }

    last_err = "unknown error"
    for attempt in range(3):
        try:
            resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=60)
            # 429/5xx 재시도
            if resp.status_code in (429, 500, 502, 503, 504):
                time.sleep(1.0 * (attempt + 1))
                continue

            # 4xx 에러는 본문을 그대로 반환해 디버깅에 도움 주자
            if resp.status_code >= 400:
                return f"AI 호출 실패 [{resp.status_code}]: {resp.text}"

            data = resp.json()
            text_out = _extract_text_from_responses_api(data)
            if text_out:
                return text_out

            # 예상치 못한 스키마면 raw 응답을 노출
            return f"AI 호출 실패: 예상치 못한 응답 형식\n{json.dumps(data, ensure_ascii=False)[:2000]}"
        except Exception as e:
            last_err = str(e)
            time.sleep(0.5 * (attempt + 1))

    return f"AI 호출 실패: {last_err}"
 
# ====== GitHub API ======
def get_pr(owner: str, repo: str, pr_number: int) -> dict:
    r = requests.get(f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{pr_number}",
                     headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()
 
def list_reviews(owner: str, repo: str, pr_number: int) -> List[dict]:
    r = requests.get(f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{pr_number}/reviews",
                     headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()
 
def submit_review(owner: str, repo: str, pr_number: int, review_id: int, body: str = "") -> dict:
    url = f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{pr_number}/reviews/{review_id}/events"
    payload = {"event": "COMMENT"}
    if body:
        payload["body"] = body
    r = requests.post(url, headers=HEADERS, json=payload, timeout=30)
    r.raise_for_status()
    return r.json()
 
def ensure_no_pending_review(owner: str, repo: str, pr_number: int):
    """사용자 기준 PENDING 리뷰가 있으면 먼저 제출해 제한 회피"""
    for rv in list_reviews(owner, repo, pr_number):
        if rv.get("state") == "PENDING":
            try:
                submit_review(owner, repo, pr_number, rv["id"], body="자동 제출(기존 pending 정리).")
                print(f"Pending review {rv['id']} submitted.")
            except requests.HTTPError as e:
                print("Pending review submit failed:", e)
 
def get_pr_files(owner: str, repo: str, pr_number: int) -> List[dict]:
    url = f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{pr_number}/files"
    out = []
    page = 1
    while True:
        r = requests.get(url, headers=HEADERS, params={"page": page, "per_page": 100}, timeout=30)
        r.raise_for_status()
        chunk = r.json()
        out.extend(chunk)
        if len(chunk) < 100:
            break
        page += 1
    return out
 
# ====== Diff 파싱 ======
def parse_hunk_header(header_line: str) -> Tuple[int, int]:
    # @@ -l[,n] +r[,n] @@ 형태에서 시작줄만 파싱
    header = header_line.strip('@ ').split(' ')
    lstart = int(header[0].split(',')[0].lstrip('-'))
    rstart = int(header[1].split(',')[0].lstrip('+'))
    return lstart, rstart
 
def iter_paragraphs_with_context(patch: str) -> Iterator[dict]:
    """
    파일 하나의 unified diff에서 연속된 '+' 또는 '-' 묶음을 '단락'으로 산출.
    각 단락에 대해:
      - kind: "add" / "del"
      - end_side: "RIGHT" / "LEFT" (끝줄 코멘트 좌표용)
      - end_line: int
      - snippet: 컨텍스트 포함된 텍스트 (접두사 제거 후)
      - path 내부에서의 헌크별 상대 컨텍스트만 사용
    """
    left_line: Optional[int] = None
    right_line: Optional[int] = None
 
    # 헌크 베이스 버퍼(접두사와 원문 함께 보관하여 컨텍스트 뽑을 때 라인 접근)
    hunk_lines: List[str] = []   # 원본 diff 라인
    hunk_left_start = hunk_right_start = None
 
    # 진행 중 블록 상태
    blk_kind: Optional[str] = None  # 'add' or 'del'
    blk_lines_idx: List[int] = []   # hunk_lines 내 인덱스 모음
    blk_last_left = blk_last_right = None
 
    def flush_block():
        nonlocal blk_kind, blk_lines_idx, blk_last_left, blk_last_right
        if not blk_kind or not blk_lines_idx:
            blk_kind = None
            blk_lines_idx = []
            blk_last_left = blk_last_right = None
            return None
 
        # 단락 끝줄 좌표
        if blk_kind == "add":
            end_side = "RIGHT"
            end_line = blk_last_right
        else:
            end_side = "LEFT"
            end_line = blk_last_left
 
        # 컨텍스트 범위 계산 (hunk_lines 인덱스 기준)
        start_idx = max(0, blk_lines_idx[0] - CONTEXT_BEFORE)
        end_idx = min(len(hunk_lines) - 1, blk_lines_idx[-1] + CONTEXT_AFTER)
 
        # 스니펫 생성: 접두사(' ','+','-') 제거하고 합치기
        cleaned = []
        for i in range(start_idx, end_idx + 1):
            line = hunk_lines[i]
            if not line:
                cleaned.append("")
            else:
                # 앞 1글자 접두사 제거 후 원문만
                cleaned.append(line[1:] if line[0] in " +-"
                               else line)
 
        snippet = "\n".join(cleaned)
        snippet = snippet.strip()
        if len(snippet) > MAX_SNIPPET_CHARS:
            snippet = snippet[:MAX_SNIPPET_CHARS] + "\n..."
 
        out = {
            "kind": blk_kind,
            "end_side": end_side,
            "end_line": end_line,
            "snippet": snippet,
        }
 
        blk_kind = None
        blk_lines_idx = []
        blk_last_left = blk_last_right = None
        return out
 
    def flush_hunk():
        # 헌크 종료 시 블록 먼저 flush
        out = flush_block()
        if out:
            yield out
 
    # 헌크 단위로 순회
    cur_in_hunk = False
    for raw in patch.splitlines():
        line = raw.rstrip("\n")
        if line.startswith('@@'):
            # 이전 헌크 flush
            for item in flush_hunk() or ():
                yield item
            # 새 헌크 시작
            cur_in_hunk = True
            hunk_lines = []
            left_line, right_line = parse_hunk_header(line)
            hunk_left_start, hunk_right_start = left_line, right_line
            continue
 
        if not cur_in_hunk or left_line is None or right_line is None:
            continue
 
        # 헌크 본문 축적
        hunk_idx = len(hunk_lines)
        hunk_lines.append(line)
 
        if not line:
            # 빈줄은 컨텍스트처럼 취급: 블록 경계
            out = flush_block()
            if out:
                yield out
            continue
 
        prefix = line[0]
        if prefix == ' ':
            # 컨텍스트: 블록 경계
            out = flush_block()
            if out:
                yield out
            left_line += 1
            right_line += 1
        elif prefix == '-':
            # 삭제 블록 진행
            if blk_kind != "del":
                out = flush_block()
                if out:
                    yield out
                blk_kind = "del"
            blk_lines_idx.append(hunk_idx)
            blk_last_left = left_line
            left_line += 1
        elif prefix == '+':
            # 추가 블록 진행
            if blk_kind != "add":
                out = flush_block()
                if out:
                    yield out
                blk_kind = "add"
            blk_lines_idx.append(hunk_idx)
            blk_last_right = right_line
            right_line += 1
        else:
            # 알 수 없는 접두사: 블록 경계
            out = flush_block()
            if out:
                yield out
 
    # 파일의 마지막까지 왔다면, 열린 블록/헌크 flush
    out = flush_block()
    if out:
        yield out
 
def build_openai_prompt(path: str, change_type: str, snippet: str) -> str:
    return textwrap.dedent(USER_PROMPT_TEMPLATE.format(
        path=path,
        change_type=change_type,
        code=snippet,
    )).strip()
 
def create_review(owner: str, repo: str, pr_number: int,
                  commit_sha: str, comments: List[dict], body: str = "") -> dict:
    url = f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{pr_number}/reviews"
    payload = {
        "commit_id": commit_sha,
        "event": "COMMENT",       # 즉시 제출 (pending 아님)
        "comments": comments
    }
    if body:
        payload["body"] = body
    r = requests.post(url, headers=HEADERS, json=payload, timeout=60)
    if r.status_code not in (200, 201):
        try:
            print("Create review failed:", r.status_code, r.json())
        except Exception:
            print("Create review failed:", r.status_code, r.text)
        r.raise_for_status()
    return r.json()
 
def main():
    pr = get_pr(OWNER, REPO, PR_NUMBER)
    head_sha = pr["head"]["sha"]
    print("HEAD SHA:", head_sha)
 
    # 기존 pending 리뷰 정리
    ensure_no_pending_review(OWNER, REPO, PR_NUMBER)
 
    files = get_pr_files(OWNER, REPO, PR_NUMBER)
    if not files:
        print("변경된 파일이 없습니다.")
        return
 
    comments: List[dict] = []
    for f in files:
        path = f.get("filename")
        patch = f.get("patch")
        if not patch:
            print(f"[SKIP] patch 없음: {path}")
            continue
 
        print(f"[파일] {path}")
        para_count = 0
        for para in iter_paragraphs_with_context(patch):
            if para["end_line"] is None:
                continue
            if MAX_PARAGRAPHS_PER_FILE and para_count >= MAX_PARAGRAPHS_PER_FILE:
                break
 
            change_type = "added" if para["end_side"] == "RIGHT" else "deleted"
            prompt = build_openai_prompt(path, change_type, para["snippet"])
            review_text = call_openai_review(prompt)
 
            body = review_text
 
            comments.append({
                "path": path,
                "line": int(para["end_line"]),
                "side": para["end_side"],   # RIGHT(추가) / LEFT(삭제)
                "body": body
            })
            para_count += 1
            print(f"  - 단락 코멘트 준비: side={para['end_side']}, line={para['end_line']}")
 
    if not comments:
        print("생성할 코멘트가 없습니다.")
        return
 
    review = create_review(
        OWNER, REPO, PR_NUMBER,
        commit_sha=head_sha,
        comments=comments,
        body="변경된 단락별 자동 코드리뷰 코멘트입니다."
    )
    print("Review created:", review.get("html_url"))
 
if __name__ == "__main__":
    main()