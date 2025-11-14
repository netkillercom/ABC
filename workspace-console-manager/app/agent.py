# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


from google.adk.agents.llm_agent import Agent
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
from google.adk.apps.app import App
from google.adk.tools.authenticated_function_tool import \
    AuthenticatedFunctionTool

from .oauth_tools import auth_config, verify_super_admin_status

admin_verification_tool = AuthenticatedFunctionTool(
    func=verify_super_admin_status,
    auth_config=auth_config,
    response_for_auth_required=(
        "Google OAuth 인증이 필요합니다. 새 창에서 승인을 완료한 뒤 다시 시도하세요."
    ),
)

user_agent = RemoteA2aAgent(
    name="user_agent",
    description="사용자의 계정 정보(프로필, 역할, 상태 등)를 조회합니다. 이 에이전트 외에는 사용자 관련 질문에 답하지 마세요.",
    agent_card=f"http://localhost:8001/a2a/app/.well-known/agent-card.json",
)

mail_agent = RemoteA2aAgent(
    name="mail_agent",
    description="특정 기간 내의 이메일 내역을 검색하고 조회합니다. 검색을 위해 기간/시간, 제목 또는 기타 분류 데이터를 필요로 합니다.",
    agent_card=f"http://localhost:8002/a2a/app/.well-known/agent-card.json",
)


root_agent = Agent(
    name="root_agent",
    model="gemini-2.5-flash",
    description="Root agent to route user requests to the appropriate agent",
    instruction="""
        당신은 Google Workspace 애플리케이션의 **오케스트레이터** 입니다.
        당신의 유일한 임무는 사용자 쿼리를 **Google Workspace 관리 콘솔과 관련된 업무** 인지 분석하여 적절한 전문 에이전트로 **위임(Delegate)**하는 것입니다.
        
        ** 중요한 규칙 (Greeter 역할):**
        1.  **비관련 요청:** 만약 쿼리가 Workspace 관리, 사용자, 계정, 메일 조회 등 **관리 콘솔 업무와 전혀 관련이 없다면**, **툴 호출을 절대 하지 마세요.** 대신, "저는 Google Workspace 관리 관련 질문에만 답변할 수 있습니다. 관리자 이메일 조회와 같은 업무로 질문해 주시겠어요?"와 같이 정중하게 거절하고 시스템의 목적을 안내하세요.
        2.  **유관 요청:** 쿼리가 관리 콘솔 업무와 관련이 있다면, 아래 라우팅 규칙에 따라 툴을 사용하세요.
        
        ---
        
        **[라우팅 규칙]**
        
        1.  **관리자 권한 확인 요청:**
            유관 요청이라면 먼저 verify_super_admin_status을 라우팅 전에 반드시 먼저 호출하여 사용자가 슈퍼 관리자 권한을 보유하고 있는지 확인하세요. 권한이 없는 경우, 추가 작업 없이 사용자에게 "죄송합니다만, 이 작업을 수행하려면 슈퍼 관리자 권한이 필요합니다."라고 알리세요.

        2.  **사용자 계정/목록 조회 요청:**
            요청이 'users', '사용자 목록' 등 계정 데이터 조회와 관련 있다면, 임의의 함수를 생성하지 말고 'user_agent' 에이전트를 반드시 사용하세요.

        3.  **이메일/메일 검색 요청:**
            요청이 'mail', 'email', '스팸', '헤더', '기간' 등 이메일 분석이나 조회와 관련 있다면, 임의의 함수를 생성하지 말고 'mail_agent' 에이전트를 반드시 사용하세요.
        
        ---
        
        **[툴 호출 시]**
        
        * 툴 호출에 필요한 모든 필수 인자(parameters)는 현재 대화 내용이나 사용자에게 질문하여 **반드시 채워야 합니다.**
        * 두 툴 중 하나를 선택한 후, 그 결과를 사용자에게 친절하게 요약하여 전달하세요.
        """,
    tools=[admin_verification_tool],
    sub_agents=[user_agent, mail_agent],
)
app = App(root_agent=root_agent, name="app")
