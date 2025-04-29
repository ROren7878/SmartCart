from flask import Flask, jsonify, render_template, session, redirect, url_for, request, make_response
from datetime import date, timedelta, datetime
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import base64
import io
from bs4 import BeautifulSoup
import csv
import os
from collections import defaultdict
import urllib.parse
from dotenv import load_dotenv

import google_auth
from googleapiclient.discovery import build
import google.oauth2.credentials


from werkzeug.exceptions import BadRequest
#import פנימיים
from config import app, db
from models import User, Buy
from models.user import get_or_create_user
from models.buy import add_buy

# יצירת טבלאות במסד נתונים
with app.app_context():
    db.create_all()

# הגדרת מפתח סודי
load_dotenv()
app.secret_key = os.getenv('FLASK_SECRET_KEY', )

#יצירת משתנה שיכיל את השנה הנוכחית
@app.context_processor
def inject_now():
    return {'current_year': datetime.now().year}
#יצירת משתנה שיכיל משתמש במהלך כל חיי השרת
@app.context_processor
def inject_user():
    return dict(user=session.get('user'))


#ניתוב ראשי - דף הבית
@app.route('/')
def index():
    if 'user' in session:
        session.pop('credentials', None)
        session.pop('user', None)
        user = session['user']
        return render_template('base.html')
    return render_template('base.html')
#ניתוב לדף לוגין
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        user_data = get_or_create_user(name, email)
        session['user'] = {
            'id': user_data.id,
            'name': user_data.name,
            'email': user_data.email
        }
        return redirect(url_for('profile'))
    return render_template('login.html')

@app.route('/login/google')
def login_google():
    return google_auth.login()

@app.route('/callback')
def callback():
    return google_auth.callback()
#ניתוב התנתקות
@app.route('/logout')
def logout():
    session.pop('credentials', None)
    session.pop('user', None)
    return redirect(url_for('index'))
#ניתוב לדף אזור אישי
@app.route('/profile')
def profile():
    if 'user' in session:
        user_id = session['user']['id']
        user = User.query.get(user_id)

        sorted_buys = sorted(user.buys, key=lambda buy: buy.date, reverse=True)
        # קח את 6 הרכישות האחרונות
        recent_buys = sorted_buys[:6]
        
        success_message = session.pop('success_message', False)
        return render_template('profile.html', buys=recent_buys, success_message=success_message, today = date.today(), user=user, categories = Buy.categories, current_page='profile')

    return redirect(url_for('login'))
#ניתוב לטעינת רכישות נוספות
@app.route('/profile/load_more')
def load_more_buys():
    if 'user' in session:
        user_id = session['user']['id']
        user = User.query.get(user_id)
        displayed_buys_count = int(request.args.get('displayed_buys_count', 6))

        sorted_buys = sorted(user.buys, key=lambda buy: buy.date, reverse=True)
        more_buys = sorted_buys[displayed_buys_count:displayed_buys_count + 6]

        if not more_buys:
            return jsonify({'status': 'no_more', 'message': 'אין עוד רכישות'})

        return jsonify({
            'status': 'success',
            'buys': [buy.to_dict() for buy in more_buys]
        })

    return jsonify({'status': 'unauthorized'})

#ניתוב של הוספת רכישה בטופס
@app.route('/after_buy', methods=['GET', 'POST'])
def after_buy():
    if request.method == 'POST':
        if 'user' in session:  # בודק אם המשתמש מחובר
            # שולף את מזהה המשתמש מה-session
            user_id = session['user']['id']
            # שולף את תאריך הרכישה וממיר אותו לאובייקט date
            date_str = request.form['date']
            date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
            # קריאה לפונקציה להוספת רכישה
            add_buy(
                user_id,
                request.form['name'],
                int(request.form['qty']),  # המרת כמות למספר שלם
                float(request.form['price']),  # המרת מחיר למספר עם נקודה עשרונית
                request.form['category'],
                date_obj
            )
            session['success_message'] = True  # ← שמירה זמנית ב-session
            
            return jsonify({'status': 'success', 'message': 'הרכישה נוספה בהצלחה!'})
        else:
            # אם אין משתמש מחובר, מפנה לדף ההתחברות
            return jsonify({'status': 'error', 'message': 'עליך להתחבר קודם'})
    # אם יש GET, פשוט מפנים לדף פרופיל
    return redirect(url_for('login'))
#CSV ניתוב הורדת קובץ 
@app.route("/export_csv")
def export_csv():
    if 'user' in session:
        user_id = session['user']['id']
        user = User.query.get(user_id)
        buys = [buy.to_dict() for buy in user.buys]
        
        output = io.StringIO()
        if buys:
            writer = csv.DictWriter(output, fieldnames=buys[0].keys())
            writer.writeheader()
            for b in buys:
                writer.writerow(b)
        # עכשיו מקודדים את התוכן ל-bytes עם utf-8-sig
        bytes_buffer = io.BytesIO()
        bytes_buffer.write(output.getvalue().encode('utf-8-sig'))
        bytes_buffer.seek(0)

        filename = f"{user.name}_buys.csv"
        safe_filename = urllib.parse.quote(filename)

        response = make_response(bytes_buffer.read())
        response.headers['Content-Disposition'] = f'attachment; filename={safe_filename}'
        response.headers['Content-Type'] = 'text/csv; charset=utf-8'

        return response
    return redirect(url_for('login'))
#ניתוב לגרף התפלגות לפי קטגוריה
@app.route("/categories_plt")
def create_categories_plt():
    if 'user' in session:
        user_id = session['user']['id']
        user = User.query.get(user_id)
        buys = [buy.to_dict() for buy in sorted(user.buys, key=lambda buy: buy.category)
                if buy.date.month == date.today().month and buy.date.year == date.today().year]

        category_totals = defaultdict(float)
        for buy in buys:
            category = buy['category']
            total_price = buy['price'] * buy['qty']
            category_totals[category] += total_price

        df = pd.DataFrame(list(category_totals.items()), columns=['Category', 'Total'])

        # הגדרות תמיכה בעברית
        matplotlib.rcParams['font.family'] = 'Arial'  # או כל פונט עברי אחר
        matplotlib.rcParams['axes.unicode_minus'] = False

        fig, ax = plt.subplots(figsize=(6,4))

        wedges, texts, autotexts = ax.pie(
            df['Total'],
            startangle=140,
            autopct='%1.1f%%',
            textprops={'fontsize': 12}
        )

        # מקרא בעברית
        ax.legend(
            wedges, df['Category'],
            title="קטגוריות",
            loc="center left",
            bbox_to_anchor=(1, 0, 0.5, 1),
            fontsize=12,
            title_fontsize=10
        )

        ax.set_title("התפלגות רכישות לפי קטגוריות", fontsize=16, weight='bold')

        ax.axis('equal')  # עיגול עגול

        img = io.BytesIO()
        plt.savefig(img, format='png', bbox_inches='tight', dpi=100)
        plt.close(fig)
        img.seek(0)

        plot_url = base64.b64encode(img.getvalue()).decode()
        title = "התפלגות רכישות לפי קטגוריות"

        return render_template("diagrams.html", plot_url=plot_url, title=title)
    return redirect(url_for('login'))
#ניתוב התפלגות לפי חודשים
@app.route("/month_diagram")
def create_month_diagram():
    if 'user' not in session:
        return redirect('login')

    user_id = session['user']['id']
    user = User.query.get(user_id)
    buys = [buy.to_dict() for buy in sorted(user.buys , key=lambda buy:buy.date.month) if  buy.date.year == date.today().year]
    
    month_totals = defaultdict(float)
    for buy in buys:
        if isinstance(buy['date'], str) :
            buy_date = datetime.strptime(buy['date'], "%Y-%m-%d").date()
        else:
            buy_date = buy['date']
        month = buy_date.month
        total_price = buy['price'] * buy['qty']
        month_totals[month] += total_price
    
    df = pd.DataFrame(list(month_totals.items()), columns=['Month', 'Total'])

    fig, ax = plt.subplots()
    df.plot(kind='bar', x='Month', y='Total', ax=ax)
    # שמירה לקובץ זמני
    img = io.BytesIO()
    plt.savefig(img, format='png',)
    plt.close(fig)
    img.seek(0)
    
    plot_url = base64.b64encode(img.getvalue()).decode()
    title = "התפלגות רכישות לפי חודשים"
    # שליחה כ-Response
    return render_template("diagrams.html", plot_url=plot_url, title=title)
#פונקציית הגרלת תאריכים בשביל יצירת נתונים למשתמש דמה   
def random_dates(start, end, n):
    dates = []
    for _ in range(n):
        random_days = np.random.randint(0, (end - start).days)
        dates.append(start + timedelta(days=random_days))
    return dates
 #ניתוב יצירת נתונים של משתמש דמה
@app.route("/demo_profile")
def demo(): 
    if 'user' not in session:
        products_names= ["לחם", "חלב", "צלחות קטנות", "כוסות", "נעליים", "חולצה"]
        products_qty = np.random.randint(1,10,len(products_names))
        products_price = np.random.uniform(10,150,len(products_names)).round(2)
        products_category = ["מזון", "מזון", "חד פעמי", "חד פעמי", "הנעלה", "ביגוד"]
        
        start_date = datetime(2025, 1, 1)  # תחילת שנה
        end_date = datetime.today()        # היום
        products_date = random_dates(start_date, end_date, len(products_names))
                
        data = pd.DataFrame(
            {"שם": products_names,
            "כמות": products_qty,
            "מחיר": products_price,
            "קטגוריה": products_category,
            "תאריך": products_date},
            index = np.arange(1,len(products_names)+1)) 
    
        return render_template('demo.html', data = data , current_page='demo')   
    return redirect(url_for('profile')) 
#ניתוב לדף ייעול קניות
@app.route("/improve_buys")
def improve():
    if 'user' in session:
        with open("templates/other_buys.html", 'r', encoding='utf-8') as html_file:
            content = html_file.read()
            soup = BeautifulSoup(content, 'lxml')
            products = []
            for row in soup.find_all('tr'):
                name_td = row.find('td', class_="product-name")
                price_td = row.find('td', class_="product-price")
                category_td = row.find('td', class_="product-category")
            
                if name_td and price_td and category_td:
                    name = name_td.get_text(strip=True)
                    price = price_td.get_text(strip=True)
                    category = category_td.get_text(strip=True)
                    products.append((name, price, category))
                    
            user_id = session['user']['id']
            user = User.query.get(user_id)
            buys = [buy.to_dict() for buy in user.buys]
            
            cheap_products = []
            expensive_products = []
            
            for buy in buys:
                for p in products:
                    if buy['name'] == p[0]:
                        buy_price = float(str(buy['price']).replace('₪', '').replace(',', '').strip())
                        product_price = float(str(p[1]).replace('₪', '').replace(',', '').strip())
                        if buy_price > product_price:
                            cheap_products.append((buy, p))
                        else:
                            expensive_products.append((buy, p))
        return render_template('improve_buys.html', cheap_products=cheap_products, expensive_products=expensive_products, user=user, current_page='improve')
    return redirect('login')
                             
#הפעלת השרת
if __name__ == "__main__":
    app.run(debug=True)
