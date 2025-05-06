import os
import base64
import json
import logging
from logging.handlers import RotatingFileHandler, SysLogHandler
import datetime
import io
from typing import List, Optional, Dict, Any, Union
from email.mime.text import MIMEText

# pydantic import
from pydantic import BaseModel, Field, EmailStr
from dotenv import load_dotenv

# Google API 관련 import
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

# mcp.server.fastmcp 관련 import
from mcp.server.fastmcp import FastMCP

# --- 환경 변수 로드 ---
load_dotenv()
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REFRESH_TOKEN = os.getenv("GOOGLE_REFRESH_TOKEN")
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
GOOGLE_CSE_ID = os.getenv('GOOGLE_CSE_ID')
TOKEN_FILE = 'token.json' # 토큰 저장 파일

# --- 로깅 설정 ---
# 로그 레벨 및 로깅 방식 환경 변수에서 가져오기
LOG_LEVEL = os.getenv('LOG_LEVEL', 'DEBUG').upper()
LOG_TO_FILE = os.getenv('LOG_TO_FILE', 'true').lower() == 'true'
LOG_TO_SYSLOG = os.getenv('LOG_TO_SYSLOG', 'false').lower() == 'true'
SYSLOG_ADDRESS = os.getenv('SYSLOG_ADDRESS', '/dev/log')  # Unix 시스템의 기본값
SYSLOG_FACILITY = os.getenv('SYSLOG_FACILITY', 'local0')

# 로그 디렉토리 생성
log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "google_toolbox.log")

# 로거 설정
logger = logging.getLogger(__name__)
logger.setLevel(getattr(logging, LOG_LEVEL))
logger.handlers = []  # 기존 핸들러 제거

# 포맷터 설정
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# 파일 로깅 설정 (기본값)
if LOG_TO_FILE:
    # 파일 핸들러 설정 (5MB 크기 제한, 최대 5개 백업 파일)
    file_handler = RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=5)
    file_handler.setLevel(getattr(logging, LOG_LEVEL))
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.info("파일 로깅 활성화. 로그 파일: %s", log_file)

# 시스템 로그 설정 (옵션)
if LOG_TO_SYSLOG:
    try:
        # 시스템에 따라 적절한 주소 선택
        if os.path.exists(SYSLOG_ADDRESS):  # Unix 소켓
            syslog_handler = SysLogHandler(address=SYSLOG_ADDRESS, facility=SYSLOG_FACILITY)
        else:  # 네트워크 소켓 (host, port)
            if ':' in SYSLOG_ADDRESS:
                host, port = SYSLOG_ADDRESS.split(':')
                syslog_handler = SysLogHandler(address=(host, int(port)), facility=SYSLOG_FACILITY)
            else:
                # 기본 포트 (514) 사용
                syslog_handler = SysLogHandler(address=(SYSLOG_ADDRESS, 514), facility=SYSLOG_FACILITY)
        
        syslog_handler.setLevel(getattr(logging, LOG_LEVEL))
        syslog_handler.setFormatter(formatter)
        logger.addHandler(syslog_handler)
        logger.info("시스템 로깅 활성화. 주소: %s, 시설: %s", SYSLOG_ADDRESS, SYSLOG_FACILITY)
    except Exception as e:
        print(f"시스템 로그 설정 중 오류 발생: {e}")
        # 시스템 로그 설정에 실패하면 콘솔 출력으로 대체
        console_handler = logging.StreamHandler()
        console_handler.setLevel(getattr(logging, LOG_LEVEL))
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        logger.error("시스템 로그 설정 실패. 콘솔 출력으로 대체. 오류: %s", str(e))

# 항상 콘솔 출력 추가 (디버깅 목적)
# 개발 환경 또는 환경 변수로 제어 가능
if os.getenv('LOG_TO_CONSOLE', 'true').lower() == 'true':
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, LOG_LEVEL))
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

logger.info("로깅 설정 완료. 레벨: %s", LOG_LEVEL)

# --- Google API 스코프 ---
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/drive.file',
    'https://www.googleapis.com/auth/drive.readonly',
]

# --- Google 인증 함수 ---
def get_google_credentials() -> Optional[Credentials]:
    """
    Google API 접근을 위한 인증 정보를 가져옵니다.
    기존 token.json 파일이 있으면 로드하고, 만료 시 리프레시합니다.
    없거나 유효하지 않으면 None을 반환합니다 (초기 인증 필요).
    """
    creds = None
    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, 'r') as token:
                creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        except Exception as e:
            logger.error(f"토큰 파일 로딩 오류: {e}")
            creds = None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("Google API 자격 증명 갱신 중.")
            try:
                creds.refresh(Request())
                with open(TOKEN_FILE, 'w') as token:
                    token.write(creds.to_json())
                logger.info("자격 증명 갱신 및 저장 완료.")
            except Exception as e:
                logger.error(f"토큰 갱신 실패: {e}")
                return None
        elif GOOGLE_REFRESH_TOKEN and GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET:
            logger.info("환경 변수의 리프레시 토큰 사용 중.")
            try:
                creds = Credentials(
                    token=None,
                    refresh_token=GOOGLE_REFRESH_TOKEN,
                    token_uri='https://oauth2.googleapis.com/token',
                    client_id=GOOGLE_CLIENT_ID,
                    client_secret=GOOGLE_CLIENT_SECRET,
                    scopes=SCOPES
                ) 
                creds.refresh(Request())
                with open(TOKEN_FILE, 'w') as token:
                    token.write(creds.to_json())
                logger.info("리프레시 토큰으로 자격 증명 얻고 저장 완료.")
            except Exception as e:
                logger.error(f"리프레시 토큰으로 토큰 얻기 실패: {e}")
                return None
        else:
            logger.error("유효한 자격 증명 또는 리프레시 토큰을 찾을 수 없습니다. 수동 인증이 필요합니다.")
            return None

    return creds

# --- MCP 서버 인스턴스 생성 ---
mcp = FastMCP(
    name="py-mcp-google-toolbox",
    version="0.1.0",
    description="MCP Server for interacting with Google (Gmail, Calendar, Drive, Custom Search, etc.)"
)


# --- Tool 구현 함수 ---

def _get_email_body(payload: Dict[str, Any]) -> str:
    """Helper function to extract plain text body from email payload."""
    # (Helper function 내용은 변경 없음)
    if not payload:
        return "(No body content)"
    if 'parts' in payload:
        for part in payload['parts']:
            if part['mimeType'] == 'text/plain' and 'body' in part and 'data' in part['body']:
                return base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
        for part in payload['parts']:
            if part['mimeType'] == 'multipart/alternative' and 'parts' in part:
                for sub_part in part['parts']:
                    if sub_part['mimeType'] == 'text/plain' and 'body' in sub_part and 'data' in sub_part['body']:
                        return base64.urlsafe_b64decode(sub_part['body']['data']).decode('utf-8')
    if 'body' in payload and 'data' in payload['body']:
        mime_type = payload.get('mimeType', 'text/plain')
        if 'text/plain' in mime_type:
            return base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8')
    return "(Could not extract plain text body)"

# --- MCP Resource 정의 ---
@mcp.resource(
  uri='google://available-google-tools', 
  name="available-google-tools", 
  description="Returns a list of Google search categories available on this MCP server."
)
async def get_available_google_tools() -> List[str]:
    """Returns a list of Google search categories available on this MCP server."""
    available_google_tools = [
        "list_emails", "search_emails", "send_email", "modify_email",
        "list_events", "create_event", "update_event", "delete_event",
        "search_google", "read_gdrive_file", "search_gdrive"
    ]
    logger.info(f"Resource 'get_available_google_tools' 호출됨. 반환: {available_google_tools}")
    return available_google_tools

# `@mcp.tool` 데코레이터를 사용하여 Tool 정의
@mcp.tool(
    name="list_emails",
    description="List recent emails from Gmail inbox",
)
async def list_emails(query: str, max_results: int = 10) -> List[Dict[str, Any]]:
    """
    List recent emails from Gmail inbox
    
    Args:
        query (str): Search query to filter emails
        max_results (int): Maximum number of emails to return (default: 10)
    
    Returns:
        List[Dict[str, Any]]: List of email details
    """
    creds = get_google_credentials()
    if not creds:
        return "Google authentication failed."

    try:
        service = build('gmail', 'v1', credentials=creds)
        results = service.users().messages().list(
            userId='me',
            maxResults=max_results,
            q=query or ""
        ).execute()

        messages = results.get('messages', [])
        email_details = []
        for msg in messages:
            msg_data = service.users().messages().get(userId='me', id=msg['id'], format='metadata', metadataHeaders=['Subject', 'From', 'Date']).execute()
            headers = {h['name']: h['value'] for h in msg_data.get('payload', {}).get('headers', [])}
            email_details.append({
                'id': msg['id'],
                'threadId': msg.get('threadId'),
                'subject': headers.get('Subject', '(No Subject)'),
                'from': headers.get('From'),
                'date': headers.get('Date'),
                'snippet': msg_data.get('snippet'),
            })

        # CallToolResponse 반환 (MCP 표준)
        return email_details

    except HttpError as error:
        logger.error(f"API 오류 발생: {error}")
        return f"Gmail API 오류: {error.resp.status} - {error.content.decode()}"
    except Exception as e:
        logger.exception("이메일 목록 조회 중 오류:")
        return f"예상치 못한 오류 발생: {str(e)}"


@mcp.tool(
    name="search_emails",
    description="Search emails with advanced query",
)
async def search_emails(query: str, max_results: int = 10) -> List[Dict[str, Any]]:
    """
    Search emails with advanced query
    
    Args:
        query (str): Gmail search query (e.g., "from:example@gmail.com has:attachment")
        max_results (int): Maximum number of emails to return (default: 10)
    
    Returns:
        List[Dict[str, Any]]: List of email details
    """
    creds = get_google_credentials()
    if not creds:
        return "Google authentication failed."

    try:
        service = build('gmail', 'v1', credentials=creds)
        results = service.users().messages().list(
            userId='me',
            maxResults=max_results,
            q=query
        ).execute()

        messages = results.get('messages', [])
        email_details = []
        for msg in messages:
            msg_full = service.users().messages().get(userId='me', id=msg['id'], format='full').execute()
            payload = msg_full.get('payload', {})
            headers = {h['name']: h['value'] for h in payload.get('headers', [])}
            body = _get_email_body(payload)
            email_details.append({
                'id': msg['id'],
                'threadId': msg.get('threadId'),
                'subject': headers.get('Subject', '(No Subject)'),
                'from': headers.get('From'),
                'to': headers.get('To'),
                'date': headers.get('Date'),
                'body': body,
                'labels': msg_full.get('labelIds', []),
                'snippet': msg_full.get('snippet'),
            })

        return email_details

    except HttpError as error:
        logger.error(f"API 오류 발생: {error}")
        return f"Gmail API 오류: {error.resp.status} - {error.content.decode()}"
    except Exception as e:
        logger.exception("이메일 검색 중 오류:")
        return f"예상치 못한 오류 발생: {str(e)}"


@mcp.tool(
    name="send_email",
    description="Send a new email",
)
async def send_email(to: EmailStr, subject: str, body: str, cc: Optional[EmailStr] = None, bcc: Optional[EmailStr] = None) -> str:
    """
    Send a new email
    
    Args:
        to (str): Recipient email address
        subject (str): Email subject
        body (str): Email body (can include HTML)
        cc (str, optional): CC recipient email address (comma-separated)
        bcc (str, optional): BCC recipient email address (comma-separated)
    
    Returns:
        str: Success message
    """
    creds = get_google_credentials()
    if not creds:
        return "Google authentication failed."

    try:
        service = build('gmail', 'v1', credentials=creds)
        message = MIMEText(body)
        message['to'] = to
        message['subject'] = subject
        if cc:
            message['cc'] = cc
        if bcc:
            message['bcc'] = bcc

        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        create_message = {'raw': encoded_message}

        send_message = service.users().messages().send(userId='me', body=create_message).execute()
        logger.info(f"메시지 ID: {send_message['id']} 발송 완료.")
        return f"이메일 발송 성공. 메시지 ID: {send_message['id']}"

    except HttpError as error:
        logger.error(f"API 오류 발생: {error}")
        return f"Gmail API 오류: {error.resp.status} - {error.content.decode()}"
    except Exception as e:
        logger.exception("이메일 발송 중 오류:")
        return f"예상치 못한 오류 발생: {str(e)}"


@mcp.tool(
    name="modify_email",
    description="Modify email labels (archive, trash, mark read/unread, etc.)",
)
async def modify_email(id: str, add_labels: Optional[List[str]] = None, remove_labels: Optional[List[str]] = None) -> str:
    """
    Modify email labels (archive, trash, mark read/unread, etc.)
    
    Args:
        id (str): Email message ID
        add_labels (array, optional): Labels to add (e.g., ['INBOX', 'UNREAD'])
        remove_labels (array, optional): Labels to remove (e.g., ['INBOX', 'SPAM'])
    
    Returns:
        str: Success message
    """
    creds = get_google_credentials()
    if not creds:
        return "Google authentication failed."

    if not add_labels and not remove_labels:
        return "add_labels 또는 remove_labels 중 하나는 제공되어야 합니다."

    try:
        service = build('gmail', 'v1', credentials=creds)
        body = {}
        if add_labels:
            body['addLabelIds'] = add_labels
        if remove_labels:
            body['removeLabelIds'] = remove_labels

        message = service.users().messages().modify(userId='me', id=id, body=body).execute()
        logger.info(f"메시지 ID: {message['id']} 수정 완료.")
        return f"이메일 수정 성공. 메시지 ID {message['id']}의 라벨 업데이트 완료."

    except HttpError as error:
        logger.error(f"API 오류 발생: {error}")
        return f"Gmail API 오류: {error.resp.status} - {error.content.decode()}"
    except Exception as e:
        logger.exception("이메일 수정 중 오류:")
        return f"예상치 못한 오류 발생: {str(e)}"


@mcp.tool(
    name="list_events",
    description="List upcoming calendar events",
)
async def list_events(time_min: Optional[str] = None, time_max: Optional[str] = None, max_results: int = 10) -> List[Dict[str, Any]]:
    """
    List upcoming calendar events
    
    Args:
        time_min (str, optional): Start time in ISO format (default: now)
        time_max (str, optional): End time in ISO format (default: now + 1 week)
        max_results (int, optional): Maximum number of events to return (default: 10)
    
    Returns:
        List[Dict[str, Any]]: List of calendar events
        
    """
    creds = get_google_credentials()
    if not creds:
        return "Google authentication failed."

    try:
        service = build('calendar', 'v3', credentials=creds)
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        time_min = time_min or now_iso
        time_max = time_max or now_iso

        events_result = service.events().list(
            calendarId='primary',
            timeMin=time_min,
            timeMax=time_max,
            maxResults=max_results,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        events = events_result.get('items', [])
        event_list = [
            {
                'id': event.get('id'),
                'summary': event.get('summary'),
                'start': event.get('start', {}).get('dateTime') or event.get('start', {}).get('date'),
                'end': event.get('end', {}).get('dateTime') or event.get('end', {}).get('date'),
                'location': event.get('location'),
                'description': event.get('description'),
            } for event in events
        ]

        return event_list

    except HttpError as error:
        logger.error(f"API 오류 발생: {error}")
        return f"Calendar API 오류: {error.resp.status} - {error.content.decode()}"
    except Exception as e:
        logger.exception("이벤트 목록 조회 중 오류:")
        return f"예상치 못한 오류 발생: {str(e)}"


@mcp.tool(
    name="create_event",
    description="Create a new calendar event",
)
async def create_event(summary: str, start: str, end: str, location: Optional[str] = None, description: Optional[str] = None, attendees: Optional[List[EmailStr]] = None) -> str:
    """
    Create a new calendar event
    
    Args:
        summary (str): Event title
        start (str): Start datetime in ISO format
        end (str): End datetime in ISO format
        location (str, optional): Event location
        description (str, optional): Event description
        attendees (array, optional): List of attendee email addresses
    
    Returns:
        str: Success message
    """
    creds = get_google_credentials()
    if not creds:
        return "Google authentication failed."

    try:
        service = build('calendar', 'v3', credentials=creds)
        # 타임존 설정 (필요시 수정 또는 자동 감지 로직 추가)
        event_tz = 'Asia/Seoul'
        event = {
            'summary': summary,
            'location': location or '' ,
            'description': description or '',
            'start': {'dateTime': start, 'timeZone': event_tz},
            'end': {'dateTime': end, 'timeZone': event_tz},
        }
        if attendees:
            event['attendees'] = [{'email': email} for email in attendees]

        logger.info(f"이벤트 생성 중: {event}")
        created_event = service.events().insert(calendarId='primary', body=event).execute()
        logger.info(f"이벤트 생성됨: {created_event.get('htmlLink')}")
        return f"이벤트 생성 성공. 이벤트 ID: {created_event['id']}"

    except HttpError as error:
        logger.error(f"API 오류 발생: {error}")
        return f"Calendar API 오류: {error.resp.status} - {error.content.decode()}"
    except Exception as e:
        logger.exception("이벤트 생성 중 오류:")
        return f"예상치 못한 오류 발생: {str(e)}"


@mcp.tool(
    name="update_event",
    description="Update an existing calendar event",
)
async def update_event(event_id: str, summary: Optional[str] = None, start: Optional[str] = None, end: Optional[str] = None, location: Optional[str] = None, description: Optional[str] = None, attendees: Optional[List[EmailStr]] = None) -> str:
    """
    Update an existing calendar event
    
    Args:
        event_id (str): Event ID to update
        summary (str, optional): New event title
        start (str, optional): New start datetime in ISO format
        end (str, optional): New end datetime in ISO format
        location (str, optional): New event location
        description (str, optional): New event description
        attendees (array, optional): New list of attendee email addresses
        
    Returns:
        str: Success message
    """
    creds = get_google_credentials()
    if not creds:
        return "Google authentication failed."

    try:
        service = build('calendar', 'v3', credentials=creds)
        event_tz = 'Asia/Seoul'

        # 기존 이벤트 정보 가져오기
        event = service.events().get(calendarId='primary', eventId=event_id).execute()

        # 입력 파라미터 기반으로 업데이트할 필드 구성
        update_payload = {}
        if summary is not None: update_payload['summary'] = summary
        if location is not None: update_payload['location'] = location
        if description is not None: update_payload['description'] = description
        if start is not None: update_payload['start'] = {'dateTime': start, 'timeZone': event_tz}
        if end is not None: update_payload['end'] = {'dateTime': end, 'timeZone': event_tz}
        if attendees is not None: update_payload['attendees'] = [{'email': email} for email in attendees]

        # 가져온 이벤트 정보에 업데이트 내용 반영 후 API 호출
        event.update(update_payload)
        updated_event = service.events().update(calendarId='primary', eventId=event_id, body=event).execute()

        logger.info(f"이벤트 업데이트됨: {updated_event.get('htmlLink')}")
        return f"이벤트 업데이트 성공. 이벤트 ID: {updated_event['id']}"

    except HttpError as error:
        logger.error(f"API 오류 발생: {error}")
        if error.resp.status == 404:
            return f"ID '{event_id}'의 이벤트를 찾을 수 없습니다."
        return f"Calendar API 오류: {error.resp.status} - {error.content.decode()}"
    except Exception as e:
        logger.exception("이벤트 업데이트 중 오류:")
        return f"예상치 못한 오류 발생: {str(e)}"


@mcp.tool(
    name="delete_event",
    description="Delete a calendar event",
)
async def delete_event(event_id: str) -> str:
    """
    Delete a calendar event
    
    Args:
        event_id (str): Event ID to delete
        
    Returns:
        str: Success message
    """
    creds = get_google_credentials()
    if not creds:
        return "Google authentication failed."

    try:
        service = build('calendar', 'v3', credentials=creds)
        service.events().delete(calendarId='primary', eventId=event_id).execute()
        logger.info(f"이벤트 삭제됨: {event_id}")
        return f"이벤트 삭제 성공. 이벤트 ID: {event_id}"

    except HttpError as error:
        logger.error(f"API 오류 발생: {error}")
        if error.resp.status == 404:
            return f"ID '{event_id}'의 이벤트를 찾을 수 없습니다."
        return f"Calendar API 오류: {error.resp.status} - {error.content.decode()}"
    except Exception as e:
        logger.exception("이벤트 삭제 중 오류:")
        return f"예상치 못한 오류 발생: {str(e)}"


@mcp.tool(
    name="search_google",
    description="Perform a Google search and return formatted results",
)
async def search_google(query: str, num_results: int = 5) -> Dict[str, Any]:
    """
    Perform a Google search and return formatted results.
    
    This function uses Google Custom Search API to search the web based on the provided query.
    It formats the results into a consistent structure and handles potential errors.
    
    Args:
        query (str): The search query string
        num_results (int, optional): Number of search results to return. Defaults to 5.
        
    Returns:
        Dict[str, Any]: A dictionary containing:
            - success (bool): Whether the search was successful
            - results (list): List of dictionaries with title, link, and snippet
            - total_results (str): Total number of results found (when successful)
            - error (str): Error message (when unsuccessful)
    """
    try:
        # Initialize Google Custom Search API
        service = build("customsearch", "v1", developerKey=GOOGLE_API_KEY)
        
        # Execute the search
        # pylint: disable=no-member
        result = service.cse().list(
            q=query,
            cx=GOOGLE_CSE_ID,
            num=num_results
        ).execute()
        
        # Format the search results
        formatted_results = []
        if "items" in result:
            for item in result["items"]:
                formatted_results.append({
                    "title": item.get("title", ""),
                    "link": item.get("link", ""),
                    "snippet": item.get("snippet", "")
                })
        
        return {
            "success": True,
            "results": formatted_results,
            "total_results": result.get("searchInformation", {}).get("totalResults", "0")
        }
    
    except HttpError as error:
        logger.error(f"API 오류 발생: {error}")
        return {
            "success": False,
            "error": f"API Error: {str(error)}",
            "results": []
        }
    except Exception as error:  # pylint: disable=broad-exception-caught
        logger.error(f"예상치 못한 오류 발생: {error}")
        return {
            "success": False,
            "error": str(error),
            "results": []
        }

@mcp.tool(
    name="read_gdrive_file",
    description="Read contents of a file from Google Drive",
)
async def read_gdrive_file(file_id: str) -> Dict[str, Any]:
    """
    Read contents of a file from Google Drive
    
    Args:
        file_id (str): ID of the file to read
    
    Returns:
        Dict[str, Any]: A dictionary containing:
            - success (bool): Whether the operation was successful
            - name (str): Name of the file
            - mime_type (str): MIME type of the file
            - content (str): Text content or base64-encoded binary content
            - is_text (bool): Whether the content is text or binary
            - error (str): Error message (when unsuccessful)
    """
    creds = get_google_credentials()
    if not creds:
        return {
            "success": False,
            "error": "Google authentication failed."
        }

    try:
        # Initialize Google Drive API service
        service = build('drive', 'v3', credentials=creds)
        
        # First get file metadata to check mime type
        file = service.files().get(
            fileId=file_id,
            fields="mimeType,name"
        ).execute()
        
        file_name = file.get('name', file_id)
        mime_type = file.get('mimeType', 'application/octet-stream')
        
        # For Google Docs/Sheets/etc we need to export
        if mime_type.startswith('application/vnd.google-apps'):
            export_mime_type = 'text/plain'  # Default
            
            # Determine appropriate export format based on file type
            if mime_type == 'application/vnd.google-apps.document':
                export_mime_type = 'text/markdown'
            elif mime_type == 'application/vnd.google-apps.spreadsheet':
                export_mime_type = 'text/csv'
            elif mime_type == 'application/vnd.google-apps.presentation':
                export_mime_type = 'text/plain'
            elif mime_type == 'application/vnd.google-apps.drawing':
                export_mime_type = 'image/png'
            
            # Export the file
            response = service.files().export(
                fileId=file_id,
                mimeType=export_mime_type
            ).execute()
            
            # Handle response based on mime type
            is_text = export_mime_type.startswith('text/') or export_mime_type == 'application/json'
            content = response if is_text else base64.b64encode(response).decode('utf-8')
            
            return {
                "success": True,
                "name": file_name,
                "mime_type": export_mime_type,
                "content": content,
                "is_text": is_text
            }
        
        # For regular files, download content
        request = service.files().get_media(fileId=file_id)
        file_content = io.BytesIO()
        downloader = MediaIoBaseDownload(file_content, request)
        
        done = False
        while not done:
            _, done = downloader.next_chunk()
        
        # Determine if content is text based on mime type
        is_text = mime_type.startswith('text/') or mime_type == 'application/json'
        content_bytes = file_content.getvalue()
        
        # Prepare response based on content type
        if is_text:
            content = content_bytes.decode('utf-8')
        else:
            content = base64.b64encode(content_bytes).decode('utf-8')
        
        logger.info(f"읽은 파일: {file_name} ({mime_type}), 크기: {len(content_bytes)} 바이트")
        
        return {
            "success": True,
            "name": file_name,
            "mime_type": mime_type,
            "content": content,
            "is_text": is_text
        }
        
    except HttpError as error:
        logger.error(f"Drive API 오류 발생: {error}")
        return {
            "success": False,
            "error": f"Google Drive API Error: {str(error)}"
        }
    except Exception as e:
        logger.exception("파일 읽기 중 오류:")
        return {
            "success": False,
            "error": f"예상치 못한 오류 발생: {str(e)}"
        }

@mcp.tool(
    name="search_gdrive",
    description="Search for files in Google Drive",
)
async def search_gdrive(query: str, page_token: Optional[str] = None, page_size: Optional[int] = 10) -> Dict[str, Any]:
    """
    Search for files in Google Drive
    
    Args:
        query (str): Name of the file to be searched for
        page_token (str, optional): Token for the next page of results
        page_size (int, optional): Number of results per page (max 100). Defaults to 10.
    
    Returns:
        Dict[str, Any]: A dictionary containing:
            - success (bool): Whether the operation was successful
            - files (list): List of files found with their metadata
            - next_page_token (str): Token for the next page of results (if available)
            - total_files (int): Total number of files found
            - error (str): Error message (when unsuccessful)
    """
    creds = get_google_credentials()
    if not creds:
        return {
            "success": False,
            "error": "Google authentication failed."
        }

    try:
        # Initialize Google Drive API service
        service = build('drive', 'v3', credentials=creds)
        
        user_query = query.strip()
        search_query = ""
        
        # If query is empty, list all files
        if not user_query:
            search_query = "trashed = false"
        else:
            # Escape special characters in the query
            escaped_query = user_query.replace("\\", "\\\\").replace("'", "\\'")
            
            # Build search query with multiple conditions
            conditions = []
            
            # Search in title
            conditions.append(f"name contains '{escaped_query}'")
            
            # If specific file type is mentioned in query, add mimeType condition
            if "sheet" in user_query.lower():
                conditions.append("mimeType = 'application/vnd.google-apps.spreadsheet'")
            elif "doc" in user_query.lower():
                conditions.append("mimeType = 'application/vnd.google-apps.document'")
            elif "presentation" in user_query.lower() or "slide" in user_query.lower():
                conditions.append("mimeType = 'application/vnd.google-apps.presentation'")
            
            search_query = f"({' or '.join(conditions)}) and trashed = false"
        
        # Set page size with limits
        if page_size is None:
            page_size = 10
        page_size = min(max(1, page_size), 100)  # Ensure between 1 and 100
        
        # Execute the search
        response = service.files().list(
            q=search_query,
            pageSize=page_size,
            pageToken=page_token,
            orderBy="modifiedTime desc",
            fields="nextPageToken, files(id, name, mimeType, modifiedTime, size)"
        ).execute()
        
        files = response.get('files', [])
        next_page_token = response.get('nextPageToken')
        
        # Format file list with additional details
        formatted_files = []
        for file in files:
            formatted_files.append({
                "id": file.get('id', ''),
                "name": file.get('name', ''),
                "mime_type": file.get('mimeType', ''),
                "modified_time": file.get('modifiedTime', ''),
                "size": file.get('size', 'N/A')
            })
        
        logger.info(f"Google Drive 검색 결과: {len(formatted_files)}개의 파일 찾음")
        
        return {
            "success": True,
            "files": formatted_files,
            "total_files": len(formatted_files),
            "next_page_token": next_page_token
        }
    
    except HttpError as error:
        logger.error(f"Drive API 오류 발생: {error}")
        return {
            "success": False,
            "error": f"Google Drive API Error: {str(error)}",
            "files": []
        }
    except Exception as e:
        logger.exception("파일 검색 중 오류:")
        return {
            "success": False,
            "error": f"예상치 못한 오류 발생: {str(e)}",
            "files": []
        }

# --- 초기 인증 확인 (서버 시작 시) ---
logger.info("초기 Google 자격 증명 확인 중...")
initial_creds = get_google_credentials()
if not initial_creds:
    logger.warning("초기 Google 자격 증명 확인 실패. 서버는 실행되지만 인증 전까지 API 호출이 실패할 수 있습니다.")
    logger.warning(".env 파일에 GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN을 설정하거나 수동 인증 흐름을 통해 token.json을 얻으세요.")
else:
    logger.info("초기 Google 자격 증명 확인 성공.")


# --- 서버 실행 ---
if __name__ == "__main__":
    logger.info("MCP 서버 실행 시작...")
    logger.info("터미널에서 'mcp dev main.py' 명령어를 사용하여 서버를 실행하는 것이 일반적입니다.")
    try:
        mcp.run()
    except AttributeError:
        logger.warning("mcp.run() 메서드를 찾을 수 없습니다. 'mcp dev main.py'를 사용하여 서버를 실행하세요.")
    except Exception as e:
        logger.exception(f"서버 실행 중 오류 발생: {e}")

