import os
import secrets
from pathlib import Path
from dotenv import load_dotenv
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')
key_path = BASE_DIR / '.django-secret'
if not os.environ.get('DJANGO_SECRET_KEY') and not key_path.exists():
    try:
        fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as stream:
            stream.write(secrets.token_urlsafe(48))
    except FileExistsError:
        pass
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY') or key_path.read_text()
DEBUG = False
ALLOWED_HOSTS = ['localhost', '127.0.0.1', '[::1]']
INSTALLED_APPS = ['django.contrib.auth', 'django.contrib.contenttypes', 'django.contrib.sessions', 'exporter', 'retrieval']
MIDDLEWARE = ['django.middleware.security.SecurityMiddleware', 'django.contrib.sessions.middleware.SessionMiddleware', 'django.middleware.common.CommonMiddleware', 'django.middleware.csrf.CsrfViewMiddleware', 'django.contrib.auth.middleware.AuthenticationMiddleware']
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': BASE_DIR / 'db.sqlite3', 'OPTIONS': {'timeout': 30}}}
ROOT_URLCONF = 'config.urls'
TEMPLATES = [{'BACKEND': 'django.template.backends.django.DjangoTemplates', 'APP_DIRS': True, 'OPTIONS': {'context_processors': ['django.template.context_processors.request', 'django.contrib.auth.context_processors.auth']}}]
LOGIN_URL = '/login'
LOGIN_REDIRECT_URL = '/search'
LOGOUT_REDIRECT_URL = '/login'
USE_TZ = True
LANGUAGE_CODE = 'tr'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
RAG_INDEX_PATH = Path(os.environ.get('RAG_INDEX_PATH', str(BASE_DIR / 'data' / 'search.sqlite3')))
PANEL_EXPORT_ROOT = BASE_DIR / 'exports_panel'
