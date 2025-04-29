import os
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from flask import session, redirect, url_for, request

from models.user import get_or_create_user


CLIENT_SECRETS_FILE = "client_secrets.json"  
SCOPES = [
    'https://www.googleapis.com/auth/userinfo.profile', 
    'https://www.googleapis.com/auth/userinfo.email',
    "openid"
    ]

def create_google_flow():
    """
    יוצר אובייקט Flow להתחברות עם גוגל.
    """
    flow = Flow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
    flow.redirect_uri = url_for('callback', _external=True)
    return flow

def login():
    """
    מפנה את המשתמש להתחברות עם גוגל.
    """
    flow = create_google_flow()
    authorization_url, state = flow.authorization_url(access_type='offline', include_granted_scopes='true')
    session['state'] = state
    return redirect(authorization_url)

def callback():
    """
    טפל בחזרה מ-Google אחרי שהמשתמש אישר את ההתחברות.
    """
    flow = create_google_flow()
    flow.redirect_uri = url_for('callback', _external=True)
    try:
        
        authorization_response = request.url
        flow.fetch_token(authorization_response=authorization_response)
    except Exception as e:
        return f"שגיאה בקבלת פרטי המשתמש: {str(e)}"

        return "שגיאה בקבלת הרשאות מגוגל. נסה שוב מאוחר יותר."
    
    credentials = flow.credentials
    session['credentials'] = credentials_to_dict(credentials)

    # ⬇️ הבאת פרטי המשתמש
    try:
        service = build('oauth2', 'v2', credentials=credentials)
        user_info = service.userinfo().get().execute()
    except Exception as e:
        print("שגיאה בזמן קבלת פרטי המשתמש:", e)
        return f"שגיאה בקבלת פרטי המשתמש: {str(e)}"

    if not user_info:
        print(user_info)
        return "שגיאה בקבלת פרטי המשתמש מגוגל. נסה להתחבר שוב."
   
    # ⬇️ יצירת המשתמש אם צריך והבאתו מה-DB
    name = user_info.get('name')
    email = user_info.get('email')
    
    if not email:
         return "לא התקבלו נתוני משתמש. נסה שוב."

    user = get_or_create_user(name, email)

    # ⬇️ שמירת המשתמש ב-session כולל ID מה-DB
    session['user'] = {
        'id': user.id,
        'name': user.name,
        'email': user.email
    }

    return redirect(url_for('profile'))


def credentials_to_dict(credentials):
    """
    ממיר את ה-credentials לדיקשנרי שנשמר ב-session.
    """
    return {'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': credentials.scopes}