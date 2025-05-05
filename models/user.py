
from extensions import db
from sqlalchemy.orm import relationship
from flask import current_app as app


class User(db.Model):
    __tablename__ = 'users'
    # שמות העמודות
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50))
    email = db.Column(db.String(100),nullable=False, unique=True)
    # קישור של מפתח זר - רשימת הרכישות של כל משתמש
    buys = relationship("Buy", backref="user", lazy=True)
    
    # פונקציה שמחזירה אוביקט מסוג רכישה כמילון
    def to_dict(self):
        return{
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "buys" : [buy.to_dict() for buy in self.buys]
        }
  
    # יצירת משתמש חדש(אם לא קיים) / שליפה של משתמש קיים
def get_or_create_user(name, email):
    """התחברות - כניסה עם משתמש קיים או יצירת משתמש חדש - אם לא קיים
    """
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        if not user:
            user = User(name=name, email=email)
            db.session.add(user)
            db.session.commit()
            db.session.refresh(user)
        return user