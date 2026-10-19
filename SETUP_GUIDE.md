# Setup and User Guide

Follow these steps in order. They are written for **Windows 10/11**.

---

## 1. Install the required software (one time)

| Software | Why | Download |
|---|---|---|
| **Python 3.11** | runs the backend | https://www.python.org/downloads/ (during install, tick **"Add python.exe to PATH"**) |
| **Node.js (LTS)** | builds the website | https://nodejs.org/ (choose the LTS version) |
| **Tesseract OCR** *(optional)* | reads photos of lab reports | https://github.com/UB-Mannheim/tesseract/wiki (keep the default install folder) |

To check that Python and Node are installed, open **Command Prompt** and type:

```
python --version
node --version
```

Both should print a version number.

---

## 2. Download the project

**Option A: ZIP (easiest)**
1. On the GitHub page, click the green **Code** button, then **Download ZIP**.
2. Right-click the downloaded ZIP and choose **Extract All**.
3. Open the extracted folder.

**Option B: Git**
```
git clone <repository-url>
cd <repository-folder>
```

---

## 3. Install the project (one time)

Double-click **`setup.bat`** in the project folder. It will:

- create a Python virtual environment and install the backend packages
- create the settings file `backend\.env` from `backend\.env.example`
- install and build the website

It takes about 5–10 minutes the first time. Wait until you see **"Setup done"**.

---

## 4. Add your AI API key

The app uses Google Gemini, which has a free key.
Without a key the app still works, but it uses simpler built-in rules instead of AI.

1. Go to **https://aistudio.google.com/apikey**, sign in with a Google account and click **Create API key**. Copy the key.
2. Open the project folder, then the **`backend`** folder.
3. Open the file **`.env`** with Notepad (right-click → *Open with* → *Notepad*).
   If you don't see `.env`, copy `.env.example`, rename the copy to `.env`, and open that.
4. Find this line:
   ```
   GEMINI_API_KEY=
   ```
   Paste your key after the `=` sign, with no spaces or quotes:
   ```
   GEMINI_API_KEY=your-key-here
   ```
5. Save the file and restart the app.

*Optional backup:* get a free Groq key at https://console.groq.com/keys and put it in `GROQ_API_KEY=` the same way.

> 🔒 **Never share or upload `backend\.env`.** It holds your private key, and `.gitignore` already stops it from being uploaded to GitHub.

---

## 5. Start the app

Double-click **`start.bat`**. A black window opens (this is the server; keep it open), and your browser opens **http://127.0.0.1:8000**.

- The **first start takes 1–3 minutes**, because it downloads a small AI search model (about 80 MB) once.
- To **stop** the app, close the black window (or press `Ctrl + C` in it).

---

## 6. How to use the app

1. **Create an account:** click *New here? Create an account*, then enter an email and a password (at least 8 characters).
2. **Fill in your profile:** name, age, sex, conditions, allergies, current medicines, diet type, meal and sleep times, and emergency contact.
   This information is used to keep medicines and foods safe for you.
3. **Start a new health check:** describe the problem, how long you've had it, and how bad it is (1–10).
   - If you mention a danger sign (for example chest pain or difficulty breathing), the **emergency screen** opens with first-aid steps and call buttons.
4. **Answer the follow-up questions:** the AI asks a few questions at a time. Answer what you can, then click *Next*.
5. **Upload a lab report** *(optional, or when the app suggests tests)*: choose a PDF or a photo. The values are read and flagged.
   To try it, use the sample report in `backend\demo\sample_cbc_report.pdf`.
6. Click **Analyse now**. In about 20–30 seconds you get your report, with these tabs:
   - **Possible causes:** conditions with confidence and reasoning
   - **Lab findings:** each value and what it means
   - **Medicines & schedule:** medicine information for your doctor to review, plus a daily timetable
   - **7-day diet chart:** *With medicines* or *Natural (no medicine)*, where offered
   - **Price comparison:** type a medicine (for example `Dolo 650`) to compare live prices on 4 pharmacy websites
   - **Full report:** your answers, references and the steps each agent took
7. Click **Download PDF report** to save or print the full report.
8. Other pages:
   - **Emergency:** first-aid guides and call buttons
   - **Privacy:** your activity log, and permanent account deletion

### Create a ready-made demo patient (optional)

With the app running, open Command Prompt in the `backend` folder and run:
```
.venv\Scripts\python scripts\make_demo.py
```
Then log in as **demo.patient@healthassist.com** with password **demo1234**. A complete report is already there.

---

## 7. Troubleshooting

| Problem | Fix |
|---|---|
| `'python' is not recognized` | Reinstall Python and tick **Add python.exe to PATH** |
| `'npm' is not recognized` | Install Node.js LTS, then reopen the window and run `setup.bat` again |
| Dashboard says *"AI model not connected"* | Add your key to `backend\.env` (step 4) and restart `start.bat` |
| AI answers are slow or fail sometimes | The free Gemini tier gets busy. The app retries other models automatically, or falls back to rules |
| Photo reports are not read | Install Tesseract OCR (step 1), or add a Gemini key so it can read the image instead |
| `address already in use` / port 8000 busy | Close the other app window that is already running, then start again |
| Some pharmacy shows *Not found* | That site didn't list the medicine or was busy. Click **Check again**, or use its **Search** link |

---

## 8. For developers

- Development mode, which reloads automatically when you change code: double-click **`dev.bat`**. The API runs on :8000 and the website on :5173.
- Run the tests: `cd backend` then `.venv\Scripts\python -m pytest tests -q`
- To use PostgreSQL instead of SQLite, set `DATABASE_URL` in `backend\.env`.
- To add more medical knowledge, put `.md` or `.txt` files in `backend\knowledge_base\`. They are indexed on the next start.
