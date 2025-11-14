import json
import os
import sys
from typing import Optional, Any, Dict
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.genai import types
from google.adk.agents.callback_context import CallbackContext
from google.adk.tools.base_tool import BaseTool, ToolContext


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

try:
    from auth import get_delegated_credentials
except ModuleNotFoundError:
    # 만약 auth.py가 user-agent 폴더가 아닌, agent-starter 폴더에 있다면
    sys.path.append(
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    )
    from auth import get_delegated_credentials


# --------------------------
# 1. 툴 함수: 데이터 조회 및 정리 (get_google_workspace_users)
# --------------------------


def get_google_workspace_users(admin_email: str, domain: str) -> dict:
    """Google Admin SDK를 사용하여 특정 도메인의 사용자 목록을 조회합니다."""
    print(
        f"🛠️ [Tool] get_google_workspace_users 실행 (Admin: {admin_email}, Domain: {domain})"
    )
    scopes = ["https://www.googleapis.com/auth/admin.directory.user.readonly"]

    credentials = get_delegated_credentials(admin_email, scopes)

    if not credentials:
        return {
            "success": False,
            "error": "인증 실패 (Admin Email 또는 서비스 계정 파일 문제)",
        }

    try:
        service = build("admin", "directory_v1", credentials=credentials)
        results = (
            service.users()
            .list(
                domain=domain,
                maxResults=100,
                orderBy="email",
                projection="full",  # 👈 추가: 사용자 객체의 모든 필드를 반환하도록 요청
            )
            .execute()
        )
        users = results.get("users", [])

        # LLM에 전달할 최종 포맷으로 데이터 정리 (JSON 리스트)
        formatted_users = []
        for user in users:
            is_admin = user.get("isAdmin", False)

            formatted_users.append(
                {
                    "email": user.get("primaryEmail", "N/A"),
                    # aliases 필드는 "full" projection으로 반환될 가능성이 높습니다.
                    "별칭_aliases": ", ".join(user.get("aliases", []) or []),
                    "역할_isAdmin": "관리자" if is_admin else "일반 사용자",
                    "상태_status": "정지됨" if user.get("suspended") else "활성",
                }
            )

        return {"success": True, "data": formatted_users}

    except HttpError as error:
        return {"success": False, "error": f"API 오류: {error}"}


# --------------------------
# 2. 콜백 함수: LLM 컨텍스트 정리 (보안 및 포맷팅)
# --------------------------


def format_and_mask_user_data(
    # callback_context: CallbackContext,
    tool: BaseTool,
    args: Dict[str, Any],
    tool_context: ToolContext,
    tool_response: Dict,  # 👈 툴이 반환한 Python Dictionary
) -> Optional[types.Content]:
    """
    툴 호출 결과를 확인하고, 사용자 데이터를 지정된 포맷으로 정리하고 일부 정보를 마스킹하여
    LLM 컨텍스트에 전달합니다.
    """
    print("🔄 [Callback] format_and_mask_user_data 실행")

    # 1. 툴 응답(tool_response)은 이미 Dictionary이므로 파싱 필요 없음
    result = tool_response

    # 에러 발생 시 처리 (tool_response에 error 키가 있을 경우)
    if not result.get("success", False):
        print(f"Callback skipping masking due to error: {result.get('error')}")
        return None

    if "data" in result:
        original_data_list = result["data"]

        if not original_data_list:
            final_summary_text = "조회된 사용자 데이터가 없습니다."
        else:
            formatted_output_lines = []

            for user in original_data_list:
                email = user.get("email", "N/A")

                # 📧 보안 마스킹 적용
                if "@" in email:
                    local_part, domain_part = email.split("@")
                    masked_local_part = local_part[:3] + "***"
                    masked_email = f"{masked_local_part}@{domain_part}"
                else:
                    masked_email = email

                # 📝 LLM이 요약하기 쉽도록 포맷 구성
                formatted_output_lines.append(
                    f"이메일: {masked_email} | 별칭: {user.get('별칭_aliases', '없음')} "
                    f"| 역할: {user.get('역할_isAdmin', '일반')} | 상태: {user.get('상태_status')}"
                )

        # 3. 마스킹된 데이터로 새 Content 객체 생성
        # 🚨 types.Content를 반환하여 툴의 원래 JSON 응답을 덮어씁니다.
        new_content = types.Content(
            role="function",
            parts=[
                types.Part.from_text(
                    text=json.dumps(
                        {
                            # 🚨 수정: 요약 리스트만 전달하고, 개수는 별도 필드로 전달
                            "user_summary_list": formatted_output_lines,
                            "user_count": (
                                len(original_data_list) if original_data_list else 0
                            ),
                            "success": True,
                        }
                    )
                ),
            ],
        )
        return new_content

    # 툴 호출 결과가 success: False였거나 예상치 못한 형식인 경우, None 반환
    return None
