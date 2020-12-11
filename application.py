import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    # Store the username of the user logged
    username = db.execute("SELECT username FROM users WHERE id= (:id)", id=int(session["user_id"]))[0]["username"]

    # Get stocks portfolio
    stocks = db.execute("SELECT * FROM portfolio WHERE username = :username ORDER BY symbol ASC", username=username)

    # List to add all totals
    total_sum = []

     # Iterate over the stocks list to append the information needed in index.html table
    for stock in stocks:
        symbol = str(stock["symbol"])
        shares = int(stock["shares"])
        name = lookup(symbol)["name"]
        price = lookup(symbol)["price"]
        total = shares * price
        stock["name"] = name
        stock["price"] = usd(price)
        stock["total"] = usd(total)
        total_sum.append(float(total))

    cash = db.execute("SELECT cash FROM users WHERE username = :username", username=username)[0]["cash"]
    total = sum(total_sum) + cash

    return render_template("index.html", stocks=stocks, cash=usd(cash), total=usd(total))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        symbol = request.form.get("symbol")
        # Store the dictionary returned from the search in a variable
        share = lookup(symbol)

        # Store the shares inputed
        quantity = int(request.form.get("shares"))

        # If the symbol searched or number of shares is invalid, return apology
        if share is None:
            return apology("invalid symbol", 400)
        elif quantity < 1:
            return apology("value must be positive integer", 400)

        # Store how much money the user has
        cash = db.execute("SELECT cash FROM users WHERE id = (:id)", id=int(session["user_id"]))

        # Store the value of purchase
        value = share["price"] * quantity

        # If the user don't have enough money, apologize
        if int(cash[0]["cash"]) < value:
            return apology("can't afford", 400)

        # Get the current user's username
        username = db.execute("SELECT username FROM users WHERE id= (:id)", id=int(session["user_id"]))[0]["username"]

        # Subtract the value of purchase from the user's cash
        db.execute("UPDATE users SET cash = cash - :value WHERE id = :uid", value=value, uid=int(session['user_id']))

        # Add the transaction to the user's history
        db.execute("INSERT INTO history (username, operation, symbol, price, shares) VALUES (:username, 'BUY', :symbol, :price, :shares)",
            username=username, symbol=share["symbol"], price=share["price"], shares=quantity)

        # Update the stock in portfolio
        updated = db.execute("UPDATE portfolio SET shares = shares + :shares WHERE username = :username AND symbol = :symbol",
            shares=quantity, username=username, symbol=share["symbol"])

        if updated != 1:
            # Add the stock to the user's portfolio if it doesn't exist
            db.execute("INSERT INTO portfolio (username, symbol, shares) VALUES (:username, :symbol, :shares)",
            username=username, symbol=share["symbol"], shares=quantity)


        # Send them to the portfolio
        return redirect("/")
    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    # Store the username of the user logged
    username = db.execute("SELECT username FROM users WHERE id= (:id)", id=int(session["user_id"]))[0]["username"]

    # Put information from 'history' into a list
    stocks = db.execute("SELECT operation, symbol, price, date, time, shares FROM history WHERE username = :username", username=username)

    # Iterate over the stocks list to append the faulty information needed in history.html table
    for stock in stocks:
        symbol = str(stock["symbol"])
        name = lookup(symbol)["name"]
        stock["name"] = name
        stock["price"] = usd(stock["price"])

    return render_template("history.html", stocks=stocks)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""

    # User reached out via POST to get quote
    if request.method == "POST":
        # Get info about stock
        share = lookup(request.form.get("symbol"))

        # If the symbol searched is invalid, return apology
        if share is None:
            return apology("invalid symbol", 400)

        # If the symbol exists, return the search
        else:
            return render_template("quoted.html", name=share["name"], price=usd(share["price"]), symbol=share["symbol"])
    else:
        return render_template("quote.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    if request.method == "POST":

        # Store the user inputs
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        # Ensure username was submitted
        if not username:
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not password or not confirmation:
            return apology("must provide password", 403)

        # Ensure passwords match
        elif password != confirmation:
            return apology("passwords should match", 403)


        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=username)

        # If username already exists, return apology
        if len(rows) != 0:
            return apology("username already exists", 403)

        # Add user to database
        db.execute("INSERT into users (username, hash) VALUES (:name, :hash)", name=username, hash=generate_password_hash(password))

        # Remember which user has registered and logged in
        id = db.execute("SELECT id FROM users WHERE username = :username",
                          username=username)

        session["user_id"] = id

        # Redirect user to home page
        return redirect("/")
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    if request.method == "POST":
        symbol = request.form.get("symbol")
        shares = int(request.form.get("shares"))

        username = db.execute("SELECT username FROM users WHERE id= (:id)", id=int(session["user_id"]))[0]["username"]

        if not symbol or lookup(symbol) is None:
            return apology("invalid symbol", 400)

        owns = db.execute("SELECT shares FROM portfolio WHERE username = :username AND symbol = :symbol", username=username, symbol=symbol)[0]["shares"]

        if shares > int(owns) or shares < 1:
            return apology("invalid shares", 400)

        value = lookup(symbol)["price"] * shares

        db.execute("UPDATE users SET cash = cash + :value WHERE id = :uid", value=value, uid=int(session['user_id']))

        # Add the transaction to the user's history
        db.execute("INSERT INTO history (username, operation, symbol, price, shares) VALUES (:username, 'SELL', :symbol, :price, :shares)",
            username=username, symbol=symbol, price=lookup(symbol)["price"], shares=shares)

        db.execute("UPDATE portfolio SET shares = shares - :shares WHERE username = :username", shares=shares, username=username)

        curr = db.execute("SELECT shares FROM portfolio WHERE username = :username", username=username)

        if int(curr[0]["shares"]) == 0:
            db.execute("DELETE FROM portfolio WHERE username = :username AND symbol = :symbol", username=username, symbol=symbol)

        return redirect("/")

    else:
        stocks = db.execute("SELECT symbol from portfolio WHERE username = :username",
                    username=db.execute("SELECT username FROM users WHERE id= (:id)", id=int(session["user_id"]))[0]["username"])
        return render_template("sell.html", symbols=[stock["symbol"] for stock in stocks])

@app.route("/leaderboard")
@login_required
def leaderboard():
    """Show leaderboard"""

    users = db.execute("SELECT username FROM users")
    user_list = [x["username"] for x in users]

    for user in user_list:
        assets(user)

    users = db.execute("SELECT username, cash, assets FROM users ORDER BY assets DESC, cash DESC")

    for user in users:
        user["assets"] = usd(user["assets"])
        user["cash"] = usd(user["cash"])


    return render_template("leaderboard.html", users=users)


def assets(username):
    cash = db.execute("SELECT cash FROM users WHERE username = :username", username=username)[0]["cash"]
    total = float(cash)

    stocks = db.execute("SELECT * FROM portfolio WHERE username = :username", username=username)

    for stock in stocks:
        symbol = str(stock["symbol"])
        shares = int(stock["shares"])
        price = lookup(symbol)["price"]
        amount = shares * price
        total += float(amount)

    db.execute("UPDATE users SET assets = :assets WHERE username = :username", assets=total, username=username)

def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
