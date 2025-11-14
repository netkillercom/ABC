import os
from typing import Any

import requests
from dotenv import load_dotenv
from fastapi.openapi.models import (OAuth2, OAuthFlowAuthorizationCode,
                                    OAuthFlows)
from google.adk.auth import AuthCredential, AuthCredentialTypes, OAuth2Auth
from google.adk.auth.auth_tool import AuthConfig
from google.adk.tools import ToolContext
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

load_dotenv()


def _get_env_or_raise(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"{name} 환경 변수가 설정되지 않았습니다. auth_agent/.env 파일을 확인하세요."
        )
    return value


GOOGLE_CLIENT_ID = _get_env_or_raise("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = _get_env_or_raise("GOOGLE_CLIENT_SECRET")
USERINFO_ENDPOINT = "https://openidconnect.googleapis.com/v1/userinfo"
REQUEST_TIMEOUT_SECONDS = 10
STATE_NAMESPACE = "auth_agent"
STATE_RESULT_KEY = "result_message"
STATE_FLAG_KEY = "is_super_admin"
STATE_EMAIL_KEY = "user_email"


auth_scheme = OAuth2(
    flows=OAuthFlows(
        authorizationCode=OAuthFlowAuthorizationCode(
            authorizationUrl="https://accounts.google.com/o/oauth2/auth",
            tokenUrl="https://oauth2.googleapis.com/token",
            scopes={
                "openid": "OpenID Connect",
                "https://www.googleapis.com/auth/userinfo.email": "User Email",
                "https://www.googleapis.com/auth/gmail.readonly": "User Gmail",
                "https://www.googleapis.com/auth/admin.directory.user.readonly": "Admin SDK ReadOnly",
            },
        )
    )
)

auth_credential = AuthCredential(
    auth_type=AuthCredentialTypes.OAUTH2,
    oauth2=OAuth2Auth(
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
    ),
)

auth_config = AuthConfig(
    auth_scheme=auth_scheme,
    raw_auth_credential=auth_credential,
)


def _get_state_bucket(tool_context: ToolContext) -> dict[str, Any]:
    state = getattr(tool_context, "state", None)
    if state is None:
        state = {}
        tool_context.state = state
    return state.setdefault(STATE_NAMESPACE, {})


def _build_admin_service(access_token: str):
    creds = Credentials(token=access_token)
    return build(
        "admin",
        "directory_v1",
        credentials=creds,
        cache_discovery=False,
    )


def _fetch_user_email(access_token: str) -> str:
    try:
        response = requests.get(
            USERINFO_ENDPOINT,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(f"Userinfo API 오류: {exc}") from exc

    user_email = response.json().get("email")
    if not user_email:
        raise RuntimeError("사용자 이메일을 가져올 수 없습니다.")
    return user_email


def _is_super_admin(access_token: str, user_email: str) -> bool:
    try:
        admin_service = _build_admin_service(access_token)
        user_resource = (
            admin_service.users()
            .get(userKey=user_email, viewType="admin_view", projection="full")
            .execute()
        )
    except Exception as exc:
        raise RuntimeError(f"Admin SDK API 오류: {exc}") from exc
    return user_resource.get("isAdmin") is True


def verify_super_admin_status(
    tool_context: ToolContext,
    credential: AuthCredential | None = None,
) -> str:
    """
    현재 인증된 사용자가 Google Workspace 슈퍼 관리자인지 확인합니다.
    결과는 세션 상태에 캐시됩니다.
    """
    state_bucket = _get_state_bucket(tool_context)
    cached_result = state_bucket.get(STATE_RESULT_KEY)
    if cached_result:
        return cached_result

    if not credential or not credential.oauth2 or not credential.oauth2.access_token:
        return "ADK에서 액세스 토큰을 가져오는 데 실패했습니다."

    access_token = credential.oauth2.access_token

    try:
        user_email = _fetch_user_email(access_token)
        is_admin = _is_super_admin(access_token, user_email)
    except RuntimeError as exc:
        return str(exc)

    if is_admin:
        result_message = f"성공: {user_email} 님은 슈퍼 관리자입니다."
    else:
        result_message = f"실패: {user_email} 님은 슈퍼 관리자가 아닙니다."

    state_bucket[STATE_RESULT_KEY] = result_message
    state_bucket[STATE_FLAG_KEY] = is_admin
    state_bucket[STATE_EMAIL_KEY] = user_email
    return result_message