"""
Django settings for spa_project project.
"""

from pathlib import Path
import os

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env nếu có (dev local)
try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / '.env')
except ImportError:
    pass  # python-dotenv chưa cài — đọc từ environment variable hệ thống

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-change-this-in-production'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ['localhost', '127.0.0.1', '*']

# Application definition
INSTALLED_APPS = [
    'daphne',
    'channels',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django_extensions',
    # Cloudinary — lưu ảnh trên cloud, máy nào cũng xem được
    'cloudinary',
    'cloudinary_storage',
    # Phase 1: New empty apps (scaffolding only, no code moved yet)
    'core',
    'accounts',
    'spa_services',
    'appointments',
    'complaints',
    'admin_panel',
    'pages',  # about & Home
    # Phase 8.6+: Admin management apps
    'customers',
    'staff',
    'chat',
    # Phase 9: Reports
    'reports',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'spa_project.urls'
ASGI_APPLICATION = 'spa_project.asgi.application'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'spa_project.wsgi.application'

# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
        'TEST': {
            'NAME': ':memory:',  # Chạy test trong RAM, không tạo file, tự dọn sau khi xong
        },
        'OPTIONS': {
            'timeout': 20,
        },
    }
}

CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer',
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
LANGUAGE_CODE = 'vi'
TIME_ZONE = 'Asia/Ho_Chi_Minh'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

# Media files
# ── Cloudinary (ảnh lưu trên cloud, máy nào cũng xem được) ──────────────────
# Điền thông tin từ https://cloudinary.com → Dashboard
CLOUDINARY_STORAGE = {
    'CLOUD_NAME': os.environ.get('CLOUDINARY_CLOUD_NAME', ''),
    'API_KEY':    os.environ.get('CLOUDINARY_API_KEY', ''),
    'API_SECRET': os.environ.get('CLOUDINARY_API_SECRET', ''),
}

# Khi đã cấu hình Cloudinary: dùng cloudinary_storage làm DEFAULT_FILE_STORAGE
# Khi chưa cấu hình (CLOUD_NAME trống): fallback về local media
if CLOUDINARY_STORAGE['CLOUD_NAME']:
    DEFAULT_FILE_STORAGE = 'cloudinary_storage.storage.MediaCloudinaryStorage'
    MEDIA_URL = '/media/'   # vẫn giữ để không lỗi code cũ
else:
    # Local storage (dev chưa setup Cloudinary)
    MEDIA_URL = '/media/'
    MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Login/Logout settings
LOGIN_URL = 'accounts:login'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'

# Session - dùng DB thay vì signed_cookies để tránh giới hạn kích thước
SESSION_ENGINE = 'django.contrib.sessions.backends.db'

# ── Email — Quên mật khẩu (SendGrid API backend) ─────────────────────────────
EMAIL_BACKEND            = 'sendgrid_backend.SendgridBackend'
SENDGRID_API_KEY         = os.environ.get('SENDGRID_API_KEY')
SENDGRID_SANDBOX_MODE_IN_DEBUG = False  # gửi thật dù DEBUG=True
DEFAULT_FROM_EMAIL       = 'Spa ANA <nguyenlebaochau157@gmail.com>'

# Thời gian hiệu lực của link đặt lại mật khẩu: 15 phút (tính bằng giây)
PASSWORD_RESET_TIMEOUT = 60 * 15  # 900 giây = 15 phút
