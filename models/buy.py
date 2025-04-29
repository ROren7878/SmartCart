
from config import db
from models import User
from flask import current_app as app


class Buy(db.Model):
    __tablename__ = "buys"
    # רשימת הקטגוריות
    categories = ["מזון", "חד פעמי", "ביגוד", "הנעלה", "משחקים", "לימודים", "רכב", "קוסמטיקה", "ניקיון", "כלי בית", "מכשירי חשמל"]
    # שמות העמודות
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(50))
    qty = db.Column(db.Integer)
    price = db.Column(db.Float)
    category = db.Column(db.String(50))
    date = db.Column(db.Date) 
    
    # פונקציה שמחזירה אוביקט מסוג רכישה כמילון
    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "qty": self.qty,
            "price": self.price,
            "category": self.category,
            "date": self.date.isoformat() if self.date else None,
            "formatted_date": self.formatted_date
        }
        
    # מאפיין לחישוב שם היום בשבוע בעברית
    @property
    def formatted_date(self):
        if not self.date:
            return None
        hebrew_days = ['שני', 'שלישי', 'רביעי', 'חמישי', 'שישי', 'שבת', 'ראשון']
        day_name = hebrew_days[self.date.weekday()]
        return f"יום {day_name}, {self.date.strftime('%d/%m/%Y')}"
       
       
    #   פונקציה להוספת רכישה
def add_buy(user_id, name, qty, price, category, date):
    """ הוספת רכישה לטבלה 
    """
    with app.app_context():
        user = User.query.filter_by(id=user_id).first()
        if user:
            buy = Buy(user_id=user_id, name=name, qty=qty, price=price,category=category, date=date)
            db.session.add(buy)
            db.session.commit()
        else:
            print("User Id Is Undefined")