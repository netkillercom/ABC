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

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from a2a.server.apps import A2AFastAPIApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard
from a2a.utils.constants import (
    AGENT_CARD_WELL_KNOWN_PATH,
    EXTENDED_AGENT_CARD_PATH,
)
from fastapi import FastAPI, Request
from google.adk.a2a.executor.a2a_agent_executor import A2aAgentExecutor
from google.adk.a2a.utils.agent_card_builder import AgentCardBuilder
from google.adk.artifacts.gcs_artifact_service import GcsArtifactService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.cloud import logging as google_cloud_logging
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider, export

from app.agent import app as adk_app
from app.utils.gcs import create_bucket_if_not_exists
from app.utils.tracing import CloudTraceLoggingSpanExporter
from app.utils.typing import Feedback


import logging


logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


import dotenv

dotenv.load_dotenv()


# _, project_id = google.auth.default()
# logging_client = google_cloud_logging.Client()
# logger = logging_client.logger(__name__)

# bucket_name = f"gs://{project_id}-workspace-console-manager-logs"
# create_bucket_if_not_exists(
#     bucket_name=bucket_name, project=project_id, location="us-central1"
# )

# provider = TracerProvider()
# processor = export.BatchSpanProcessor(CloudTraceLoggingSpanExporter())
# provider.add_span_processor(processor)
# trace.set_tracer_provider(provider)


A2A_RPC_PATH = f"/a2a/{adk_app.name}"

logger.info(f"ADK App Name: {adk_app.name}")
logger.info(f"A2A RPC Path: {A2A_RPC_PATH}")


runner = Runner(
    app=adk_app,
    # artifact_service=GcsArtifactService(bucket_name=bucket_name),
    session_service=InMemorySessionService(),
)

custom_executor = A2aAgentExecutor(runner=runner)

request_handler = DefaultRequestHandler(
    agent_executor=custom_executor, task_store=InMemoryTaskStore()
)


async def build_dynamic_agent_card() -> AgentCard:
    """Agent Card를 동적으로 빌드하여 게이트웨이의 메타데이터를 정의합니다."""
    try:
        base_url = os.getenv("APP_URL", "http://127.0.0.1:8000")
        rpc_url = f"{base_url}{A2A_RPC_PATH}"
        agent_version = os.getenv("AGENT_VERSION", "0.1.0")

        logger.info("🧩 [AgentCard Build Info] Starting build process.")

        logger.info("🧩 [AgentCard Build Info] Starting build process.")
        logger.info(f" - adk_app.root_agent.name: {adk_app.root_agent.name}")
        logger.info(f" - rpc_url: {rpc_url}")

        agent_card_builder = AgentCardBuilder(
            agent=adk_app.root_agent,
            capabilities=AgentCapabilities(streaming=True),
            rpc_url=rpc_url,
            agent_version=agent_version,
        )
        agent_card = await agent_card_builder.build()
        logger.info("✅ AgentCard successfully built.")
        return agent_card

    except Exception as e:
        logger.error(f"❌ Error building AgentCard: {e}", exc_info=True)
        raise


@asynccontextmanager
async def lifespan(app_instance: FastAPI) -> AsyncIterator[None]:
    """FastAPI 서버 시작 시 A2A 라우트를 등록합니다."""
    logger.info("🚀 lifespan() called: Registering A2A routes.")
    try:
        agent_card = await build_dynamic_agent_card()

        a2a_app = A2AFastAPIApplication(
            agent_card=agent_card, http_handler=request_handler
        )
        # 🚨 POST /a2a/app (A2A RPC) 엔드포인트를 FastAPI에 등록합니다.
        a2a_app.add_routes_to_app(
            app_instance,
            agent_card_url=f"{A2A_RPC_PATH}{AGENT_CARD_WELL_KNOWN_PATH}",
            rpc_url=A2A_RPC_PATH,
            extended_agent_card_url=f"{A2A_RPC_PATH}{EXTENDED_AGENT_CARD_PATH}",
        )
        logger.info("✅ A2A routes registered.")
    except Exception as e:
        logger.error(f"❌ Error during lifespan setup: {e}", exc_info=True)
    yield


# 기존 함수 참조 유지
orig_on_message_send = DefaultRequestHandler.on_message_send
orig_setup = DefaultRequestHandler._setup_message_execution
orig_run = DefaultRequestHandler._run_event_stream


# 로깅 개선된 래퍼 함수들
async def debug_on_message_send(self, params, context=None):
    logger.debug("\n🟢 DefaultRequestHandler.on_message_send CALLED")
    logger.debug("params.message: %s", params.message)
    result = await orig_on_message_send(self, params, context)
    logger.debug("🟢 on_message_send RESULT: %s", result)
    return result


async def debug_setup(self, params, context=None):
    logger.debug("\n🟡 _setup_message_execution CALLED")
    logger.debug("params.message: %s", params.message)
    return await orig_setup(self, params, context)


async def debug_run(self, request, queue):
    logger.debug("\n🔵 _run_event_stream CALLED")
    logger.debug("request.task_id: %s", request.task_id)
    return await orig_run(self, request, queue)


# Monkey patching 적용
DefaultRequestHandler.on_message_send = debug_on_message_send
DefaultRequestHandler._setup_message_execution = debug_setup
DefaultRequestHandler._run_event_stream = debug_run


logger.info("Request Handler's Executor: %s", request_handler.agent_executor.execute)


app = FastAPI(
    title="workspace-console-manager",
    description="API for interacting with the Agent workspace-console-manager",
    lifespan=lifespan,
)


@app.middleware("http")
async def debug_middleware(request, call_next):
    logger.debug(f"\n🧩 FastAPI Request Path: {request.url.path}")
    response = await call_next(request)
    logger.debug(f"🧩 FastAPI Response Status: {response.status_code}")
    return response


# Main execution
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="debug")
