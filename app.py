from flask import Flask, request, jsonify, render_template
from flask_socketio import SocketIO
import sqlite3
import os
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from flask import Flask
import os

app = Flask(__name__)

@app.route("/")
def home():
    return "Trading Bot Live 🚀"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
# INIT
app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# DATABASE SETUP
conn = sqlite3.connect("trades.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal TEXT,
    rr REAL,
    session TEXT,
    killzone TEXT,
    result TEXT
)
""")
conn.commit()

# AI PREDICTION
def predict():
    try:
        cursor.execute("SELECT session, killzone, rr, result FROM trades WHERE result != 'OPEN'")
        rows = cursor.fetchall()

        # Not enough data
        if len(rows) < 10:
            return 50

        df = pd.DataFrame(rows, columns=["session", "killzone", "rr", "result"])

        # Convert result to numeric
        df["result"] = df["result"].map({"WIN": 1, "LOSS": 0})

        # Drop any bad rows
        df = df.dropna()

        if df.empty:
            return 50

        df = pd.get_dummies(df)

        X = df.drop("result", axis=1)
        y = df["result"]

        if len(X) < 5:
            return 50

        model = RandomForestClassifier(n_estimators=50)
        model.fit(X, y)

        prob = model.predict_proba(X.iloc[-1:])[0][1]
        return round(prob * 100, 2)

    except Exception as e:
        print("AI ERROR:", e)
        return 50


# STATS CALCULATION
def get_stats():
    try:
        cursor.execute("SELECT result, rr FROM trades")
        rows = cursor.fetchall()

        total = len(rows)
        wins = sum(1 for r in rows if r[0] == "WIN")
        losses = sum(1 for r in rows if r[0] == "LOSS")

        winrate = (wins / total * 100) if total > 0 else 0

        pnl = 0
        for r in rows:
            if r[0] == "WIN":
                pnl += r[1]
            elif r[0] == "LOSS":
                pnl -= 1

        return {
            "total": total,
            "wins": wins,
            "losses": losses,
            "winrate": round(winrate, 2),
            "pnl": round(pnl, 2)
        }

    except Exception as e:
        print("STATS ERROR:", e)
        return {
            "total": 0,
            "wins": 0,
            "losses": 0,
            "winrate": 0,
            "pnl": 0
        }


# ROUTES

@app.route("/")
def dashboard():
    return render_template("dashboard.html")


@app.route("/stats")
def stats():
    return jsonify(get_stats())


@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        # SECURITY
        api_key = request.headers.get("x-api-key")
        if api_key != os.environ.get("API_KEY"):
            return jsonify({"error": "unauthorized"}), 401

        data = request.json

        # Validate input
        required_fields = ["signal", "rr", "session", "killzone"]
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"Missing {field}"}), 400

        prob = predict()

        # AI FILTER
        if prob < 50:
            return jsonify({"status": "blocked", "prob": prob})

        # SAVE TRADE
        cursor.execute(
            "INSERT INTO trades (signal, rr, session, killzone, result) VALUES (?, ?, ?, ?, ?)",
            (data["signal"], float(data["rr"]), data["session"], data["killzone"], "OPEN")
        )
        conn.commit()

        # EMIT LIVE UPDATE
        socketio.emit("update", {
            "prob": prob,
            "stats": get_stats()
        })

        return jsonify({"status": "accepted", "prob": prob})

    except Exception as e:
        print("WEBHOOK ERROR:", e)
        return jsonify({"error": "server error"}), 500


# RUN APP
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host="0.0.0.0", port=port)