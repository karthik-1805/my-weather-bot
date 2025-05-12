from flask import Flask

app = Flask(__name__)

@app.route("/")
def home():
    return "Hello! This is your weather bot!"

if __name__ == "__main__":
    app.run()
