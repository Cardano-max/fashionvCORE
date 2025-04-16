import os
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
load_dotenv()

class Config:
    """Base configuration."""
    
    # Flask settings
    SECRET_KEY = os.environ.get('SECRET_KEY', 'your_secret_key_here')
    DEBUG = False
    TESTING = False
    
    # SQLAlchemy settings
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///tryontrend.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Upload settings
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
    RESULTS_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB max upload size
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
    
    # Try-on settings
    HUGGINGFACE_URL = os.environ.get('HUGGINGFACE_URL', 'https://huggingface.co/spaces/Kwai-Kolors/Kolors-Virtual-Try-On')
    
    # Stripe settings
    STRIPE_PUBLIC_KEY = os.environ.get('STRIPE_PUBLIC_KEY', 'your_stripe_public_key')
    STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY', 'your_stripe_secret_key')
    
    # Mail settings
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() in ['true', 'on', '1']
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', 'noreply@tryontrend.com')


class DevelopmentConfig(Config):
    """Development configuration."""
    
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///fashioncore_dev.db'


class TestingConfig(Config):
    """Testing configuration."""
    
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///fashioncore_test.db'
    WTF_CSRF_ENABLED = False


class ProductionConfig(Config):
    """Production configuration."""
    
    # Use secure cookie for sessions
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    
    # Use a strong secret key in production
    SECRET_KEY = os.environ.get('SECRET_KEY', 'this_should_be_changed_in_production')


# Dictionary with different configuration environments
config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}

# Function to get the current configuration
def get_config():
    """Return the appropriate configuration object based on the environment."""
    config_name = os.environ.get('FLASK_CONFIG', 'default')
    return config[config_name]