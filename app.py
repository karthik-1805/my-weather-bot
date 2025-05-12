from flask import Flask, request, render_template_string
import re
import json
import os
import requests
import openai
import smtplib
import ssl
from email.message import EmailMessage
from fpdf import FPDF


# ---------- CONFIG ----------

openai.api_key = os.getenv("OPENAI_API_KEY")
OWM_API_KEY = os.getenv("OWM_API_KEY")
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD")

# ---------- FLASK APP ----------

app = Flask(__name__)

# ---------- SYSTEM PROMPT ----------

react_system_prompt = """
You are an AI assistant that answers weather-based questions. You always follow this loop:

Thought → Action → PAUSE → Action_Response → Answer.

You can call functions to help you answer better. Your available tools are:

get_weather:
    Call this to get weather for a city.
    Example: {"function_name": "get_weather", "function_parms": {"city": "Chennai"}}

Only use a function if needed. Use Thought to decide first.

Once you receive Action_Response, write an Answer that uses the weather data to help the user decide things like:
- if they need an umbrella
- what transport they should take
- what to wear
- any activities/weather concerns
""".strip()

# ---------- LLM CALL ----------

def generate_text_basic(prompt, model="gpt-4o", system_prompt="You are a helpful AI assistant"):
    response = openai.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]
    )
    return response.choices[0].message.content

# ---------- WEATHER FUNCTION ----------

def get_weather(city):
    try:
        params = {"q": city, "appid": OWM_API_KEY, "units": "metric"}
        res = requests.get("http://api.openweathermap.org/data/2.5/weather", params=params)
        data = res.json()

        if data["cod"] != 200:
            return "unknown"

        desc = data["weather"][0]["description"]
        temp = data["main"]["temp"]
        humidity = data["main"]["humidity"]
        return f"{desc}, {temp}°C, {humidity}% humidity"
    except Exception as e:
        return "unknown"

# ---------- EMAIL FUNCTION ----------

def send_email_with_gmail(to_email, subject, body_text, file_path):
    message = EmailMessage()
    message["From"] = SENDER_EMAIL
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body_text)

    with open(file_path, "rb") as f:
        message.add_attachment(f.read(), maintype="application", subtype="pdf", filename="weather_report.pdf")

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(message)

# ---------- PDF SAVE ----------

def save_to_pdf(text, filename="weather_report.pdf"):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.multi_cell(0, 10, text)
    pdf.output(filename)

# ---------- MAIN LOGIC ----------

def handle_question(user_question, user_email):
    try:
        # Initial response
        initial = generate_text_basic(user_question, model="gpt-4o", system_prompt=react_system_prompt)
        action_json_str = re.search(r"{[\s\S]+}", initial).group(0)
        action = json.loads(action_json_str)

        if action.get("function_name") != "get_weather":
            return "Function not recognized."

        city = action["function_parms"].get("city", "the location")
        weather_result = get_weather(city)

        # Final reasoning
        followup_prompt = f"Action_Response: The weather in {city} is {weather_result}"
        final_response = generate_text_basic(followup_prompt, model="gpt-4o", system_prompt=react_system_prompt)

        match = re.search(r"Answer:\s*(.+)", final_response)
        final_answer = match.group(1).strip() if match else final_response.strip()

        save_to_pdf(final_answer)
        send_email_with_gmail(user_email, "🌦️ Your AI Weather Report", "Hi, see attached report.", "weather_report.pdf")

        return f"✅ Answer sent to {user_email}<br><br><strong>{final_answer}</strong>"

    except Exception as e:
        return f"❌ Something went wrong: {str(e)}"

# ---------- ROUTES ----------

HTML_FORM = """
<!DOCTYPE html>
<html>
<head><title>🌤️ AI Weather Assistant</title></head>
<body>
  <h2>Ask your weather question</h2>
  <form method="POST">
    <label>Weather Question:</label><br>
    <textarea name="question" rows="4" cols="50" required></textarea><br><br>
    <label>Your Email:</label><br>
    <input type="email" name="email" required><br><br>
    <input type="submit" value="Ask">
  </form>
  <br>{{ result|safe }}
</body>
</html>
"""

@app.route("/", methods=["GET", "POST"])
def home():
    result = ""
    if request.method == "POST":
        question = request.form.get("question")
        email = request.form.get("email")
        result = handle_question(question, email)
    return render_template_string(HTML_FORM, result=result)

# ---------- RUN ----------

if __name__ == "__main__":
    app.run(debug=True)
