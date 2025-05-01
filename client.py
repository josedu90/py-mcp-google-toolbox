import asyncio
import sys
import json
import logging
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from typing import Any, Dict, List, Optional

# --- 로깅 설정 ---
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 서버 스크립트 파일명 (실제 서버 파일명과 일치해야 함)
SERVER_SCRIPT_FILENAME = "server.py"

async def run_tool_call(tool_name: str, arguments: Dict[str, Any]) -> None:
    """지정된 Tool 이름과 파라미터로 MCP 서버의 Tool을 호출하고 결과를 출력합니다."""

    # 서버 실행 설정: 현재 디렉토리의 SERVER_SCRIPT_FILENAME을 python으로 실행
    server_params = StdioServerParameters(
        command=sys.executable, # 현재 사용 중인 파이썬 인터프리터 사용
        args=[SERVER_SCRIPT_FILENAME],
        env=None, # 필요시 환경 변수 전달 가능 (예: {'PYTHONPATH': '.'})
    )

    print(f"--- MCP 서버 Tool 호출 요청 ---")
    print(f"   Tool: {tool_name}")
    print(f"   Arguments: {json.dumps(arguments, indent=2, ensure_ascii=False)}") # 인자 예쁘게 출력

    try:
        # stdio_client를 사용하여 서버 프로세스 시작 및 연결
        async with stdio_client(server_params) as (read, write):
            # ClientSession 생성
            async with ClientSession(read, write) as session:
                # 서버와 초기 핸드셰이크 수행
                await session.initialize()
                logger.info("MCP 서버와 연결 초기화 완료.")

                # (선택 사항) 사용 가능한 툴 목록 확인
                try:
                    tools_info = await session.list_tools()
                    available_tools = [tool.name for tool in tools_info.tools] if hasattr(tools_info, 'tools') else []
                    logger.info(f"서버에서 사용 가능한 Tools: {available_tools}")

                    # 요청된 Tool이 서버에 있는지 확인 (선택적이지만 권장)
                    if tool_name not in available_tools:
                        logger.warning(f"경고: 요청된 Tool '{tool_name}'이 서버의 사용 가능 목록에 없습니다. 호출을 시도합니다.")
                        raise ValueError(f"오류: 서버에서 '{tool_name}' Tool을 찾을 수 없습니다.")

                except Exception as e:
                    logger.warning(f"사용 가능한 Tool 목록 조회 중 오류 발생: {e}")


                # 지정된 Tool 호출
                logger.info(f"'{tool_name}' Tool 호출 중...")
                result = await session.call_tool(tool_name, arguments=arguments)
                logger.debug(f"Tool 호출 원시 결과: {result}") # 디버깅 시 상세 결과 확인

                # 결과 출력
                print("\n--- Tool 호출 결과 ---")
                if hasattr(result, 'content') and result.content:
                    # 결과 내용이 여러 개일 수 있으므로 반복 처리
                    for content_item in result.content:
                        if hasattr(content_item, 'text'):
                            # JSON 형식의 텍스트일 경우 파싱하여 예쁘게 출력 시도
                            try:
                                parsed_json = json.loads(content_item.text)
                                print(json.dumps(parsed_json, indent=2, ensure_ascii=False))
                            except json.JSONDecodeError:
                                # JSON 파싱 실패 시 원본 텍스트 출력
                                print(content_item.text)
                        else:
                            # text 속성이 없는 경우 객체 자체 출력
                            print(content_item)
                elif hasattr(result, 'isError') and result.isError:
                    print("오류 응답:")
                    # isError가 True일 때 content가 있을 수 있음
                    if hasattr(result, 'content') and result.content:
                        for content_item in result.content:
                            if hasattr(content_item, 'text'):
                                print(content_item.text)
                            else:
                                print(content_item)
                    else: # 오류지만 content가 없는 경우
                        print("오류가 발생했으나 상세 내용이 없습니다.")

                else:
                    # 예상치 못한 응답 형식
                    print("예상치 못한 응답 형식:")
                    print(result)

    except Exception as e:
        print(f"\n--- 클라이언트 오류 발생 ---")
        print(f"   오류 유형: {type(e).__name__}")
        print(f"   오류 메시지: {e}")

if __name__ == "__main__":
    # 터미널 인자 파싱
    if len(sys.argv) < 2:
        print(f"사용법: uv run client.py <tool_name> [param1=value1] [param2=value2] ...")
        print("\n사용 가능한 Tool 이름 예시:")
        print("  list_emails, search_emails, send_email, modify_email,")
        print("  list_events, create_event, update_event, delete_event")
        print("\n파라미터 형식:")
        print("  key=value (띄어쓰기 없이)")
        print("  배열 파라미터 (예: attendees): attendees=email1@example.com,email2@example.com")
        print("\n예시:")
        print(f"  uv run client.py list_emails max_results=5 query=is:unread")
        print(f"  uv run client.py search_emails query=from:test@example.com")
        print(f"  uv run client.py send_email to=test@example.com subject=테스트메일 body=안녕하세요.")
        print(f"  uv run client.py modify_email id=MESSAGE_ID remove_labels=INBOX add_labels=ARCHIVED")
        print(f"  uv run client.py list_events time_min=2025-05-01T00:00:00+09:00 time_max=2025-05-02T23:59:59+09:00 max_results=5")
        print(f"  uv run client.py create_event summary=회의 start=2025-05-02T10:00:00+09:00 end=2025-05-02T11:00:00+09:00 attendees=user1@example.com,user2@example.com")
        print(f"  uv run client.py update_event event_id=EVENT_ID summary=새로운회의 start=2025-05-02T10:00:00+09:00 end=2025-05-02T11:00:00+09:00 attendees=user1@example.com,user2@example.com")
        print(f"  uv run client.py delete_event event_id=EVENT_ID")
        print(f"  uv run client.py search_google query=python")
        print(f"  uv run client.py read_gdrive_file file_id=1234567890")
        print(f"  uv run client.py search_gdrive query=python")
        sys.exit(1)

    tool_name = sys.argv[1]
    arguments: Dict[str, Any] = {}

    # 추가 인자 파싱 (key=value)
    if len(sys.argv) > 2:
        for arg in sys.argv[2:]:
            if "=" in arg:
                key, value = arg.split("=", 1)
                key = key.strip()
                value = value.strip()

                # 배열 형태의 파라미터 처리 (쉼표로 구분)
                # 서버의 Pydantic 모델에서 List 타입으로 정의된 필드 이름을 여기에 추가
                array_param_keys = ['addLabels', 'removeLabels', 'attendees']
                if key in array_param_keys:
                    # 쉼표로 분리하고 각 항목의 앞뒤 공백 제거
                    arguments[key] = [item.strip() for item in value.split(',') if item.strip()]
                # 숫자형 파라미터 처리 (예: maxResults)
                elif key in ['maxResults'] and value.isdigit():
                    arguments[key] = int(value)
                # 그 외 일반 문자열 파라미터
                else:
                    arguments[key] = value
            else:
                print(f"경고: 잘못된 파라미터 형식 무시됨 - '{arg}'. 'key=value' 형식을 사용하세요.")

    # 비동기 함수 실행
    try:
        asyncio.run(run_tool_call(tool_name, arguments))
    except KeyboardInterrupt:
        logger.info("사용자에 의해 클라이언트 실행이 중단되었습니다.")
