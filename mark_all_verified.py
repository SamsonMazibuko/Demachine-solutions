from app import app
from models import db, User

with app.app_context():
    User.query.update({User.is_verified: True})
    db.session.commit()
    print("All existing users marked as verified.") 