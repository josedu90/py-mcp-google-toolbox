import os
import json
from google_auth_oauthlib.flow import InstalledAppFlow

# 필요한 권한 범위 정의
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/drive.file',
    'https://www.googleapis.com/auth/drive.readonly',
]

def get_refresh_token():
    try:
        # 현재 작업 디렉토리 기준으로 credentials.json 파일 경로 설정
        credentials_path = os.path.join(os.getcwd(), 'credentials.json')
        
        # OAuth 클라이언트 설정 및 인증
        flow = InstalledAppFlow.from_client_secrets_file(
            credentials_path, SCOPES)
        creds = flow.run_local_server(port=0)
        
        # 인증 정보 출력
        print('\nRefresh Token:', creds.refresh_token)
        print('\nClient ID:', creds._client_id)
        print('\nClient Secret:', creds._client_secret)
        
        # 인증 정보를 파일로 저장
        with open('token.json', 'w') as token_file:
            token_data = {
                'refresh_token': creds.refresh_token,
                'client_id': creds._client_id,
                'client_secret': creds._client_secret,
                'token': creds.token,
                'token_uri': creds.token_uri,
                'scopes': creds.scopes
            }
            json.dump(token_data, token_file, indent=2)
        
        print('\nCredentials saved to token.json')
    
    except Exception as error:
        print('Error getting refresh token:', error)

if __name__ == '__main__':
    get_refresh_token()
