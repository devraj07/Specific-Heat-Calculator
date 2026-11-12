# Setup guide

How to run cpcalc on a computer for the first time, how to start it on every later day, and what to do when something goes wrong. No earlier experience with Python environments is assumed.

**What you need:** a computer with internet access, Python 3.10 or newer, and about 500 MB of free disk space.

---

## 1. First time on a new computer

### Step 1: Install Python

1. Download Python from <https://www.python.org/downloads/> (any version from 3.10 up; tested on 3.12).
2. **Windows:** on the first installer screen, tick **"Add python.exe to PATH"**, then click *Install Now*.
3. Check it worked. Open a terminal (see the box below) and type:

```bash
python --version          # Windows
python3 --version         # Mac / Linux
```

You should see `Python 3.10` or higher. On Mac and Linux, use `python3` and `pip3` wherever this guide says `python` and `pip` if the short names are not found.

> **Which terminal?** On Windows use *Command Prompt*, *PowerShell* or *Windows Terminal* (they all work; only the activate command in step 4 differs). On Mac use *Terminal*. In VS Code press `Ctrl+` ` (backtick) to open its built-in terminal.

### Step 2: Get the project

**With Git** (recommended: you can update later with one command):

```bash
git clone https://github.com/YOUR-USERNAME/YOUR-REPOSITORY.git
cd YOUR-REPOSITORY
```

**Without Git:** on the GitHub page click **Code → Download ZIP**, unzip it, and open a terminal *inside the unzipped folder* (the one that contains `cpcalc/`, `README.md` and `requirements.txt`).

### Step 3: Create a virtual environment (once)

A **virtual environment** is a private folder of Python libraries for this project only. It keeps cpcalc's libraries separate from everything else on your computer, so you can install and delete freely.

```bash
python -m venv venv
```

This creates a folder called `venv`. It is not part of the project and is never uploaded to GitHub.

### Step 4: Activate it (every time you open a new terminal)

| System | Command |
|---|---|
| Windows, Command Prompt | `venv\Scripts\activate` |
| Windows, PowerShell | `venv\Scripts\Activate.ps1` |
| Mac / Linux | `source venv/bin/activate` |

Your prompt now starts with **(venv)**. That means the environment is active. (VS Code often does this for you automatically.)

### Step 5: Install the libraries (once)

```bash
pip install -r requirements.txt
```

This reads `requirements.txt` and installs NumPy, SciPy, pandas, openpyxl, Streamlit and thermo. It takes a few minutes.

### Step 6: Start the app

```bash
python -m cpcalc ui
```

Your browser opens at <http://localhost:8501>. If it does not, type that address into the browser yourself. To stop the app, click in the terminal and press `Ctrl+C`.

---

## 2. Every later day (3 steps)

```bash
cd path/to/the/project          # 1. go to the project folder
venv\Scripts\activate           # 2. activate  (Mac/Linux: source venv/bin/activate)
python -m cpcalc ui             # 3. start
```

When you are done: `Ctrl+C` to stop the app, and `deactivate` to leave the environment.

**To get the newest version** (if you used `git clone`): `git pull`, then `pip install -r requirements.txt` again.

---

## 3. What each command does

| Command | Meaning |
|---|---|
| `python -m venv venv` | make a private environment in a folder named `venv` |
| `venv\Scripts\activate` | switch it on for this terminal window |
| `pip install -r requirements.txt` | install every library listed in the file |
| `python -m cpcalc ui` | run the package `cpcalc` with the `ui` option: start the web app |
| `python -m cpcalc examples` | list the built-in examples |
| `python -m cpcalc example D3 --explain` | run example D3 in the terminal and show every step |
| `python -m cpcalc run my_case.xlsx --explain --html sheet.html` | run your own Excel workbook and write an HTML calculation sheet |
| `python -m cpcalc template --out my_case.xlsx` | write an empty Excel workbook to fill in |
| `python -m cpcalc test` | run the tests (needs `requirements-dev.txt`) |
| `deactivate` | leave the virtual environment |

Run all of these from the project folder (the one that contains the `cpcalc` folder).

---

## 4. Run the tests (optional)

```bash
pip install -r requirements-dev.txt
python -m cpcalc test
```

You should see every test pass. The comparison with CoolProp is skipped if CoolProp is not installed.

---

## 5. Deploy the app online (optional)

Deploying puts the app on a server so that **anyone with the link can use it in a browser, without installing Python or any library**. The server installs the libraries itself.

1. **Upload the project to GitHub.** Make sure the repository contains `requirements.txt` and `streamlit_app.py` at its top level, and that the `venv` folder is *not* uploaded (the included `.gitignore` takes care of that).
2. Go to <https://share.streamlit.io> and sign in with your GitHub account.
3. Click **Create app**, choose your repository and branch, and set the main file to **`streamlit_app.py`**.
4. Click **Deploy**. After a few minutes you get a public link such as `https://your-app.streamlit.app`.

Good to know:

- The free version is public, and the app goes to sleep after a period without visitors; the first visit afterwards takes a moment to wake it.
- Every visitor has their own session: nobody sees anyone else's inputs.
- If you change the code on GitHub, the deployed app updates automatically.
- If the `thermo` library fails to install on the server, delete its line from `requirements.txt`. The app still works; only *Find in thermo* is lost.
- Compounds added with *Add a compound* and cases you build live only in the visitor's browser session. Use *Download this case (.xlsx)* to keep them.

---

## 6. Troubleshooting

| What you see | What it means and what to do |
|---|---|
| `'python' is not recognized` (Windows) | Python is not on the PATH. Reinstall it and tick *Add python.exe to PATH*, or try `py` instead of `python`. |
| `python3: command not found` (Mac/Linux) | Install Python from python.org or with your package manager. |
| PowerShell: *running scripts is disabled on this system* | Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, then activate again. Or use Command Prompt instead. |
| `No module named cpcalc` | You are in the wrong folder. `cd` into the folder that contains the `cpcalc` folder. |
| `No module named streamlit` (or numpy, scipy, ...) | The environment is not active (no **(venv)** in the prompt) or step 5 was skipped. Activate it and run `pip install -r requirements.txt`. |
| An error about `width` or `use_container_width` | Your Streamlit is too old. Run `pip install -U "streamlit>=1.51"`. |
| `thermo` fails to install | Remove the `thermo` line from `requirements.txt` and install again. Only *Find in thermo* is lost. |
| The browser does not open | Open <http://localhost:8501> yourself. If the port is busy: `python -m streamlit run cpcalc/app.py --server.port 8502`. |
| **(venv)** appears every time you open VS Code | Normal: VS Code activates the environment for you. To switch it off: *Settings → "python terminal activate environment"*. |
| A result says *calculated under assumptions* or *not calculable* | Not an installation problem. Tab 3 lists the assumptions or exactly what data is missing, and where to type it in tab 2. |
