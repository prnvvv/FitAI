from app.core.config import Settings
s = Settings()
print('DATABASE_URL:', repr(s.database_url))
print('env_file config:', s.model_config)