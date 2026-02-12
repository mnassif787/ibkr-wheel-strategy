"""
Custom middleware for development and cloud deployment
"""
import base64
from django.conf import settings
from django.http import HttpResponse


class VSCodeSimpleBrowserMiddleware:
    """
    Middleware to allow embedding in VS Code Simple Browser during development
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        
        # Remove restrictive headers and add permissive ones for VS Code Simple Browser
        if hasattr(response, 'headers'):
            # Remove any existing X-Frame-Options
            if 'X-Frame-Options' in response.headers:
                del response.headers['X-Frame-Options']
            
            # Add permissive Content Security Policy
            response.headers['Content-Security-Policy'] = (
                "default-src * 'unsafe-inline' 'unsafe-eval' data: blob:; "
                "frame-ancestors *; "
                "script-src * 'unsafe-inline' 'unsafe-eval'; "
                "style-src * 'unsafe-inline';"
            )
        
        return response


class BasicAuthMiddleware:
    """
    Simple HTTP Basic Auth to protect the platform when deployed online.
    Set BASIC_AUTH_USER and BASIC_AUTH_PASS in .env to enable.
    If not set, authentication is skipped (local development).
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        username = getattr(settings, 'BASIC_AUTH_USER', '')
        password = getattr(settings, 'BASIC_AUTH_PASS', '')

        # Skip auth if not configured (local dev) or for health check endpoint
        if not username or not password:
            return self.get_response(request)

        if request.path == '/health/' or request.path.startswith('/static/'):
            return self.get_response(request)

        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if auth_header:
            try:
                method, credentials = auth_header.split(' ', 1)
                if method.lower() == 'basic':
                    decoded = base64.b64decode(credentials).decode('utf-8')
                    auth_user, auth_pass = decoded.split(':', 1)
                    if auth_user == username and auth_pass == password:
                        return self.get_response(request)
            except (ValueError, Exception):
                pass

        response = HttpResponse('Authentication required', status=401)
        response['WWW-Authenticate'] = 'Basic realm="IBKR Wheel Strategy"'
        return response
