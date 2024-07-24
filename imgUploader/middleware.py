import logging
from django.conf import settings
from django.http import JsonResponse
import requests

logger = logging.getLogger(__name__)

class GoogleAuthMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Skip authentication for specific endpoints (e.g., login)
        if request.path in ['/api/google-login/']:
            return self.get_response(request)

        token = request.headers.get('Authorization')

        if not token:
            return JsonResponse({'success': False, 'error': 'No token provided'}, status=401)

        try:
            # Verify the token with Google's token info endpoint
            response = requests.get(f'https://www.googleapis.com/oauth2/v3/tokeninfo?access_token={token}')
            
            if response.status_code != 200:
                return JsonResponse({'success': False, 'error': 'Invalid token'}, status=401)
            
            idinfo = response.json()
            
            if idinfo['aud'] != settings.GOOGLE_OAUTH2_CLIENT_ID:
                return JsonResponse({'success': False, 'error': 'Wrong audience'}, status=401)
            
            request.user_info = idinfo
        except Exception as e:
            logger.error(f'Error verifying token: {str(e)}')
            return JsonResponse({'success': False, 'error': 'Error verifying token'}, status=401)

        return self.get_response(request)
