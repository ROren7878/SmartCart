from flask import Flask, jsonify, render_template, session, redirect, url_for, request, make_response
from datetime import date, timedelta, datetime
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import base64
import io
import csv
import os
from collections import defaultdict
import urllib.parse
from dotenv import load_dotenv
from bs4 import BeautifulSoup

from werkzeug.exceptions import BadRequest

# פנימיים
from extensions import db
from models.user import User, get_or_create_user
from models.buy import Buy, add_buy
import google_auth

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///myshop.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# אתחול מסד נתונים
db.init_app(app)
with app.app_context():
    db.create_all()

# משתנים גלובליים לתבניות
@app.context_processor
def inject_now():
    return {'current_year': datetime.now().year}

@app.context_processor
def inject_user():
    return dict(user=session.get('user'))

# דף הבית
@app.route('/')
def index():
    session.pop('credentials', None)
    return render_template('base.html')

# התחברות רגילה
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        user_data = get_or_create_user(name, email)
        session['user'] = {'id': user_data.id, 'name': user_data.name, 'email': user_data.email}
        return redirect(url_for('profile'))
    return render_template('login.html')

# התחברות עם גוגל
@app.route('/login/google')
def login_google():
    return google_auth.login()

@app.route('/callback')
def callback():
    return google_auth.callback()

# התנתקות
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# אזור אישי
@app.route('/profile')
def profile():
    if 'user' not in session:
        return redirect(url_for('login'))

    user = User.query.get(session['user']['id'])
    recent_buys = sorted(user.buys, key=lambda b: b.date, reverse=True)[:6]
    success_message = session.pop('success_message', False)

    return render_template('profile.html', buys=recent_buys, success_message=success_message, today=date.today(), user=user, categories=Buy.categories, current_page='profile')

# הוספת רכישה
@app.route('/after_buy', methods=['GET', 'POST'])
def after_buy():
    if request.method == 'POST':
        if 'user' not in session:
            return jsonify({'status': 'error', 'message': 'עליך להתחבר קודם'})

        user_id = session['user']['id']
        date_obj = datetime.strptime(request.form['date'], '%Y-%m-%d').date()

        add_buy(user_id, request.form['name'], int(request.form['qty']), float(request.form['price']), request.form['category'], date_obj)

        session['success_message'] = True
        latest_buys = sorted(User.query.get(user_id).buys, key=lambda b: b.date, reverse=True)[:6]

        return jsonify({'status': 'success', 'message': 'הרכישה נוספה בהצלחה!', 'latest_buys': [b.to_dict() for b in latest_buys]})

    return redirect(url_for('login'))

# טעינת רכישות נוספות
@app.route('/profile/load_more')
def load_more_buys():
    if 'user' not in session:
        return jsonify({'status': 'unauthorized'})

    user = User.query.get(session['user']['id'])
    displayed = int(request.args.get('displayed_buys_count', 6))
    more_buys = sorted(user.buys, key=lambda b: b.date, reverse=True)[displayed:displayed + 6]

    if not more_buys:
        return jsonify({'status': 'no_more', 'message': 'אין עוד רכישות'})

    return jsonify({'status': 'success', 'buys': [b.to_dict() for b in more_buys]})

# הורדת רכישות כ-CSV
@app.route('/export_csv')
def export_csv():
    if 'user' not in session:
        return redirect(url_for('login'))

    user = User.query.get(session['user']['id'])
    buys = [b.to_dict() for b in user.buys]

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=buys[0].keys()) if buys else None

    if writer:
        writer.writeheader()
        writer.writerows(buys)

    buffer = io.BytesIO()
    buffer.write(output.getvalue().encode('utf-8-sig'))
    buffer.seek(0)

    filename = urllib.parse.quote(f"{user.name}_buys.csv")
    response = make_response(buffer.read())
    response.headers['Content-Disposition'] = f'attachment; filename={filename}'
    response.headers['Content-Type'] = 'text/csv; charset=utf-8'

    return response

# גרף לפי קטגוריות
@app.route('/categories_plt')
def categories_plt():
    if 'user' not in session:
        return redirect(url_for('login'))

    user = User.query.get(session['user']['id'])
    buys = [b.to_dict() for b in user.buys if b.date.month == date.today().month and b.date.year == date.today().year]

    totals = defaultdict(float)
    for b in buys:
        totals[b['category']] += b['price'] * b['qty']

    df = pd.DataFrame(list(totals.items()), columns=['Category', 'Total'])

    matplotlib.rcParams['font.family'] = 'Arial'
    matplotlib.rcParams['axes.unicode_minus'] = False

    fig, ax = plt.subplots(figsize=(6, 4))
    wedges, texts, autotexts = ax.pie(df['Total'], startangle=140, autopct='%1.1f%%', textprops={'fontsize': 12})
    ax.legend(wedges, df['Category'], title="קטגוריות", loc="center left", bbox_to_anchor=(1, 0, 0.5, 1), fontsize=12, title_fontsize=10)
    ax.set_title("התפלגות רכישות לפי קטגוריות", fontsize=16, weight='bold')
    ax.axis('equal')

    img = io.BytesIO()
    plt.savefig(img, format='png', bbox_inches='tight', dpi=100)
    plt.close(fig)
    img.seek(0)

    return render_template("diagrams.html", plot_url=base64.b64encode(img.getvalue()).decode(), title="התפלגות רכישות לפי קטגוריות")

# גרף לפי חודשים
@app.route('/month_diagram')
def month_diagram():
    if 'user' not in session:
        return redirect(url_for('login'))

    user = User.query.get(session['user']['id'])
    buys = [b.to_dict() for b in user.buys if b.date.year == date.today().year]

    totals = defaultdict(float)
    for b in buys:
        buy_date = datetime.strptime(b['date'], "%Y-%m-%d").date() if isinstance(b['date'], str) else b['date']
        totals[buy_date.month] += b['price'] * b['qty']

    df = pd.DataFrame(list(totals.items()), columns=['Month', 'Total'])

    fig, ax = plt.subplots()
    df.plot(kind='bar', x='Month', y='Total', ax=ax)

    img = io.BytesIO()
    plt.savefig(img, format='png')
    plt.close(fig)
    img.seek(0)

    return render_template("diagrams.html", plot_url=base64.b64encode(img.getvalue()).decode(), title="התפלגות רכישות לפי חודשים")

# פרופיל הדגמה
@app.route('/demo_profile')
def demo_profile():
    if 'user' in session:
        return redirect(url_for('profile'))

    names = ["לחם", "חלב", "צלחות", "כוסות", "נעליים", "חולצה"]
    qtys = np.random.randint(1, 10, len(names))
    prices = np.random.uniform(10, 150, len(names)).round(2)
    categories = ["מזון", "מזון", "חד פעמי", "חד פעמי", "הנעלה", "ביגוד"]
    dates = [datetime(2025, 1, 1) + timedelta(days=np.random.randint(0, (datetime.today() - datetime(2025, 1, 1)).days)) for _ in names]

    data = pd.DataFrame({"שם": names, "כמות": qtys, "מחיר": prices, "קטגוריה": categories, "תאריך": dates})
    return render_template('demo.html', data=data, current_page='demo')

# השוואת מחירים
@app.route('/improve')
def improve_buys():
    if 'user' not in session:
        return redirect(url_for('login'))

    with open("templates/other_buys.html", encoding='utf-8') as f:
        soup = BeautifulSoup(f.read(), 'lxml')
        products = [(row.find('td', class_="product-name").text.strip(),
                     row.find('td', class_="product-price").text.strip(),
                     row.find('td', class_="product-category").text.strip())
                    for row in soup.find_all('tr') if row.find_all('td')]

    user = User.query.get(session['user']['id'])
    buys = [b.to_dict() for b in user.buys]
    cheap, expensive = [], []

    for b in buys:
        for p in products:
            if b['name'] == p[0]:
                bp = float(str(b['price']).replace('₪', '').replace(',', ''))
                pp = float(str(p[1]).replace('₪', '').replace(',', ''))
                (cheap if bp > pp else expensive).append((b, p))

    return render_template('improve_buys.html', cheap_products=cheap, expensive_products=expensive, user=user, current_page='improve')

# הרצת השרת
if __name__ == '__main__':
    app.run(debug=True)
