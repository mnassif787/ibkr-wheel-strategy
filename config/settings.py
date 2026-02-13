from pathlib import Path
import os
from decouple import config

# Build paths inside the project
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config('SECRET_KEY', default='django-insecure-dev-key-change-in-production')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = config('DEBUG', default=True, cast=bool)

ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1').split(',')

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',  # For number formatting (intcomma filter)
    
    # Third-party apps
    'tailwind',
    'django_browser_reload',
    
    # Local apps
    'apps.core',
    'apps.ibkr',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'config.middleware.VSCodeSimpleBrowserMiddleware',  # Custom middleware for VS Code
    'config.middleware.BasicAuthMiddleware',  # Password protection for online access
    'django_browser_reload.middleware.BrowserReloadMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'apps.ibkr.context_processors.health_status',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Dubai'  # GMT+4 Gulf Standard Time
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
# Use WhiteNoise storage without manifest (to avoid missing file errors)
STATICFILES_STORAGE = 'whitenoise.storage.CompressedStaticFilesStorage'

# Media files
MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Tailwind CSS
TAILWIND_APP_NAME = 'theme'
INTERNAL_IPS = ['127.0.0.1']

# Email configuration (Resend)
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend' if DEBUG else 'resend.django.EmailBackend'
RESEND_API_KEY = config('RESEND_API_KEY', default='')
DEFAULT_FROM_EMAIL = config('EMAIL_FROM', default='noreply@localhost')
SERVER_EMAIL = DEFAULT_FROM_EMAIL

# IBKR Configuration
IBKR_HOST = config('IBKR_HOST', default='127.0.0.1')
IBKR_PORT = config('IBKR_PORT', default=7497, cast=int)
IBKR_CLIENT_ID = config('IBKR_CLIENT_ID', default=1, cast=int)
IBKR_PAPER_TRADING = config('IBKR_PAPER_TRADING', default=True, cast=bool)

# IB Gateway Docker Configuration (used when running in containers)
IBKR_USERNAME = config('IBKR_USERNAME', default='')
IBKR_PASSWORD = config('IBKR_PASSWORD', default='')
IBKR_TRADING_MODE = config('IBKR_TRADING_MODE', default='paper')  # 'paper' or 'live'
VNC_PASSWORD = config('VNC_PASSWORD', default='ibkrvnc')

# Application Settings
SITE_NAME = config('SITE_NAME', default='IBKR Wheel Strategy')
SITE_URL = config('SITE_URL', default='http://localhost:8000')

# Allow embedding in VS Code Simple Browser (development only)
if DEBUG:
    # Disable security middleware restrictions for development
    SECURE_CROSS_ORIGIN_OPENER_POLICY = None
    SECURE_REFERRER_POLICY = None

# Ngrok / Reverse Proxy support
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in config('CSRF_TRUSTED_ORIGINS', default='').split(',')
    if origin.strip()
] or [
    'https://*.ngrok-free.app',
    'https://*.ngrok.io',
    'http://localhost:8000',
    'http://127.0.0.1:8000',
]
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True

# Basic Auth for cloud deployment (set in .env to enable password protection)
# Leave empty to disable (local development)
BASIC_AUTH_USER = config('BASIC_AUTH_USER', default='')
BASIC_AUTH_PASS = config('BASIC_AUTH_PASS', default='')
