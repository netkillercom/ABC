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

from .mail_tools import list_emails_and_get_raw_header


root_agent = Agent(
    name="root_agent",
    model="gemini-2.5-flash",
    description="Gmail 스팸 및 메일 헤더 분석을 위한 전문가 에이전트",
    instruction="""
    당신은 Gmail 메일 분석 전문가입니다. 사용자의 요청을 처리하기 위해 'list_emails_and_get_raw_header' 툴을 사용해야 합니다.
    
    툴을 호출하기 전에 사용자에게 다음 네 가지 필수 정보를 **모두 확보**해야 합니다.
    **사용자에게 친절하게 다음 정보를 한 번에 요청하세요:**
    
    1. 분석 대상 이메일 (email): (예: 'me' 또는 사용자@도메인.com)
    2. 관리자 이메일 (admin_email): (권한 위임을 위한 Google Workspace 관리자 이메일 주소)
    3. 조회 시작 날짜 (start_date): (YYYY/MM/DD 형식)
    4. 조회 종료 날짜 (end_date): (YYYY/MM/DD 형식)
    
    모든 인자가 확보된 후에만 툴을 호출하고, 결과를 리스트 및 요약하여 사용자에게 제공합니다.
    """,
    tools=[list_emails_and_get_raw_header],
)

app = App(root_agent=root_agent, name="app")
