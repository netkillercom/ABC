import base64
import os
import sys
from email import message_from_string
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

try:
    from auth import get_delegated_credentials
except ModuleNotFoundError:
    # 만약 auth.py가 user-agent 폴더가 아닌, agent-starter 폴더에 있다면
    sys.path.append(
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    )
    from auth import get_delegated_credentials


def classify_header_spam(header_text: str) -> str:
    """
    이메일 헤더를 분석하여 SPF, DKIM 결과와 수신 경로 수를 확인하고,
    스팸 여부와 근거를 문자열로 반환합니다.
    """
    print("🔬 [Tool] classify_header_spam 실행")

    # 이메일 헤더 전문을 파싱
    msg = message_from_string(header_text)
    findings = []

    # SPF 검사
    auth_results = msg.get("Authentication-Results", "")
    if "spf=fail" in auth_results.lower():
        findings.append("SPF 검사 실패 (spf=fail): 의심 발신자 IP")

    # DKIM 검사
    if "dkim=fail" in auth_results.lower():
        findings.append("DKIM 검사 실패 (dkim=fail): 헤더 변조 의심")

    # DMARC 검사 (추가 검사)
    if "dmarc=fail" in auth_results.lower():
        findings.append("DMARC 검사 실패 (dmarc=fail): 정책 미준수")

    # 수신 경로 개수 확인
    received_count = len(msg.get_all("Received", []))
    findings.append(f"Received 헤더 개수 (수신 경로): {received_count}개")

    # 최종 판단 및 보고서 생성
    if any("실패" in item for item in findings):
        status = "🚨 스팸 가능성이 높은 메일로 판단됩니다."
    else:
        status = "✅ 스팸 징후가 없는 정상 메일로 판단됩니다."

    report = "\n".join([status] + findings)
    return report


def list_emails_and_get_raw_header(
    admin_email: str, email: str, start_date: str, end_date: str
) -> dict:
    """
    Gmail API를 사용하여 특정 기간 내의 이메일 목록을 조회하고,
    각 이메일의 전체 원본 헤더 전문을 추출하여 스팸 분석을 수행합니다.

    Args:
        email (str): 조회할 사용자의 이메일 주소 ('me' 또는 실제 이메일).
        start_date (str): 조회 시작 날짜 (YYYY/MM/DD 형식).
        end_date (str): 조회 종료 날짜 (YYYY/MM/DD 형식).

    Returns:
        dict: 조회 및 분석 결과 데이터 목록 또는 오류 메시지.
    """
    print(
        f"🛠️ [Tool] list_emails_and_get_raw_header 실행 (기간: {start_date} ~ {end_date})"
    )
    # read-only 권한만 필요
    scopes = ["https://www.googleapis.com/auth/gmail.readonly"]

    try:
        credentials = get_delegated_credentials(admin_email=admin_email, scopes=scopes)
    except NameError:
        return {
            "success": False,
            "error": "인증 정보 (get_delegated_credentials)를 찾을 수 없습니다.",
        }

    if not credentials:
        return {"success": False, "error": "인증 실패"}

    try:
        service = build("gmail", "v1", credentials=credentials)

        # --- 내부 헬퍼 함수: 메시지 원본 내용 추출 ---
        def get_raw_message(msg_id: str) -> dict:
            """특정 이메일 ID의 원본 데이터를 추출합니다."""

            # format='raw'를 사용하여 이메일의 전체 원본 MIME 메시지를 가져옵니다.
            message = (
                service.users()
                .messages()
                .get(userId=email, id=msg_id, format="raw")
                .execute()
            )

            # 원본 데이터는 Base64 URL-safe로 인코딩되어 있습니다.
            raw_data = message.get("raw")
            if not raw_data:
                return {"id": msg_id, "error": "원본 데이터를 찾을 수 없습니다."}

            # Base64 디코딩하여 원본 텍스트(헤더 + 본문)를 가져옵니다.
            # 스팸 분석 함수는 이 전체 텍스트에서 헤더만 추출하여 사용합니다.
            raw_text = base64.urlsafe_b64decode(raw_data).decode(
                "utf-8", errors="ignore"
            )

            # 메일의 제목을 빠르게 추출 (분석 결과와 함께 보여주기 위함)
            # 전체 텍스트에서 'Subject' 헤더만 파싱
            msg_parser = message_from_string(raw_text)
            subject = msg_parser.get("Subject", "제목 없음")

            # 스팸 분석 함수 호출
            spam_report = classify_header_spam(raw_text)

            return {
                "id": msg_id,
                "subject": subject,
                "spam_analysis_report": spam_report,
                # 전체 원본 헤더는 보고서에 길어질 수 있으므로, 분석 결과만 반환합니다.
                # 'raw_header_full': raw_text
            }

        # ---------------------------------------------------

        # 1. 메시지 ID 목록 조회
        query_string = f"after:{start_date} before:{end_date}"
        print(f"🔍 [Query] {query_string}")

        # format='metadata'를 사용하여 목록 조회 시 오버헤드 최소화
        results = (
            service.users().messages().list(userId=email, q=query_string).execute()
        )
        message_ids = results.get("messages", [])

        if not message_ids:
            return {
                "success": True,
                "data": [],
                "message": f"{query_string} 조건에 해당하는 이메일이 없습니다.",
            }

        # 2. 각 ID에 대해 원본 데이터 조회 및 스팸 분석 수행
        analysis_results = []
        for msg_info in message_ids:
            analysis_results.append(get_raw_message(msg_info["id"]))

        return {"success": True, "data": analysis_results}

    except HttpError as error:
        return {"success": False, "error": f"API 오류: {error}"}


# 하루전에 발생한 이메일들을 조회하고 헤더를 총 분석하는 함수
def list_yesterdays_emails_and_get_raw_header(admin_email: str, email: str) -> dict:
    from datetime import datetime, timedelta

    today = datetime.utcnow().date()
    yesterday = today - timedelta(days=1)

    start_date = yesterday.strftime("%Y/%m/%d")
    end_date = today.strftime("%Y/%m/%d")

    return list_emails_and_get_raw_header(
        admin_email=admin_email,
        email=email,
        start_date=start_date,
        end_date=end_date,
    )
