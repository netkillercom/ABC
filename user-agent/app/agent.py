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

from google.adk.agents import Agent
from google.adk.apps.app import App

from .user_tools import get_google_workspace_users, format_and_mask_user_data

# root_agent 정의
root_agent = Agent(
    name="root_agent",
    model="gemini-2.5-flash",
    description="Google Workspace의 사용자 목록을 조회하는 전문가입니다. 반드시 get_google_workspace_users 툴을 사용해야 합니다.",
    instruction="""
    당신은 Google Workspace 전문가입니다.
    사용자로부터 요청을 받으면, 반드시 'get_google_workspace_users' 툴을 호출하여 사용자 목록을 조회해야 합니다.
    
    툴을 호출하기 전에 사용자에게 다음 두 가지 필수 정보를 **모두 확보**해야 합니다.
    **친절하게 다음 정보를 한 번에 요청하세요:**
    
    1. 관리자 이메일 (admin_email): (권한 위임을 위한 Google Workspace 관리자 이메일 주소, 예: admin@example.com)
    2. 조회 도메인 (domain): (사용자를 조회할 Google Workspace 도메인 이름, 예: example.com)
    
    모든 인자가 확보된 후에만 툴을 호출하고, 결과를 바탕으로 사용자 목록을 친절하게 요약하여 보고하세요.
    """,
    tools=[get_google_workspace_users],
    after_tool_callback=format_and_mask_user_data,
)

app = App(root_agent=root_agent, name="app")
