"""
MCP client helpers for CritiqAI.

Architecture (corrected):
- argument-scorer : stdio local Python MCP  (luôn available)
- Google Drive    : remote SSE tại drivemcp.googleapis.com  (OAuth Bearer)
- Gmail           : remote SSE tại gmailmcp.googleapis.com   (OAuth Bearer)
- Google Sheets   : Google Sheets REST API trực tiếp          (OAuth Bearer)
  → Sheets KHÔNG có MCP server chính thức — dùng googleapiclient thay thế

OAuth token được lấy từ token.json (do google-auth-oauthlib tạo lần đầu)
hoặc từ biến môi trường GOOGLE_ACCESS_TOKEN (CI/production).
"""

import json
import logging
import os
import sys

from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

logger = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────────
DRIVE_MCP_URL  = "https://drivemcp.googleapis.com/mcp/v1"
GMAIL_MCP_URL  = "https://gmailmcp.googleapis.com/mcp/v1"
SCORER_URL     = os.getenv("SCORER_URL", "")  # e.g. https://argument-scorer-xxx.run.app

DEBATE_LOG_SHEET_ID = os.getenv("DEBATE_LOG_SHEET_ID", "")
_DEBATE_LOG_COL_RANGE = "A:G"   # column range only — sheet name resolved dynamically
TEACHER_EMAIL       = os.getenv("TEACHER_EMAIL", "")

# Keyed by spreadsheet ID so a different sheet (e.g. across tests/sessions)
# never returns another spreadsheet's cached tab name.
_first_sheet_name_cache: dict[str, str] = {}


def _get_first_sheet_name(service) -> str:
    """Return the first sheet tab name, cached per spreadsheet ID."""
    cached = _first_sheet_name_cache.get(DEBATE_LOG_SHEET_ID)
    if cached is None:
        meta = service.spreadsheets().get(
            spreadsheetId=DEBATE_LOG_SHEET_ID, fields="sheets.properties.title"
        ).execute()
        cached = meta["sheets"][0]["properties"]["title"]
        _first_sheet_name_cache[DEBATE_LOG_SHEET_ID] = cached
    return cached

TOKEN_FILE = os.getenv(
    "TOKEN_FILE_PATH",
    os.path.join(os.path.dirname(__file__), "token.json"),
)
SCORER_SERVER_PATH = os.path.join(
    os.path.dirname(__file__), "mcp_servers", "argument_scorer", "server.py"
)

SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/gmail.compose",
]


# ── OAuth helper ───────────────────────────────────────────────────────────────

def _get_credentials():
    """
    Trả về google.oauth2.credentials.Credentials đã được refresh.
    Lần đầu: mở browser để user đăng nhập, lưu token.json.
    Các lần sau: load token.json và tự refresh nếu hết hạn.
    """
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from google_auth_oauthlib.flow import InstalledAppFlow

        creds = None
        if os.path.exists(TOKEN_FILE):
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                client_id     = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "")
                client_secret = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "")
                if not client_id or not client_secret:
                    logger.warning("GOOGLE_OAUTH_CLIENT_ID / SECRET không có trong .env")
                    return None

                client_config = {
                    "installed": {
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                        "redirect_uris": ["http://localhost"],
                    }
                }
                flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
                creds = flow.run_local_server(port=0)

            # Atomic write: a crash mid-write must not leave a truncated
            # token.json that breaks every subsequent run.
            tmp = f"{TOKEN_FILE}.tmp"
            with open(tmp, "w") as f:
                f.write(creds.to_json())
            os.replace(tmp, TOKEN_FILE)

        return creds
    except Exception as e:
        logger.warning("OAuth không khả dụng: %s", e)
        return None


def _bearer_token() -> str | None:
    """Trả về access token string, hoặc None nếu không có."""
    creds = _get_credentials()
    return creds.token if creds else None


# ── argument-scorer MCP ────────────────────────────────────────────────────────
# Routing:
#   SCORER_URL set  → HTTP streamable-http (Cloud Run / serverless)
#   SCORER_URL not set → stdio subprocess (local dev)
#   Both fail       → direct Python import of rubric.py

async def score_argument_via_mcp(text: str) -> dict:
    """
    Gọi argument-scorer MCP.
    - Nếu SCORER_URL được set: kết nối qua HTTP (Cloud Run).
    - Nếu không: gọi stdio subprocess cục bộ.
    - Fallback: import rubric.py trực tiếp (0 subprocess, 0 network).
    """
    if SCORER_URL:
        return await _score_via_http(text)
    return await _score_via_stdio(text)


async def _score_via_http(text: str) -> dict:
    """Connect tới argument-scorer Cloud Run qua MCP streamable-http."""
    try:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        url = SCORER_URL.rstrip("/") + "/mcp"
        async with streamablehttp_client(url) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "score_argument", {"text": text, "rubric": "paul_elder"}
                )
                raw = result.content[0].text if result.content else "{}"
                return json.loads(raw)
    except Exception as e:
        logger.warning("argument-scorer HTTP unavailable (%s) — dùng fallback trực tiếp", e)
        return _fallback_score(text)


async def _score_via_stdio(text: str) -> dict:
    """Spawn argument-scorer subprocess qua stdio (local dev)."""
    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        server_params = StdioServerParameters(
            command=sys.executable,
            args=[SCORER_SERVER_PATH],
        )
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "score_argument", {"text": text, "rubric": "paul_elder"}
                )
                raw = result.content[0].text if result.content else "{}"
                return json.loads(raw)
    except Exception as e:
        logger.warning("argument-scorer MCP unavailable (%s) — dùng fallback trực tiếp", e)
        return _fallback_score(text)


def _fallback_score(text: str) -> dict:
    try:
        rubric_dir = os.path.join(os.path.dirname(__file__), "mcp_servers", "argument_scorer")
        if rubric_dir not in sys.path:
            sys.path.insert(0, rubric_dir)
        from rubric import score_all
        return score_all(text)
    except Exception as e:
        logger.error("Fallback scorer thất bại: %s", e)
        return {
            "logical_coherence": 2, "evidence_quality": 2,
            "counterargument_handling": 2, "scope_awareness": 2,
            "total": 8, "max_possible": 20, "percentage": 40,
        }


# ── Google Drive MCP (remote SSE, OAuth) ──────────────────────────────────────

async def read_essay_from_drive(doc_url: str) -> str | None:
    """
    Đọc nội dung Google Doc.
    Thử Drive MCP remote trước; fallback sang Drive REST API nếu MCP lỗi.
    Trả về plain text hoặc None.
    """
    if not doc_url:
        return None

    # Thử Drive REST API trực tiếp (đáng tin cậy hơn MCP SSE hiện tại)
    result = await _read_drive_via_api(doc_url)
    if result:
        return result

    # Fallback: Drive MCP SSE
    token = _bearer_token()
    if not token:
        logger.warning("Không có OAuth token — không thể đọc Drive")
        return None
    try:
        from mcp import ClientSession
        from mcp.client.sse import sse_client
        import asyncio

        headers = {"Authorization": f"Bearer {token}"}
        async with asyncio.timeout(10):
            async with sse_client(DRIVE_MCP_URL, headers=headers) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    res = await session.call_tool(
                        "get_document", {"document_url": doc_url}
                    )
                    return res.content[0].text if res.content else None
    except Exception as e:
        logger.warning("Drive MCP SSE cũng lỗi: %s", e)
        return None


async def _read_drive_via_api(doc_url: str) -> str | None:
    """Đọc Google Doc qua Drive + Docs REST API (googleapiclient)."""
    import re
    creds = _get_credentials()
    if not creds:
        return None
    try:
        from googleapiclient.discovery import build

        # Trích doc_id từ URL
        match = re.search(r"/document/d/([a-zA-Z0-9_-]+)", doc_url)
        if not match:
            logger.warning("Không parse được doc_id từ URL: %s", doc_url)
            return None
        doc_id = match.group(1)

        docs_service = build("docs", "v1", credentials=creds)
        doc = docs_service.documents().get(documentId=doc_id).execute()

        # Ghép nội dung text từ tất cả paragraph
        lines = []
        for elem in doc.get("body", {}).get("content", []):
            para = elem.get("paragraph")
            if not para:
                continue
            text = "".join(
                e.get("textRun", {}).get("content", "")
                for e in para.get("elements", [])
            )
            lines.append(text)
        return "".join(lines).strip() or None
    except Exception as e:
        logger.warning("Drive REST API lỗi: %s", e)
        return None


# ── Google Sheets (REST API trực tiếp — không có MCP chính thức) ──────────────

async def append_debate_row(
    session_id: str,
    round_label: str,
    student_name: str,
    persona: str,
    challenge: str,
    student_response: str,
    scores: dict | None = None,
) -> bool:
    """
    Ghi 1 dòng vào Google Sheet qua Sheets REST API (googleapiclient).
    Columns: session_id | student_name | round | persona | challenge | response | scores_json
    """
    if not DEBATE_LOG_SHEET_ID:
        logger.warning("DEBATE_LOG_SHEET_ID chưa cấu hình — bỏ qua Sheets log")
        return False
    
    # MOCK MODE check
    if not os.getenv("GOOGLE_OAUTH_CLIENT_ID"):
        logger.info("MOCK MODE: Đã giả lập ghi log Sheets cho session %s", session_id)
        return True

    creds = _get_credentials()
    if not creds:
        logger.warning("Không có OAuth credentials — bỏ qua Sheets log")
        return False
    try:
        from googleapiclient.discovery import build

        scores_str = json.dumps(scores) if scores else ""
        row = [session_id, student_name, str(round_label), persona, challenge, student_response, scores_str]

        service = build("sheets", "v4", credentials=creds)
        first_sheet = _get_first_sheet_name(service)
        range_str = f"{first_sheet}!{_DEBATE_LOG_COL_RANGE}"
        service.spreadsheets().values().append(
            spreadsheetId=DEBATE_LOG_SHEET_ID,
            range=range_str,
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": [row]},
        ).execute()

        logger.info("Sheets: đã ghi row [%s / %s]", session_id, round_label)
        return True
    except Exception as e:
        logger.warning("Sheets API lỗi: %s — bỏ qua row log", e)
        return False


# ── Gmail MCP (remote SSE, OAuth) ─────────────────────────────────────────────

async def create_gmail_draft(to: str, subject: str, body: str) -> str | None:
    """
    Tạo Gmail draft qua Gmail MCP chính thức của Google.
    URL: https://gmailmcp.googleapis.com/mcp/v1
    KHÔNG tự gửi — chỉ tạo draft để giáo viên review.
    Trả về draft_id hoặc None.
    """
    recipient = to or TEACHER_EMAIL
    if not recipient:
        logger.warning("TEACHER_EMAIL chưa cấu hình — bỏ qua Gmail draft")
        return None

    # MOCK MODE check
    if not os.getenv("GOOGLE_OAUTH_CLIENT_ID"):
        logger.info("MOCK MODE: Đã giả lập tạo Gmail Draft tới %s", recipient)
        return "mock_draft_123"

    token = _bearer_token()
    if not token:
        logger.warning("Không có OAuth token — không thể tạo Gmail draft")
        return None
    try:
        from mcp import ClientSession
        from mcp.client.sse import sse_client
        import asyncio

        headers = {"Authorization": f"Bearer {token}"}
        # Guard with a timeout like the Drive call — an unresponsive Gmail MCP
        # endpoint must not hang the request indefinitely; the except clause
        # below falls back to the REST API.
        async with asyncio.timeout(15):
            async with sse_client(GMAIL_MCP_URL, headers=headers) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(
                        "create_draft",
                        {"to": recipient, "subject": subject, "body": body},
                    )
                    raw = result.content[0].text if result.content else "{}"
                    data = json.loads(raw)
                    draft_id = data.get("id") or data.get("draft_id")
                    logger.info("Gmail draft tạo thành công: %s", draft_id)
                    return draft_id
    except Exception as e:
        logger.warning("Gmail MCP unavailable: %s — fallback dùng Gmail API", e)
        return await _create_gmail_draft_via_api(recipient, subject, body)


async def _create_gmail_draft_via_api(to: str, subject: str, body: str) -> str | None:
    """Fallback: tạo draft qua Gmail REST API (googleapiclient) nếu MCP lỗi."""
    creds = _get_credentials()
    if not creds:
        return None
    try:
        import base64
        from email.mime.text import MIMEText
        from googleapiclient.discovery import build

        message = MIMEText(body)
        message["to"] = to
        message["subject"] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

        service = build("gmail", "v1", credentials=creds)
        draft = service.users().drafts().create(
            userId="me", body={"message": {"raw": raw}}
        ).execute()
        draft_id = draft.get("id")
        logger.info("Gmail draft (REST fallback) tạo thành công: %s", draft_id)
        return draft_id
    except Exception as e:
        logger.warning("Gmail REST API cũng lỗi: %s", e)
        return None


# ── Self-test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import asyncio

    async def _test():
        sample = (
            "According to WHO (2023), screen time over 4 hours correlates with depression "
            "in 34% of adolescents. While some argue social media connects isolated communities, "
            "the harm may outweigh benefits. Therefore, regulation is needed. However, this "
            "argument applies only to teenagers in high-income countries and may not generalize."
        )
        print("Testing argument-scorer MCP...")
        scores = await score_argument_via_mcp(sample)
        print("Scores:", json.dumps(scores, indent=2))

    asyncio.run(_test())
