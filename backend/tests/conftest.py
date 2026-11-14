# Keep application startup/migrations away from the user's local database.
import os
import tempfile
os.environ['MODE'] = 'demo'
os.environ['DATABASE_URL'] = 'sqlite:///' + tempfile.mktemp(prefix='instacomment-suite-',suffix='.db')
os.environ['FRONTEND_ORIGIN'] = 'http://localhost:5173'
